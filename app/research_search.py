import json
import os
import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urlparse

import requests

from .security import validate_public_https_url
from .ai_import import extract_page
from .research_config import get_settings, source_trust
from .bgg import identify as identify_bgg, BGGError


class ResearchSearchError(RuntimeError):
    pass


def search_provider_name():
    raw = os.environ.get("AUTO_SEARCH_PROVIDER", "searxng" if os.environ.get("SEARXNG_BASE_URL") else "none")
    value = str(raw or "none").strip().lower()
    if value not in {"none", "searxng"}:
        raise ResearchSearchError(f"Unbekannter AUTO_SEARCH_PROVIDER: {value}")
    return value


def _searxng_base_url():
    raw = os.environ.get("SEARXNG_BASE_URL", "").strip().rstrip("/")
    if not raw:
        raise ResearchSearchError("SEARXNG_BASE_URL ist nicht gesetzt.")
    try:
        parsed = urlparse(raw)
    except Exception as exc:
        raise ResearchSearchError("SEARXNG_BASE_URL ist ungültig.") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ResearchSearchError("SEARXNG_BASE_URL muss eine HTTP(S)-URL ohne Zugangsdaten sein.")
    if parsed.query or parsed.fragment:
        raise ResearchSearchError("SEARXNG_BASE_URL darf keine Query-Parameter oder Fragmente enthalten.")
    return raw


def _int_env(name, default, lo, hi):
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    return min(max(value, lo), hi)


def provider_status():
    provider = search_provider_name()
    if provider == "none":
        return {"status": "disabled", "provider": "none"}
    base = _searxng_base_url()
    try:
        response = requests.get(
            f"{base}/",
            headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": "Brettspielregal-Diagnose/8.7.1"},
            timeout=(3, 6), allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise ResearchSearchError("SearXNG ist vom Docker-Backend nicht erreichbar.") from exc
    if response.status_code >= 400:
        raise ResearchSearchError(f"SearXNG antwortete mit HTTP {response.status_code}.")
    return {"status": "ok", "provider": "searxng", "http_status": response.status_code}


def searxng_search(query, limit=None):
    base = _searxng_base_url()
    limit = limit or _int_env("AUTO_SEARCH_RESULTS", 8, 3, 15)
    timeout = _int_env("AUTO_SEARCH_TIMEOUT_SECONDS", 20, 5, 60)
    try:
        response = requests.get(
            f"{base}/search",
            params={"q": query, "format": "json", "language": "de", "safesearch": "1"},
            headers={"Accept": "application/json", "User-Agent": "Brettspielregal-Worker/8.7.1"},
            timeout=(4, timeout),
        )
    except requests.RequestException as exc:
        raise ResearchSearchError("SearXNG ist vom Worker nicht erreichbar.") from exc
    if response.status_code == 403:
        raise ResearchSearchError("SearXNG verweigert JSON-Ausgaben. In settings.yml muss search.formats 'json' enthalten.")
    if response.status_code >= 400:
        raise ResearchSearchError(f"SearXNG antwortete mit HTTP {response.status_code}.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ResearchSearchError("SearXNG lieferte kein gültiges JSON.") from exc
    rows, seen = [], set()
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        try:
            safe = validate_public_https_url(url)
        except ValueError:
            continue
        seen.add(safe)
        rows.append({
            "url": safe,
            "title": str(item.get("title") or "").strip()[:300],
            "content": str(item.get("content") or "").strip()[:1200],
            "engine": str(item.get("engine") or "").strip()[:80],
        })
        if len(rows) >= limit:
            break
    return rows


def _norm(value):
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value.lower()).strip()
    return re.sub(r"\s+", " ", value)


def _expected_title(query, current_game=None):
    current_game = current_game or {}
    title = str(current_game.get("title") or "").strip()
    if title and not title.lower().startswith("ean "):
        return title
    q = str(query or "").strip()
    return "" if q.isdigit() else q


def _query_ean(query, current_game=None):
    current_game = current_game or {}
    candidates = [current_game.get("ean"), query]
    for value in candidates:
        digits = re.sub(r"\D", "", str(value or ""))
        if len(digits) in {8, 12, 13, 14}:
            return digits
    return ""


def score_candidate(row, query, current_game=None, settings=None):
    """Score a SearXNG URL before any page is fetched or shown to Ollama."""
    settings = settings or get_settings()
    current_game = current_game or {}
    title = str(row.get("title") or "")
    snippet = str(row.get("content") or "")
    url = str(row.get("url") or "")
    trust = source_trust(url, settings)
    expected = _expected_title(query, current_game)
    haystack = f"{title} {snippet}"
    score, reasons = 0, []
    if expected:
        a, b = _norm(expected), _norm(title)
        similarity = SequenceMatcher(None, a, b).ratio() if a and b else 0.0
        if a and a in b:
            similarity = max(similarity, min(1.0, len(a) / max(len(b), 1) + 0.20))
        title_points = int(round(similarity * 50))
        score += title_points
        reasons.append(f"Titel {int(round(similarity * 100))}%")
    ean = _query_ean(query, current_game)
    if ean and ean in re.sub(r"\D", "", haystack):
        score += 100; reasons.append("EAN exakt")
    trust_points = {"primary": 30, "reference": 18, "normal": 0, "low": -45}.get(trust, 0)
    score += trust_points
    if trust == "primary": reasons.append("Primärquelle")
    elif trust == "reference": reasons.append("Referenzquelle")
    elif trust == "low": reasons.append("niedrige Priorität")
    lower = f"{title} {url}".lower()
    if re.search(r"\b(rezension|review|spieltest|testbericht|forum|blog)\b", lower):
        score -= 30; reasons.append("Review/Test")
    query_lower = str(query or "").lower()
    if re.search(r"\b(erweiterung|expansion|extension)\b", lower) and not re.search(r"\b(erweiterung|expansion|extension)\b", query_lower):
        score -= 45; reasons.append("mögliche Erweiterung")
    if "boardgamegeek.com/boardgame/" in url.lower():
        score += 18; reasons.append("BGG-Spielseite")
    publisher = _norm(current_game.get("publisher"))
    if publisher and publisher in _norm(haystack):
        score += 12; reasons.append("Verlag passt")
    year = current_game.get("year")
    if year and str(year) in haystack:
        score += 7; reasons.append("Jahr passt")
    row = dict(row)
    row.update({"trust": trust, "score": score, "reasons": reasons})
    return row


def _search_queries(query, current_game, settings):
    expected = _expected_title(query, current_game)
    ean = _query_ean(query, current_game)
    queries = []
    if ean:
        queries += [f'"{ean}" Brettspiel', f'"{ean}" Spiel']
    if expected:
        queries += [f'"{expected}" Brettspiel', f'"{expected}" Spiel Verlag', f'"{expected}" board game']
        # One focused BGG URL-discovery query. Structured BGG lookup runs independently.
        queries.append(f'"{expected}" site:boardgamegeek.com/boardgame')
        primary = (settings.get("primary_domains") or [])[:7]
        if primary:
            queries.append(f'"{expected}" (' + " OR ".join(f"site:{d}" for d in primary) + ")")
    if not queries:
        queries.append(str(query))
    out = []
    for q in queries:
        if q not in out:
            out.append(q)
    return out[:5]


def search(query, current_game=None):
    provider = search_provider_name()
    if provider == "none":
        raise ResearchSearchError("Automatische Websuche ist nicht eingerichtet (AUTO_SEARCH_PROVIDER=none).")
    settings = get_settings()
    current_game = current_game or {}
    rows, errors = [], []
    for q in _search_queries(query, current_game, settings):
        try:
            rows.extend(searxng_search(q, limit=8))
        except ResearchSearchError as exc:
            errors.append(str(exc))
    if not rows and errors:
        raise ResearchSearchError(errors[-1])
    dedup = {}
    for row in rows:
        url = row.get("url")
        if not url or url in dedup:
            continue
        dedup[url] = score_candidate(row, query, current_game, settings)
    return sorted(dedup.values(), key=lambda x: (x.get("score", -999), -len(x.get("url", ""))), reverse=True)[:30]


def _select_candidates(candidates, max_pages, *, allow_bgg_html=False):
    """Build a robust fetch queue from strong candidates.

    v8.7.1 deliberately returns more than ``max_pages`` candidates so a blocked
    publisher/shop page does not abort the whole research job. Only successful
    fetches count against ``max_pages`` later in ``research_game``.
    """
    selected, seen_hosts = [], set()
    ordered = sorted(
        candidates,
        key=lambda x: (x.get("trust") == "primary", x.get("trust") == "reference", x.get("score", -999)),
        reverse=True,
    )
    # Try several alternatives. This is intentionally larger than max_pages,
    # because some otherwise excellent product pages reject automated fetches.
    fetch_budget = min(max(len(candidates), 1), max(6, max_pages * 4))
    for row in ordered:
        trust, score = row.get("trust"), int(row.get("score") or 0)
        url = str(row.get("url", ""))
        is_bgg_html = "boardgamegeek.com/boardgame/" in url.lower()
        if trust == "low":
            continue
        if is_bgg_html and not allow_bgg_html:
            continue
        host = (urlparse(url).hostname or "").lower()
        threshold = 12 if trust == "primary" else 18 if trust == "reference" else 22
        if score < threshold:
            continue
        # Prefer diversity first. A second URL from a host may still be useful,
        # but only after other hosts have had a chance.
        if host in seen_hosts:
            continue
        selected.append(row)
        seen_hosts.add(host)
        if len(selected) >= fetch_budget:
            break

    # If strict thresholds produced nothing, keep one plausible non-low result.
    if not selected:
        fallback = next((
            r for r in ordered
            if r.get("trust") != "low"
            and (allow_bgg_html or "boardgamegeek.com/boardgame/" not in str(r.get("url", "")).lower())
            and int(r.get("score") or 0) >= 5
        ), None)
        if fallback:
            selected.append(fallback)

    selected_urls = {r["url"] for r in selected}
    ignored = [r for r in candidates if r.get("url") not in selected_urls][:12]
    return selected, ignored

def _compact_page_bundle(result, fallback, structured, text, warnings):
    # Search snippets are intentionally excluded. Ollama receives only data fetched from the selected URL.
    safe_structured = {
        "page_title": structured.get("page_title", ""),
        "meta_description": structured.get("meta_description", ""),
        "jsonld_product": structured.get("jsonld_product", {}),
    }
    return {
        "kind": "web_page",
        "url": result["url"],
        "title": result.get("title", ""),
        "trust": result.get("trust", "normal"),
        "candidate_score": result.get("score", 0),
        "candidate_reasons": result.get("reasons", []),
        "extracted": fallback,
        "structured": safe_structured,
        "warnings": warnings,
        "text_excerpt": str(text or "")[:4500],
    }


def research_game(query, current_game=None):
    query = str(query or "").strip()
    if not query:
        raise ResearchSearchError("Suchbegriff fehlt.")
    current_game = current_game or {}
    candidates = search(query, current_game)
    max_pages = _int_env("AUTO_FETCH_PAGES", 3, 1, 4)
    max_total_chars = _int_env("AUTO_RESEARCH_MAX_CHARS", 24000, 8000, 50000)

    # Identify with structured BGG first. When that is unavailable (for example
    # no API token), a public BGG game page is allowed back into the normal web
    # fetch queue as a fallback reference.
    bgg_identity, bgg_error = None, ""
    try:
        bgg_identity = identify_bgg(query, current_game)
    except BGGError as exc:
        bgg_error = str(exc)

    selected, ignored = _select_candidates(
        candidates, max_pages, allow_bgg_html=not bool(bgg_identity)
    )
    bundles, sources, extracted_titles = [], [], []
    fetch_failures = []

    fetched = 0
    for result in selected:
        if fetched >= max_pages:
            break
        try:
            fallback, text, structured, warnings = extract_page(result["url"])
        except Exception as exc:
            result["fetch_error"] = str(exc)[:180]
            fetch_failures.append({"url": result["url"], "error": str(exc)[:180]})
            continue
        fetched += 1
        sources.append(result["url"])
        title = str(fallback.get("title") or "").strip()
        if title and title not in extracted_titles:
            extracted_titles.append(title)
        bundles.append(_compact_page_bundle(result, fallback, structured, text, warnings))

    # EAN-first capture has no title for the BGG search. Once a strong product page
    # reveals the title, do one structured BGG identity lookup with that title.
    if not bgg_identity and extracted_titles:
        try:
            bgg_identity = identify_bgg(extracted_titles[0], {**current_game, "title": extracted_titles[0]})
        except BGGError as exc:
            bgg_error = str(exc)

    if bgg_identity:
        bgg_data = bgg_identity["data"]
        sources.insert(0, bgg_data["url"])
        bundles.insert(0, {
            "kind": "bgg_structured",
            "url": bgg_data["url"],
            "trust": "reference",
            "identity_score": bgg_identity["score"],
            "matched_name": bgg_identity["matched_name"],
            "data": bgg_data,
        })

    if not bundles:
        if not candidates:
            detail = "SearXNG lieferte keine passenden HTTPS-Treffer."
        elif fetch_failures:
            detail = f"{len(fetch_failures)} passende Quelle(n) wurden gefunden, konnten aber nicht abgerufen werden."
        else:
            detail = "Die gefundenen Treffer lagen unter der Vertrauensschwelle."
        if bgg_error:
            detail += " BGG: " + bgg_error
        raise ResearchSearchError("Keine verlässliche Quelle konnte verwendet werden. " + detail)

    evidence_obj = {
        "pipeline": "v8.7-preselected-sources",
        "query": query,
        "important": "SearXNG wurde nur zum Finden von URLs verwendet. Such-Snippets sind KEINE Faktengrundlage.",
        "sources": bundles,
    }
    evidence = json.dumps(evidence_obj, ensure_ascii=False, separators=(",", ":"))[:max_total_chars]
    selected_report = []
    if bgg_identity:
        selected_report.append({
            "kind": "bgg_structured", "title": bgg_identity["data"].get("name") or bgg_identity["matched_name"],
            "url": bgg_identity["data"]["url"], "trust": "reference", "score": bgg_identity["score"],
            "reasons": ["strukturierte BGG-Daten", f"Titelmatch: {bgg_identity['matched_name']}"]
        })
    successful_urls = set(sources)
    for row in candidates:
        if row.get("url") in successful_urls:
            item = {k: row.get(k) for k in ("title", "url", "trust", "score", "reasons")}
            if row.get("fetch_error"):
                item["fetch_error"] = row.get("fetch_error")
            selected_report.append(item)
    ignored_report = [{k: row.get(k) for k in ("title", "url", "trust", "score", "reasons", "fetch_error")} for row in candidates if row.get("url") not in successful_urls][:10]
    report = {
        "pipeline": "v8.7",
        "identity": ({
            "provider": "BoardGameGeek", "bgg_id": bgg_identity["data"]["bgg_id"],
            "title": bgg_identity["data"].get("name", ""), "matched_name": bgg_identity["matched_name"],
            "score": bgg_identity["score"], "url": bgg_identity["data"]["url"],
        } if bgg_identity else None),
        "bgg_error": bgg_error,
        "selected": selected_report[:5],
        "ignored": ignored_report[:8],
        "candidate_count": len(candidates),
        "pages_fetched": fetched,
        "fetch_failures": len(fetch_failures),
    }
    return {
        "query": query,
        "sources": sources[:5],
        "evidence": evidence,
        "results": candidates,
        "pages_fetched": fetched,
        "research": report,
    }

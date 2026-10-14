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
            headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": "Brettspielregal-Diagnose/8.8.3"},
            timeout=(3, 6), allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise ResearchSearchError("SearXNG ist vom Docker-Backend nicht erreichbar.") from exc
    if response.status_code >= 400:
        raise ResearchSearchError(f"SearXNG antwortete mit HTTP {response.status_code}.")
    return {"status": "ok", "provider": "searxng", "http_status": response.status_code}


def _normalize_search_result_url(raw_url):
    """Return a safe public HTTPS candidate and whether HTTP was upgraded.

    Search engines occasionally expose an ``http://`` canonical URL even when
    the same public site supports HTTPS.  We never fetch plain HTTP, but we may
    safely try the equivalent HTTPS URL on the standard port.  Private/local
    targets are still rejected by ``validate_public_https_url``.
    """
    raw_url = str(raw_url or "").strip()
    if not raw_url:
        raise ValueError("Leere URL.")
    parsed = urlparse(raw_url)
    upgraded = False
    if parsed.scheme.lower() == "http":
        if parsed.username or parsed.password:
            raise ValueError("URL mit Zugangsdaten ist nicht erlaubt.")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("Ungültiger Port.") from exc
        if port not in (None, 80):
            raise ValueError("HTTP-URL verwendet einen nicht unterstützten Port.")
        host = parsed.hostname or ""
        if not host:
            raise ValueError("Hostname fehlt.")
        host_text = f"[{host}]" if ":" in host and not host.startswith("[") else host
        parsed = parsed._replace(scheme="https", netloc=host_text)
        raw_url = parsed.geturl()
        upgraded = True
    return validate_public_https_url(raw_url), upgraded


def searxng_search(query, limit=None, *, language="de", safesearch=0, include_meta=False):
    """Search SearXNG and keep only public HTTPS URLs.

    v8.8.0 exposes lightweight diagnostics to the caller while preserving the
    strict public-HTTPS policy used by the page fetcher.
    """
    base = _searxng_base_url()
    limit = limit or _int_env("AUTO_SEARCH_RESULTS", 8, 3, 15)
    timeout = _int_env("AUTO_SEARCH_TIMEOUT_SECONDS", 20, 5, 60)
    try:
        response = requests.get(
            f"{base}/search",
            params={
                "q": query,
                "format": "json",
                "language": language,
                "safesearch": str(safesearch),
                "categories": "general",
            },
            headers={"Accept": "application/json", "User-Agent": "Brettspielregal-Worker/8.8.3"},
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

    raw_results = payload.get("results") or []
    rows, seen = [], set()
    rejected = {"missing_url": 0, "unsafe_url": 0, "duplicate": 0}
    http_upgraded = 0
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            rejected["missing_url"] += 1
            continue
        try:
            safe, upgraded = _normalize_search_result_url(url)
        except ValueError:
            rejected["unsafe_url"] += 1
            continue
        if safe in seen:
            rejected["duplicate"] += 1
            continue
        if upgraded:
            http_upgraded += 1
        seen.add(safe)
        rows.append({
            "url": safe,
            "title": str(item.get("title") or "").strip()[:300],
            "content": str(item.get("content") or "").strip()[:1200],
            "engine": str(item.get("engine") or "").strip()[:80],
        })
        if len(rows) >= limit:
            break

    meta = {
        "query": str(query),
        "language": language,
        "raw_results": len(raw_results),
        "accepted_https": len(rows),
        "http_upgraded": http_upgraded,
        "rejected": rejected,
        "unresponsive_engines": payload.get("unresponsive_engines") or [],
    }
    return (rows, meta) if include_meta else rows

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


def _unique(values):
    out = []
    for value in values:
        value = str(value or "").strip()
        if value and value not in out:
            out.append(value)
    return out


def _search_queries(query, current_game, settings):
    """German-first discovery queries.

    Keep these intentionally simple. Some engines behind SearXNG behave badly
    with quoted expressions, large OR expressions or site filters.
    """
    expected = _expected_title(query, current_game)
    ean = _query_ean(query, current_game)
    queries = []
    if ean:
        queries += [ean, f"{ean} Brettspiel", f"{ean} board game"]
    if expected:
        queries += [
            expected,
            f"{expected} Brettspiel",
            f"{expected} board game",
            f"{expected} BoardGameGeek",
            f"{expected} Verlag",
        ]
    if not queries:
        queries.append(str(query))
    return _unique(queries)[:5]


def _fallback_queries(query, current_game, settings):
    """Broader multilingual rescue queries used only when discovery is weak."""
    expected = _expected_title(query, current_game)
    ean = _query_ean(query, current_game)
    queries = []
    if ean:
        queries += [ean, f"{ean} board game"]
    if expected:
        queries += [expected, f"{expected} board game", f"{expected} BoardGameGeek"]
        # Domain names as plain terms work across more SearXNG engines than a
        # single complex ``site:a OR site:b`` expression.
        for domain in (settings.get("primary_domains") or [])[:3]:
            queries.append(f"{expected} {domain}")
    if not queries:
        queries.append(str(query))
    return _unique(queries)[:6]


def _rank_rows(rows, query, current_game, settings):
    dedup = {}
    for row in rows:
        url = row.get("url")
        if not url or url in dedup:
            continue
        dedup[url] = score_candidate(row, query, current_game, settings)
    return sorted(
        dedup.values(),
        key=lambda x: (x.get("score", -999), -len(x.get("url", ""))),
        reverse=True,
    )[:30]


def _is_plausible_candidate(row):
    if row.get("trust") == "low":
        return False
    score = int(row.get("score") or 0)
    trust = row.get("trust")
    threshold = 12 if trust == "primary" else 18 if trust == "reference" else 22
    return score >= threshold


def search(query, current_game=None, *, return_diagnostics=False):
    provider = search_provider_name()
    if provider == "none":
        raise ResearchSearchError("Automatische Websuche ist nicht eingerichtet (AUTO_SEARCH_PROVIDER=none).")
    settings = get_settings()
    current_game = current_game or {}
    rows, errors, diagnostics = [], [], []

    # Pass 1: German-first discovery. SafeSearch is deliberately disabled for
    # this private metadata lookup; the SearXNG instance remains the policy
    # boundary and only public HTTPS URLs survive validation.
    for q in _search_queries(query, current_game, settings):
        try:
            found, meta = searxng_search(q, limit=8, language="de", safesearch=0, include_meta=True)
            meta["phase"] = "de"
            rows.extend(found)
            diagnostics.append(meta)
            # Enough diverse candidates are available; avoid hammering the
            # local metasearch instance with redundant discovery queries.
            interim = _rank_rows(rows, query, current_game, settings)
            if sum(1 for row in interim if _is_plausible_candidate(row)) >= 3:
                break
        except ResearchSearchError as exc:
            errors.append(str(exc))
            diagnostics.append({"query": q, "language": "de", "phase": "de", "error": str(exc)})

    ranked = _rank_rows(rows, query, current_game, settings)
    plausible_count = sum(1 for row in ranked if _is_plausible_candidate(row))

    # Pass 2: broad multilingual rescue. Run it not only for zero rows, but
    # also when German search returned only weak/noisy candidates. This is the
    # important rescue path for international titles such as "Scythe".
    if plausible_count < 2:
        for q in _fallback_queries(query, current_game, settings):
            try:
                found, meta = searxng_search(q, limit=12, language="all", safesearch=0, include_meta=True)
                meta["phase"] = "multilingual"
                meta["fallback"] = "language=all"
                rows.extend(found)
                diagnostics.append(meta)
                interim = _rank_rows(rows, query, current_game, settings)
                if sum(1 for row in interim if _is_plausible_candidate(row)) >= 3:
                    break
            except ResearchSearchError as exc:
                errors.append(str(exc))
                diagnostics.append({"query": q, "language": "all", "phase": "multilingual", "error": str(exc)})
        ranked = _rank_rows(rows, query, current_game, settings)

    if not ranked and errors and not any(int(d.get("raw_results") or 0) for d in diagnostics if isinstance(d, dict)):
        # Preserve the actionable transport/configuration error when no engine
        # produced any result at all.
        raise ResearchSearchError(errors[-1])

    if return_diagnostics:
        return ranked, diagnostics
    return ranked

def _select_candidates(candidates, max_pages, *, allow_bgg_html=False):
    """Build a robust fetch queue from strong candidates.

    v8.8.0 deliberately returns more than ``max_pages`` candidates so a blocked
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



_SOURCE_CLASS_LABELS = {
    "official": "Offizielle Verlags-/Herstellerseite",
    "structured_reference": "Strukturierte Referenzquelle",
    "reference": "Referenzquelle",
    "rules": "Regel-/Anleitungsquelle",
    "retailer": "Händler/Shop",
    "review": "Rezension/Test",
    "product": "Produktseite",
    "generic": "Webquelle",
}

_GENERIC_NAME_TOKENS = {
    "spiele", "spiel", "games", "game", "verlag", "publisher", "publishing",
    "gmbh", "ag", "kg", "mbh", "inc", "ltd", "llc", "shop", "online", "www",
}

def _name_tokens(value):
    return {
        token for token in _norm(value).split()
        if len(token) >= 4 and token not in _GENERIC_NAME_TOKENS
    }

def _host_tokens(url):
    host = (urlparse(str(url or "")).hostname or "").lower().removeprefix("www.")
    parts = host.split(".")
    stem = " ".join(parts[:-1] if len(parts) > 1 else parts)
    return {
        token for token in re.split(r"[^a-z0-9]+", stem)
        if len(token) >= 4 and token not in _GENERIC_NAME_TOKENS
    }

def _name_matches_host(name, url):
    names = _name_tokens(name)
    hosts = _host_tokens(url)
    return bool(names and hosts and names.intersection(hosts))

def _official_brand_signal(url, text):
    """Recognise publisher-like sites without maintaining an endless domain list.

    Example: ``feuerland-spiele.de`` plus a footer such as
    ``Feuerland Verlagsgesellschaft mbH`` is strong evidence that the fetched
    page belongs to the publisher itself.  A random shop mentioning Feuerland
    does not match because its hostname carries a different brand token.
    """
    hosts = _host_tokens(url)
    if not hosts:
        return False
    normalized = _norm(text)
    official_words = r"(?:verlag|verlagsgesellschaft|publisher|publishing|hersteller|manufacturer)"
    for token in hosts:
        if re.search(rf"\b{re.escape(token)}\b.{{0,80}}\b{official_words}\b", normalized):
            return True
        if re.search(rf"\b{official_words}\b.{{0,80}}\b{re.escape(token)}\b", normalized):
            return True
    return False

def classify_fetched_page(result, fallback, structured, text, current_game=None, settings=None):
    """Second-stage source classification after the page was really fetched.

    Search-result scores are useful for discovery, but they cannot know whether
    a page is the publisher's own product page, a shop or a review.  This pass
    inspects the fetched content and produces the score that decides what Ollama
    actually receives.
    """
    settings = settings or get_settings()
    current_game = current_game or {}
    url = str(result.get("url") or fallback.get("source_url") or "")
    host = (urlparse(url).hostname or "").lower()
    candidate_score = int(result.get("score") or 0)
    trust = result.get("trust") or source_trust(url, settings)
    score = candidate_score
    reasons = []
    source_class = "generic"

    page_title = str(fallback.get("title") or structured.get("page_title") or result.get("title") or "")
    expected = _expected_title("", current_game) or str(result.get("query") or "")
    if not expected:
        expected = str(current_game.get("title") or "")
    if expected and page_title:
        similarity = SequenceMatcher(None, _norm(expected), _norm(page_title)).ratio()
        if _norm(expected) and _norm(expected) in _norm(page_title):
            similarity = max(similarity, 0.88)
        if similarity >= 0.80:
            score += 16; reasons.append("Seiteninhalt passt zum Spieltitel")
        elif similarity < 0.35:
            score -= 35; reasons.append("Seiteninhalt passt schlecht zum Spieltitel")

    lower_surface = _norm(" ".join([str(result.get("title") or ""), url, str(structured.get("page_title") or ""), str(text or "")[:900]]))
    full_norm = _norm(text)
    product = structured.get("jsonld_product") if isinstance(structured, dict) else {}
    if isinstance(product, dict) and product:
        score += 14; reasons.append("strukturierte Produktdaten")
        source_class = "product"

    usable_fields = [
        fallback.get("publisher"), fallback.get("ean"), fallback.get("year"),
        fallback.get("designer"), fallback.get("min_players"), fallback.get("max_players"),
        fallback.get("min_age"), fallback.get("play_time_min"), fallback.get("rules_url"),
    ]
    coverage = sum(v not in (None, "", []) for v in usable_fields)
    if coverage:
        bonus = min(coverage * 3, 21)
        score += bonus; reasons.append(f"{coverage} konkrete Spieldaten erkannt")

    known_publisher = str(fallback.get("publisher") or current_game.get("publisher") or "").strip()
    official = False
    if trust == "primary":
        official = True
        score += 45; reasons.append("als Primärquelle hinterlegt")
    if known_publisher and _name_matches_host(known_publisher, url):
        official = True
        score += 55; reasons.append("Verlag passt zur Domain")
    if _official_brand_signal(url, text):
        official = True
        score += 48; reasons.append("Verlags-/Herstelleridentität auf der Seite erkannt")

    is_bgg = "boardgamegeek.com" in host
    is_wiki = host.endswith("wikipedia.org") or host.endswith("wikidata.org")
    review_surface = re.search(r"\b(rezension|review|spieltest|testbericht|im test|fazit|bewertung)\b", lower_surface)
    shop_surface = re.search(r"\b(warenkorb|lieferzeit|sofort lieferbar|kaufen|checkout|versand|in den cart|add to cart)\b", lower_surface)
    rules_surface = re.search(r"\b(spielregel|spielregeln|rulebook|regeln|anleitung|manual)\b", lower_surface)

    if official:
        source_class = "official"
    elif is_bgg:
        source_class = "reference"
        score += 28; reasons.append("BoardGameGeek-Spielseite")
    elif is_wiki:
        source_class = "reference"
        score += 5; reasons.append("allgemeine Referenzquelle")
        # Wikipedia can help with identity/history, but should not beat a real
        # publisher product page for edition-specific metadata.
        score = min(score, 55)
    elif review_surface:
        source_class = "review"
        score -= 45; reasons.append("Rezension/Test erkannt")
    elif shop_surface:
        source_class = "retailer"
        score -= 8; reasons.append("Händler-/Shopseite erkannt")
    elif rules_surface and fallback.get("rules_url"):
        source_class = "rules"
        score += 12; reasons.append("Regel-/Anleitungsinhalt erkannt")

    if source_class == "official" and fallback.get("rules_url"):
        score += 8; reasons.append("offizielle Anleitung gefunden")
    if source_class == "official" and fallback.get("cover_url"):
        score += 5; reasons.append("Cover auf Primärseite gefunden")

    return {
        **result,
        "source_class": source_class,
        "source_label": _SOURCE_CLASS_LABELS[source_class],
        "post_fetch_score": int(score),
        "post_fetch_reasons": reasons,
    }


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
        "source_class": result.get("source_class", "generic"),
        "source_label": result.get("source_label", "Webquelle"),
        "source_score": result.get("post_fetch_score", result.get("score", 0)),
        "source_reasons": result.get("post_fetch_reasons", []),
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
    settings = get_settings()
    max_pages = _int_env("AUTO_FETCH_PAGES", 3, 1, 4)
    max_total_chars = _int_env("AUTO_RESEARCH_MAX_CHARS", 24000, 8000, 50000)

    # Structured identity is independent of SearXNG and should be attempted
    # first.  With a BGG token, a temporary SearXNG outage must not prevent a
    # well-known game from reaching Ollama.
    bgg_identity, bgg_error = None, ""
    try:
        bgg_identity = identify_bgg(query, current_game)
    except BGGError as exc:
        bgg_error = str(exc)

    try:
        try:
            search_result = search(query, current_game, return_diagnostics=True)
        except TypeError as exc:
            # Backwards-compatible for tests/custom integrations that still
            # provide the pre-v8.8.0 list-only search contract.
            if "return_diagnostics" not in str(exc):
                raise
            search_result = search(query, current_game)
        if isinstance(search_result, tuple) and len(search_result) == 2:
            candidates, search_diagnostics = search_result
        else:
            candidates, search_diagnostics = search_result, []
    except ResearchSearchError as exc:
        # If BGG already identified the game, continue with the structured
        # evidence.  Otherwise this remains a genuine research failure.
        if bgg_identity:
            candidates, search_diagnostics = [], [{"error": str(exc)}]
        else:
            raise

    selected, ignored = _select_candidates(
        candidates, max_pages, allow_bgg_html=not bool(bgg_identity)
    )
    bundles, sources, extracted_titles = [], [], []
    fetch_failures = []
    fetched_pages = []

    # Fetch a few more candidates than Ollama finally receives.  The second
    # stage can only recognise an official publisher page after seeing the real
    # page, so stopping after the first N successful HTTP responses would keep
    # search-result noise artificially ahead of better sources.
    fetch_success_budget = min(6, max(max_pages + 2, max_pages))
    fetched = 0
    for result in selected:
        if fetched >= fetch_success_budget:
            break
        try:
            fallback, text, structured, warnings = extract_page(result["url"])
        except Exception as exc:
            result["fetch_error"] = str(exc)[:180]
            fetch_failures.append({"url": result["url"], "error": str(exc)[:180]})
            continue
        fetched += 1
        title = str(fallback.get("title") or "").strip()
        if title and title not in extracted_titles:
            extracted_titles.append(title)
        classified = classify_fetched_page(result, fallback, structured, text, current_game, settings)
        result.update({
            "source_class": classified.get("source_class"),
            "source_label": classified.get("source_label"),
            "post_fetch_score": classified.get("post_fetch_score"),
            "post_fetch_reasons": classified.get("post_fetch_reasons"),
        })
        fetched_pages.append((classified, fallback, text, structured, warnings))

    fetched_pages.sort(
        key=lambda item: (int(item[0].get("post_fetch_score") or -999), item[0].get("source_class") == "official"),
        reverse=True,
    )
    used_pages = fetched_pages[:max_pages]
    for classified, fallback, text, structured, warnings in used_pages:
        sources.append(classified["url"])
        bundles.append(_compact_page_bundle(classified, fallback, structured, text, warnings))

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
            raw = sum(int(d.get("raw_results") or 0) for d in search_diagnostics if isinstance(d, dict))
            accepted = sum(int(d.get("accepted_https") or 0) for d in search_diagnostics if isinstance(d, dict))
            unresponsive = []
            for d in search_diagnostics:
                if isinstance(d, dict):
                    for item in d.get("unresponsive_engines") or []:
                        name = item[0] if isinstance(item, (list, tuple)) and item else str(item)
                        if name and name not in unresponsive:
                            unresponsive.append(str(name))
            if raw:
                detail = f"SearXNG lieferte {raw} Roh-Treffer, aber keinen verwendbaren öffentlichen HTTPS-Treffer."
            else:
                detail = "SearXNG lieferte auch bei einer einfachen mehrsprachigen Suche keine Treffer."
            if unresponsive:
                detail += " Nicht antwortende Suchmaschinen: " + ", ".join(unresponsive[:6]) + "."
        elif fetch_failures:
            detail = f"{len(fetch_failures)} passende Quelle(n) wurden gefunden, konnten aber nicht abgerufen werden."
            first_error = str(fetch_failures[0].get("error") or "").strip()
            if first_error:
                detail += " Erster Abruffehler: " + first_error[:140]
        else:
            top_score = max((int(row.get("score") or 0) for row in candidates), default=0)
            detail = f"{len(candidates)} öffentliche HTTPS-Treffer wurden gefunden, aber keiner war verlässlich genug (beste Bewertung: {top_score})."
        if bgg_error:
            detail += " BGG: " + bgg_error
        raise ResearchSearchError("Keine verlässliche Quelle konnte verwendet werden. " + detail)

    evidence_obj = {
        "pipeline": "v8.8-postfetch-ranked-field-evidence",
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
            "source_class": "structured_reference", "source_label": "Strukturierte Referenzquelle",
            "post_fetch_score": bgg_identity["score"],
            "reasons": ["strukturierte BGG-Daten", f"Titelmatch: {bgg_identity['matched_name']}"]
        })
    successful_urls = set(sources)
    for row in candidates:
        if row.get("url") in successful_urls:
            item = {k: row.get(k) for k in ("title", "url", "trust", "score", "reasons", "source_class", "source_label", "post_fetch_score", "post_fetch_reasons")}
            if row.get("fetch_error"):
                item["fetch_error"] = row.get("fetch_error")
            selected_report.append(item)
    selected_report.sort(key=lambda item: int(item.get("post_fetch_score") if item.get("post_fetch_score") is not None else item.get("score") or -999), reverse=True)
    ignored_report = [{k: row.get(k) for k in ("title", "url", "trust", "score", "reasons", "fetch_error", "source_class", "source_label", "post_fetch_score", "post_fetch_reasons")} for row in candidates if row.get("url") not in successful_urls][:10]
    report = {
        "pipeline": "v8.8.3",
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
        "pages_used": len(used_pages),
        "fetch_failures": len(fetch_failures),
        "search_diagnostics": search_diagnostics[-6:],
    }
    return {
        "query": query,
        "sources": sources[:5],
        "evidence": evidence,
        "results": candidates,
        "pages_fetched": fetched,
        "pages_used": len(used_pages),
        "research": report,
        "_field_source_bundles": bundles,
    }

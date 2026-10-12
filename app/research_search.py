import json
import os
from urllib.parse import urlparse

import requests

from .security import validate_public_https_url
from .ai_import import extract_page
from .research_config import get_settings, source_trust


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


def searxng_search(query, limit=None):
    base = _searxng_base_url()
    limit = limit or _int_env("AUTO_SEARCH_RESULTS", 8, 3, 15)
    timeout = _int_env("AUTO_SEARCH_TIMEOUT_SECONDS", 20, 5, 60)
    try:
        response = requests.get(
            f"{base}/search",
            params={"q": query, "format": "json", "language": "de", "safesearch": "1"},
            headers={"Accept": "application/json", "User-Agent": "Brettspielregal-Worker/8.4"},
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
    rows = []
    seen = set()
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


def search(query):
    provider = search_provider_name()
    if provider == "none":
        raise ResearchSearchError("Automatische Websuche ist nicht eingerichtet (AUTO_SEARCH_PROVIDER=none).")
    settings = get_settings()
    rows = []
    # Primärquellen zuerst gezielt anfragen. SearXNG reicht site:-Operatoren an die Suchmaschinen weiter.
    primary = settings.get("primary_domains") or []
    reference = settings.get("reference_domains") or []
    preferred = (primary + reference)[:10]
    if preferred:
        domain_clause = " OR ".join(f"site:{d}" for d in preferred)
        try:
            rows.extend(searxng_search(f"{query} ({domain_clause})", limit=12))
        except ResearchSearchError:
            pass
    # BoardGameGeek gezielt zusätzlich anfragen, weil Titel und IDs häufig besser matchen als bei Shops.
    if reference:
        ref_clause = " OR ".join(f"site:{d}" for d in reference[:4])
        try:
            rows.extend(searxng_search(f"{query} ({ref_clause})", limit=6))
        except ResearchSearchError:
            pass
    rows.extend(searxng_search(query))
    dedup = {}
    for row in rows:
        url = row.get("url")
        if not url or url in dedup:
            continue
        row = dict(row)
        row["trust"] = source_trust(url, settings)
        dedup[url] = row
    order = {"primary": 0, "reference": 1, "normal": 2, "low": 3}
    return sorted(dedup.values(), key=lambda x: order.get(x.get("trust"), 1))[:15]


def research_game(query):
    query = str(query or "").strip()
    if not query:
        raise ResearchSearchError("Suchbegriff fehlt.")
    results = search(query)
    if not results:
        raise ResearchSearchError("Die Websuche hat keine passenden Treffer geliefert.")

    max_pages = _int_env("AUTO_FETCH_PAGES", 4, 1, 8)
    max_total_chars = _int_env("AUTO_RESEARCH_MAX_CHARS", 30000, 8000, 60000)
    chunks = [f"Suchanfrage: {query}\n"]
    sources = []
    fetched = 0

    for index, result in enumerate(results, 1):
        sources.append(result["url"])
        trust = result.get("trust") or "normal"
        chunks.append(
            f"\n=== Suchtreffer {index} [{trust.upper()}] ===\nTitel: {result['title']}\nURL: {result['url']}\nSuchsnippet: {result['content']}\n"
        )
        if trust == "low":
            chunks.append("Niedrig priorisierte Quelle: nicht direkt als Kerndatenquelle abrufen.\n")
            continue
        if trust == "reference":
            chunks.append("Strukturierte Referenzquelle: für allgemeine Spieldaten nutzen; deutsche Ausgabe, EAN, Cover und Anleitung gegen Herstellerdaten prüfen.\n")
        if fetched >= max_pages:
            continue
        try:
            fallback, text, structured, warnings = extract_page(result["url"])
        except Exception as exc:
            chunks.append(f"Direkter Abruf nicht verfügbar: {str(exc)[:180]}\n")
            continue
        fetched += 1
        chunks.append("Vorab extrahierte Metadaten: " + json.dumps(fallback, ensure_ascii=False)[:5000] + "\n")
        if structured:
            chunks.append("Strukturierte Seitendaten: " + json.dumps(structured, ensure_ascii=False)[:4000] + "\n")
        if warnings:
            chunks.append("Erkannte Warnungen: " + json.dumps(warnings, ensure_ascii=False)[:1500] + "\n")
        if text:
            chunks.append("Seitentext:\n" + text[:7000] + "\n")
        if sum(len(x) for x in chunks) >= max_total_chars:
            break

    evidence = "".join(chunks)[:max_total_chars]
    return {"query": query, "sources": sources[:20], "evidence": evidence, "results": results, "pages_fetched": fetched}

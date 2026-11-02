"""Suggest, never auto-accept, potential publisher-hosted PDF rulebooks."""
from urllib.parse import urlparse
import re
from .research_search import searxng_search, ResearchSearchError
from .research_config import get_settings


def rules_candidates(game):
    title = str((game or {}).get("title") or "").strip()[:180]
    if not title:
        raise ValueError("Spieltitel fehlt.")
    publisher = str((game or {}).get("publisher") or "").strip()[:90]
    # Search metadata alone is never proof that a document is an official rulebook.
    queries = [f"{title} {publisher} Spielanleitung PDF", f"{title} Brettspiel Regeln PDF"]
    sources = get_settings()
    preferred = {str(x).lower().removeprefix("www.") for x in sources.get("primary_domains", [])}
    found = []
    seen = set()
    for query in queries:
        for row in searxng_search(query, limit=12):
            url = str(row.get("url") or "")
            host = (urlparse(url).hostname or "").lower().removeprefix("www.")
            if url in seen or not host:
                continue
            seen.add(url)
            text = (str(row.get("title") or "")+" "+str(row.get("content") or "")).lower()
            if not ("pdf" in url.lower() or re.search(r"anleitung|regel|rulebook|rules\b",text)):
                continue
            official = any(host==domain or host.endswith("."+domain) for domain in preferred)
            pdf = urlparse(url).path.lower().endswith(".pdf")
            score = (50 if official else 0) + (20 if pdf else 0) + (10 if publisher and publisher.lower() in text else 0)
            found.append({"url": url[:2000], "title": str(row.get("title") or host)[:200],
                          "host": host, "pdf_link": pdf, "publisher_domain": official,
                          "score": score, "verified": False})
    found.sort(key=lambda x:x["score"],reverse=True)
    return {"candidates": found[:8], "note": "Suchtreffer sind nicht verifiziert. Vor dem Speichern den Verlag und die PDF selbst prüfen.", "web_search_used": True, "verified": False}

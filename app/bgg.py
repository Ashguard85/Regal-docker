import html
import os
import re
import time
import unicodedata
import threading
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

import requests
from bs4 import BeautifulSoup


BGG_API_BASE = "https://boardgamegeek.com/xmlapi2"
BGG_PUBLIC_BASE = "https://boardgamegeek.com/boardgame"
_LAST_REQUEST_AT = 0.0
_RATE_LOCK = threading.Lock()


class BGGError(RuntimeError):
    pass


def enabled():
    return os.environ.get("BGG_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def _timeout():
    try:
        return min(max(int(os.environ.get("BGG_TIMEOUT_SECONDS", "15")), 5), 45)
    except ValueError:
        return 15


def _token():
    return str(os.environ.get("BGG_API_TOKEN", "") or "").strip()


def _min_interval():
    try:
        return min(max(float(os.environ.get("BGG_MIN_INTERVAL_SECONDS", "5")), 1.0), 15.0)
    except ValueError:
        return 5.0


def _wait_rate_limit():
    global _LAST_REQUEST_AT
    with _RATE_LOCK:
        delay = _min_interval() - (time.monotonic() - _LAST_REQUEST_AT)
        if delay > 0:
            time.sleep(delay)
        _LAST_REQUEST_AT = time.monotonic()


def _norm(value):
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value.lower()).strip()
    return re.sub(r"\s+", " ", value)


def _similarity(a, b):
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ratio = SequenceMatcher(None, a, b).ratio()
    # Subtitles and localized suffixes should not destroy an otherwise exact title match.
    if a in b or b in a:
        ratio = max(ratio, min(len(a), len(b)) / max(len(a), len(b)))
    return ratio


def _get(path, params):
    if not enabled():
        raise BGGError("BoardGameGeek-Referenz ist deaktiviert.")
    token = _token()
    if not token:
        raise BGGError("BGG_API_TOKEN fehlt; strukturierte BoardGameGeek-Daten sind deshalb deaktiviert.")
    last = None
    for attempt in range(3):
        _wait_rate_limit()
        try:
            response = requests.get(
                f"{BGG_API_BASE}/{path}",
                params=params,
                headers={
                    "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.1",
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "Brettspielregal/8.7.2 (private self-hosted collection)",
                },
                timeout=(4, _timeout()),
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            last = exc
            time.sleep(0.5 * (attempt + 1))
            continue
        if response.status_code == 202:
            time.sleep(1.0 * (attempt + 1))
            continue
        if response.status_code in {429, 500, 503}:
            last = BGGError(f"BoardGameGeek ist momentan ausgelastet (HTTP {response.status_code}).")
            time.sleep(1.0 * (attempt + 1))
            continue
        if response.status_code in {401, 403}:
            raise BGGError("BoardGameGeek hat den API-Token abgelehnt. BGG_API_TOKEN prüfen.")
        if response.status_code >= 400:
            raise BGGError(f"BoardGameGeek antwortete mit HTTP {response.status_code}.")
        try:
            return ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise BGGError("BoardGameGeek lieferte ungültiges XML.") from exc
    raise BGGError(str(last) if isinstance(last, BGGError) else "BoardGameGeek ist momentan nicht erreichbar.") from (last if isinstance(last, Exception) else None)


def search(query, limit=8):
    query = str(query or "").strip()
    if not query or query.isdigit():
        return []
    root = _get("search", {"query": query, "type": "boardgame,boardgameexpansion"})
    rows = []
    for item in root.findall("item"):
        names = [n.get("value", "").strip() for n in item.findall("name") if n.get("value")]
        name = names[0] if names else ""
        if not name:
            continue
        try:
            item_id = int(item.get("id", "0"))
        except ValueError:
            continue
        year = None
        year_node = item.find("yearpublished")
        if year_node is not None:
            try:
                year = int(year_node.get("value", ""))
            except (ValueError, TypeError):
                pass
        rows.append({
            "id": item_id,
            "name": name,
            "year": year,
            "similarity": round(_similarity(query, name), 4),
            "url": f"{BGG_PUBLIC_BASE}/{item_id}",
        })
    rows.sort(key=lambda x: x["similarity"], reverse=True)
    return rows[:max(1, min(int(limit), 15))]


def _value(item, tag, cast=None):
    node = item.find(tag)
    if node is None:
        return None
    value = node.get("value")
    if value in (None, ""):
        return None
    if cast:
        try:
            return cast(value)
        except (TypeError, ValueError):
            return None
    return value


def _links(item, type_name):
    out = []
    for node in item.findall("link"):
        if node.get("type") != type_name:
            continue
        value = str(node.get("value") or "").strip()
        if value and value not in out:
            out.append(value)
    return out


def _description(item):
    node = item.find("description")
    raw = node.text if node is not None else ""
    raw = html.unescape(raw or "")
    text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)[:5000]


def thing(item_id):
    root = _get("thing", {"id": str(int(item_id)), "stats": "1"})
    item = root.find("item")
    if item is None:
        raise BGGError("BoardGameGeek hat keinen Datensatz zu dieser ID geliefert.")
    primary = ""
    alternates = []
    for node in item.findall("name"):
        value = str(node.get("value") or "").strip()
        if not value:
            continue
        if node.get("type") == "primary" and not primary:
            primary = value
        elif value not in alternates:
            alternates.append(value)
    if not primary and alternates:
        primary = alternates.pop(0)
    try:
        bgg_id = int(item.get("id", item_id))
    except ValueError:
        bgg_id = int(item_id)
    image_node = item.find("image")
    thumb_node = item.find("thumbnail")
    image = (image_node.text or "").strip() if image_node is not None else ""
    thumbnail = (thumb_node.text or "").strip() if thumb_node is not None else ""
    # An inbound boardgameexpansion link usually means this item is an expansion of a base game.
    expansion_of = []
    for node in item.findall("link"):
        if node.get("type") == "boardgameexpansion" and str(node.get("inbound") or "").lower() in {"true", "1"}:
            expansion_of.append(str(node.get("value") or "").strip())
    return {
        "bgg_id": bgg_id,
        "item_type": str(item.get("type") or "boardgame"),
        "name": primary,
        "alternate_names": alternates[:20],
        "year": _value(item, "yearpublished", int),
        "min_players": _value(item, "minplayers", int),
        "max_players": _value(item, "maxplayers", int),
        "play_time_min": _value(item, "playingtime", int),
        "min_age": _value(item, "minage", int),
        "designers": _links(item, "boardgamedesigner")[:10],
        "publishers": _links(item, "boardgamepublisher")[:10],
        "mechanics": _links(item, "boardgamemechanic")[:30],
        "categories": _links(item, "boardgamecategory")[:30],
        "families": _links(item, "boardgamefamily")[:20],
        "description": _description(item),
        "image": image,
        "thumbnail": thumbnail,
        "expansion_of": [x for x in expansion_of if x][:10],
        "url": f"{BGG_PUBLIC_BASE}/{bgg_id}",
    }


def identify(query, current_game=None):
    """Return the best structured BGG identity candidate, or None when confidence is weak."""
    if not enabled():
        return None
    current_game = current_game or {}
    expected = str(current_game.get("title") or "").strip()
    if not expected or expected.lower().startswith("ean "):
        expected = str(query or "").strip()
    # BGG search is title-oriented, not an EAN resolver.
    if not expected or expected.isdigit() or len(re.sub(r"\D", "", expected)) in {8, 12, 13, 14} and not re.search(r"[A-Za-zÄÖÜäöüß]", expected):
        return None
    candidates = search(expected, limit=8)
    if not candidates:
        return None
    best = candidates[0]
    score = int(round(best["similarity"] * 80))
    if best["similarity"] >= 0.97:
        score += 15
    current_year = current_game.get("year")
    if current_year and best.get("year") == current_year:
        score += 5
    score = min(score, 100)
    if score < 48:
        return None
    data = thing(best["id"])
    # Re-score against aliases from the full record.
    all_names = [data.get("name", ""), *(data.get("alternate_names") or [])]
    similarity = max((_similarity(expected, n) for n in all_names if n), default=best["similarity"])
    score = min(100, max(score, int(round(similarity * 90))))
    return {
        "score": score,
        "matched_name": max((n for n in all_names if n), key=lambda n: _similarity(expected, n), default=data.get("name", "")),
        "query": expected,
        "data": data,
        "search_candidates": candidates[:5],
    }

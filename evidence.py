import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urlparse


DERIVED_FIELDS = {"description", "rules_text", "tags"}
NEVER_BULK_APPLY = {"title", "description", "rules_text", "tags", "award"}
NUMERIC_FIELDS = {"min_players", "max_players", "play_time_min", "min_age", "year"}
URL_FIELDS = {"source_url", "rules_url", "cover_url"}
CONFLICT_FIELDS = NUMERIC_FIELDS | {"ean"}

LEVEL_LABELS = {
    "primary": "Primärquelle",
    "strong": "Gut belegt",
    "single": "Eine Quelle",
    "derived": "KI-abgeleitet",
    "conflict": "Widerspruch",
}


def _norm_text(value):
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value.lower()).strip()
    return re.sub(r"\s+", " ", value)


def _url_norm(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        path = re.sub(r"/+", "/", parsed.path or "/").rstrip("/") or "/"
        return f"{parsed.scheme.lower()}://{host}{path}"
    except Exception:
        return raw.rstrip("/").lower()


def _as_values(value):
    if value in (None, "", []):
        return []
    if isinstance(value, (list, tuple, set)):
        return [v for v in value if v not in (None, "", [])]
    return [value]


def _equivalent(field, proposed, source_value):
    if proposed in (None, "", []) or source_value in (None, "", []):
        return False
    if field in NUMERIC_FIELDS:
        try:
            return int(proposed) == int(source_value)
        except (TypeError, ValueError):
            return False
    if field in URL_FIELDS:
        return bool(_url_norm(proposed) and _url_norm(proposed) == _url_norm(source_value))

    p = _norm_text(proposed)
    s = _norm_text(source_value)
    if not p or not s:
        return False
    if p == s:
        return True
    if field == "title":
        return SequenceMatcher(None, p, s).ratio() >= 0.86 or p in s or s in p
    if field in {"publisher", "designer"}:
        # Source records may contain several names while the approved value is a
        # single person/publisher. Avoid loose generic substring matching.
        if len(p) >= 5 and len(s) >= 5 and (p in s or s in p):
            return True
        return SequenceMatcher(None, p, s).ratio() >= 0.90
    return SequenceMatcher(None, p, s).ratio() >= 0.94


def _value_key(field, value):
    if value in (None, "", []):
        return ""
    if field in NUMERIC_FIELDS:
        try:
            return str(int(value))
        except (TypeError, ValueError):
            pass
    if field in URL_FIELDS:
        return _url_norm(value)
    return _norm_text(value)


def _source_name(bundle):
    if bundle.get("kind") == "bgg_structured":
        data = bundle.get("data") or {}
        return str(data.get("name") or bundle.get("matched_name") or "BoardGameGeek")
    title = str(bundle.get("title") or "").strip()
    if title:
        return title[:180]
    try:
        return (urlparse(str(bundle.get("url") or "")).hostname or "Quelle").removeprefix("www.")
    except Exception:
        return "Quelle"


def _source_label(bundle):
    if bundle.get("kind") == "bgg_structured":
        return "Strukturierte Referenzquelle"
    return str(bundle.get("source_label") or "Webquelle")


def _source_class(bundle):
    if bundle.get("kind") == "bgg_structured":
        return "structured_reference"
    return str(bundle.get("source_class") or "generic")


def _field_values(bundle, field):
    if bundle.get("kind") == "bgg_structured":
        data = bundle.get("data") or {}
        mapping = {
            "title": data.get("name"),
            "description": data.get("description"),
            "source_url": data.get("url") or bundle.get("url"),
            "min_players": data.get("min_players"),
            "max_players": data.get("max_players"),
            "play_time_min": data.get("play_time_min"),
            "min_age": data.get("min_age"),
            "year": data.get("year"),
            "designer": data.get("designers") or [],
            "publisher": data.get("publishers") or [],
            "cover_url": data.get("image") or data.get("thumbnail"),
        }
        return _as_values(mapping.get(field))
    extracted = bundle.get("extracted") or {}
    if field == "source_url":
        return _as_values(extracted.get("source_url") or bundle.get("url"))
    return _as_values(extracted.get(field))


def _source_descriptor(bundle, value=None):
    return {
        "name": _source_name(bundle),
        "url": str(bundle.get("url") or ""),
        "source_label": _source_label(bundle),
        "source_class": _source_class(bundle),
        "value": value,
    }


def build_field_evidence(proposed_game, bundles):
    """Build deterministic per-field provenance from already fetched sources.

    No additional model request or HTTP request is performed here. The function
    only compares Qwen's normalized proposal with values that were already
    extracted from the selected source pages / structured BGG record.
    """
    bundles = [b for b in (bundles or []) if isinstance(b, dict)]
    result = {}
    for field, proposed in (proposed_game or {}).items():
        if proposed in (None, "", []):
            continue

        if field in DERIVED_FIELDS:
            source_refs = [_source_descriptor(b) for b in bundles[:4]]
            result[field] = {
                "level": "derived",
                "label": LEVEL_LABELS["derived"],
                "safe_to_apply": False,
                "summary": f"Aus {len(source_refs)} ausgewählten Quelle{'n' if len(source_refs) != 1 else ''} von der KI zusammengeführt." if source_refs else "Von der KI aus dem Recherchematerial abgeleitet.",
                "sources": source_refs,
                "conflicts": [],
            }
            continue

        supports = []
        observed = []
        for bundle in bundles:
            vals = _field_values(bundle, field)
            for raw in vals:
                if raw in (None, "", []):
                    continue
                desc = _source_descriptor(bundle, raw)
                observed.append(desc)
                if _equivalent(field, proposed, raw):
                    supports.append(desc)

        # Distinct contradictory values from independent sources. Only count
        # values that are not equivalent to the proposal and are not duplicates.
        conflict_values = []
        seen_conflicts = set()
        if field in CONFLICT_FIELDS:
            for item in observed:
                if _equivalent(field, proposed, item["value"]):
                    continue
                key = _value_key(field, item["value"])
                if not key or key in seen_conflicts:
                    continue
                seen_conflicts.add(key)
                conflict_values.append(item)

        official_support = [s for s in supports if s.get("source_class") == "official"]
        independent_support_hosts = set()
        for s in supports:
            try:
                independent_support_hosts.add((urlparse(s.get("url") or "").hostname or s.get("name") or "").lower())
            except Exception:
                independent_support_hosts.add(s.get("name") or "")

        # A conflict is meaningful only when the proposed value is directly
        # supported somewhere and another selected source provides another value.
        has_conflict = bool(supports and conflict_values)
        if has_conflict:
            level = "conflict"
            summary = "Ausgewählte Quellen nennen unterschiedliche Werte. Bitte einzeln prüfen."
        elif official_support:
            level = "primary"
            summary = f"Offizielle Quelle bestätigt den Wert: {official_support[0]['name']}."
        elif len(independent_support_hosts) >= 2:
            level = "strong"
            summary = f"{len(independent_support_hosts)} unabhängige Quellen stimmen überein."
        elif supports:
            level = "single"
            summary = f"Eine Quelle bestätigt den Wert: {supports[0]['name']}."
        else:
            level = "derived"
            summary = "Der vorgeschlagene Wert ist in den strukturiert extrahierten Feldern nicht direkt belegt; er wurde aus dem Quellenmaterial abgeleitet."

        safe = level in {"primary", "strong"} and field not in NEVER_BULK_APPLY
        result[field] = {
            "level": level,
            "label": LEVEL_LABELS[level],
            "safe_to_apply": safe,
            "summary": summary,
            "sources": supports[:5] if supports else [_source_descriptor(b) for b in bundles[:3]],
            "conflicts": conflict_values[:5],
        }
    return result

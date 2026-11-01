"""Deterministic source selection for new captures and explicit refreshes."""
import re
from urllib.parse import urlparse


def is_ean(value):
    text = str(value or "").strip()
    digits = re.sub(r"[ -]", "", text)
    return len(digits) in {8, 12, 13, 14} and digits.isdigit()


def is_explicit_link(value):
    try:
        p = urlparse(str(value or "").strip())
        return p.scheme.lower() == "https" and bool(p.hostname)
    except ValueError:
        return False


def choose_mode(job, game, settings):
    """full on refresh, EAN or user URL; BGG-only for initial title capture."""
    if job.get("search_scope") != "initial":
        return "full"
    if not settings.get("initial_bgg_only", True):
        return "full"
    if is_ean(job.get("query")) or is_ean(game.get("ean")):
        return "full"  # XML API2 cannot search GTIN/EAN.
    if is_explicit_link(job.get("query")) or is_explicit_link(game.get("source_url")):
        return "full"
    return "bgg_only"

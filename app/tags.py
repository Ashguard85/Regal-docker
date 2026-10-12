import re

# v8.4: Kanonische Tags werden ausschließlich auf Deutsch gespeichert/angezeigt.
TAG_CATEGORIES = {
    "Spielart": [
        "Familienspiel", "Kinderspiel", "Kennerspiel", "Expertenspiel", "Partyspiel",
        "Solospiel", "Zweipersonenspiel", "Kooperativ", "Kompetitiv",
    ],
    "Mechanik": [
        "Deckbau", "Kartenauswahl", "Arbeitereinsatz", "Plättchenlegen", "Sets sammeln",
        "Risikoabwägung", "Handkartenmanagement", "Gebietskontrolle", "Kombinationsaufbau",
        "Würfeln & Eintragen", "Deduktion", "Versteigerung", "Stichspiel", "Geschicklichkeit",
        "Gedächtnis", "Rätsel", "Kampagne", "Routenbau", "Mehrheiten", "Würfelspiel", "Kartenspiel",
    ],
    "Thema": [
        "Fantasy", "Science-Fiction", "Abenteuer", "Natur & Tiere", "Historisch", "Krimi",
        "Wirtschaft", "Weltraum", "Eisenbahn", "Städtebau", "Landwirtschaft", "Piraten", "Horror",
    ],
    "Eigenschaften": [
        "Schnell gelernt", "Kurze Partie", "Lange Partie", "Strategisch", "Taktisch",
        "Glückslastig", "Hohe Interaktion", "Wenig Interaktion", "Asymmetrisch",
        "Hoher Wiederspielwert", "Reisetauglich",
    ],
}

# Englische BGG-/Shop-Begriffe und ältere v8.3-Tags werden auf deutsche Werte normalisiert.
ALIASES = {
    "familie": "Familienspiel", "family game": "Familienspiel", "family": "Familienspiel",
    "kinder": "Kinderspiel", "kids": "Kinderspiel", "kenner": "Kennerspiel",
    "expert": "Expertenspiel", "experte": "Expertenspiel", "party": "Partyspiel",
    "solo": "Solospiel", "1 spieler": "Solospiel", "2 spieler": "Zweipersonenspiel",
    "2-player": "Zweipersonenspiel", "coop": "Kooperativ", "co-op": "Kooperativ",
    "cooperative": "Kooperativ", "cooperative game": "Kooperativ", "kooperatives spiel": "Kooperativ",
    "competitive": "Kompetitiv",
    "deckbuilding": "Deckbau", "deck building": "Deckbau", "deck building game": "Deckbau",
    "drafting": "Kartenauswahl", "card drafting": "Kartenauswahl",
    "worker placement": "Arbeitereinsatz", "worker-placement": "Arbeitereinsatz", "arbeiter einsetzen": "Arbeitereinsatz",
    "tile placement": "Plättchenlegen", "tile-laying": "Plättchenlegen", "plättchen legen": "Plättchenlegen",
    "set collection": "Sets sammeln", "sets sammeln": "Sets sammeln",
    "push your luck": "Risikoabwägung", "press your luck": "Risikoabwägung",
    "hand management": "Handkartenmanagement",
    "area control": "Gebietskontrolle", "area majority": "Mehrheiten",
    "engine building": "Kombinationsaufbau", "engine builder": "Kombinationsaufbau",
    "roll & write": "Würfeln & Eintragen", "roll and write": "Würfeln & Eintragen",
    "deduction": "Deduktion", "auction": "Versteigerung", "trick taking": "Stichspiel",
    "trick-taking": "Stichspiel", "dexterity": "Geschicklichkeit", "memory": "Gedächtnis",
    "puzzle": "Rätsel", "legacy": "Kampagne", "campaign": "Kampagne",
    "route building": "Routenbau", "dice game": "Würfelspiel", "card game": "Kartenspiel",
    "sci-fi": "Science-Fiction", "science fiction": "Science-Fiction", "nature": "Natur & Tiere",
    "animals": "Natur & Tiere", "historical": "Historisch", "mystery": "Krimi",
    "economic": "Wirtschaft", "space": "Weltraum", "railroad": "Eisenbahn",
    "city building": "Städtebau", "farming": "Landwirtschaft", "horror": "Horror",
    "strategy": "Strategisch", "strategiespiel": "Strategisch", "tactical": "Taktisch",
    "luck": "Glückslastig", "high interaction": "Hohe Interaktion", "low interaction": "Wenig Interaktion",
    "asymmetric": "Asymmetrisch", "replayability": "Hoher Wiederspielwert", "travel": "Reisetauglich",
    # ältere kanonische Werte aus v8.3
    "worker placement": "Arbeitereinsatz", "tile placement": "Plättchenlegen", "set collection": "Sets sammeln",
    "push your luck": "Risikoabwägung", "engine building": "Kombinationsaufbau", "memory": "Gedächtnis",
    "kampagne/legacy": "Kampagne",
}

_REJECT_PATTERNS = [
    r"^spiele?\s+mit\b", r"^spiele?\s+von\b", r"merchandise", r"gesellschaftsspiel$",
    r"brettspiel$", r"rezension", r"review", r"testbericht", r"spieletest",
]


def tag_catalog():
    return {category: list(values) for category, values in TAG_CATEGORIES.items()}


def all_tags():
    return [tag for values in TAG_CATEGORIES.values() for tag in values]


def _key(value):
    text = str(value or "").strip().lower()
    return re.sub(r"\s+", " ", text)


def normalize_tag(value):
    text = str(value or "").strip()
    if not text:
        return ""
    key = _key(text)
    if any(re.search(pattern, key) for pattern in _REJECT_PATTERNS):
        return ""
    canonical = {tag.lower(): tag for tag in all_tags()}
    if key in canonical:
        return canonical[key]
    return ALIASES.get(key, "")


def normalize_tags(values, limit=12):
    if isinstance(values, str):
        values = [part.strip() for part in re.split(r"[,;\n]", values) if part.strip()]
    out = []
    for value in values or []:
        tag = normalize_tag(value)
        if tag and tag not in out:
            out.append(tag)
        if len(out) >= limit:
            break
    return out


def category_for(tag):
    for category, values in TAG_CATEGORIES.items():
        if tag in values:
            return category
    return "Sonstige"


def prompt_catalog():
    lines = []
    for category, values in TAG_CATEGORIES.items():
        lines.append(f"{category}: " + ", ".join(values))
    return "\n".join(lines)

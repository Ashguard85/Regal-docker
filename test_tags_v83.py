from app.tags import normalize_tags, tag_catalog
from app.research_config import render_research_prompt


def test_tag_normalization_rejects_navigation_noise():
    tags = normalize_tags([
        "Spiele mit L", "Spiele von N – S", "Merchandiseprodukt",
        "Family", "coop", "Deck Building", "Science Fiction",
    ])
    assert tags == ["Familienspiel", "Kooperativ", "Deckbau", "Science-Fiction"]


def test_tag_catalog_has_useful_categories():
    catalog = tag_catalog()
    assert "Spielart" in catalog
    assert "Mechanik" in catalog
    assert "Thema" in catalog
    assert "Eigenschaften" in catalog
    assert "Kooperativ" in catalog["Spielart"]
    assert "Arbeitereinsatz" in catalog["Mechanik"]


def test_research_prompt_always_contains_controlled_tags():
    settings = {
        "primary_domains": ["kosmos.de"],
        "reference_domains": ["boardgamegeek.com"],
        "low_trust_domains": ["spieletest.at"],
        "system_prompt": "system",
        "research_prompt": "Query={{QUERY}}\nGame={{CURRENT_GAME}}\nSources={{SOURCES}}\nEvidence={{EVIDENCE}}",
    }
    text = render_research_prompt("Cascadia", {"title":"Cascadia"}, ["https://kosmos.de/x"], "evidence", settings)
    assert "VERBINDLICHE TAG-REGELN" in text
    assert "Familienspiel" in text
    assert "Deckbau" in text

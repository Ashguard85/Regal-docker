import importlib
import os


def _settings():
    return {
        "primary_domains": [],
        "reference_domains": ["boardgamegeek.com"],
        "low_trust_domains": [],
        "system_prompt": "x",
        "research_prompt": "x",
    }


def test_dynamic_publisher_page_outranks_wikipedia():
    import app.research_search as mod
    importlib.reload(mod)
    current = {"title": "Scythe"}
    wiki = mod.classify_fetched_page(
        {"url": "https://de.wikipedia.org/wiki/Scythe", "title": "Scythe - Wikipedia", "score": 29, "trust": "normal"},
        {"title": "Scythe", "publisher": "", "source_url": "https://de.wikipedia.org/wiki/Scythe"},
        {"page_title": "Scythe – Wikipedia", "jsonld_product": {}},
        "Scythe ist ein Brettspiel von Jamey Stegmaier.",
        current,
        _settings(),
    )
    publisher = mod.classify_fetched_page(
        {"url": "https://www.feuerland-spiele.de/spiele/scythe/", "title": "Scythe - Feuerland Spiele", "score": 23, "trust": "normal"},
        {
            "title": "Scythe", "publisher": "", "source_url": "https://www.feuerland-spiele.de/spiele/scythe/",
            "min_players": 1, "max_players": 5, "play_time_min": 120, "min_age": 14,
            "designer": "Jamey Stegmaier", "rules_url": "https://www.feuerland-spiele.de/scythe-regel.pdf",
        },
        {"page_title": "Scythe - Feuerland Spiele", "jsonld_product": {}},
        "Scythe ab 14, 1-5 Spieler, 120 Minuten. Autor Jamey Stegmaier. Downloads Spielregel. Feuerland Verlagsgesellschaft mbH.",
        current,
        _settings(),
    )
    assert publisher["source_class"] == "official"
    assert publisher["post_fetch_score"] > wiki["post_fetch_score"]
    assert wiki["source_class"] == "reference"


def test_research_fetches_extra_candidates_then_uses_best_pages(monkeypatch):
    os.environ["AUTO_SEARCH_PROVIDER"] = "searxng"
    os.environ["SEARXNG_BASE_URL"] = "http://searxng:8080"
    os.environ["AUTO_FETCH_PAGES"] = "2"
    import app.research_search as mod
    importlib.reload(mod)
    monkeypatch.setattr(mod, "get_settings", _settings)
    monkeypatch.setattr(mod, "identify_bgg", lambda *a, **k: None)
    candidates = [
        {"title": "Scythe - Wikipedia", "url": "https://de.wikipedia.org/wiki/Scythe", "trust": "normal", "score": 29, "reasons": ["Titel 88%"]},
        {"title": "Scythe Test", "url": "https://example.org/scythe-test", "trust": "normal", "score": 27, "reasons": ["Titel 70%"]},
        {"title": "Scythe - Feuerland Spiele", "url": "https://www.feuerland-spiele.de/spiele/scythe/", "trust": "normal", "score": 23, "reasons": ["Titel 76%"]},
    ]
    monkeypatch.setattr(mod, "search", lambda *a, **k: (candidates, []))

    def fake_extract(url):
        if "wikipedia" in url:
            return ({"title": "Scythe", "source_url": url}, "Scythe ist ein Brettspiel.", {"page_title": "Scythe – Wikipedia", "jsonld_product": {}}, [])
        if "example.org" in url:
            return ({"title": "Scythe Test", "source_url": url}, "Scythe Test Rezension Fazit Bewertung.", {"page_title": "Scythe Test Rezension", "jsonld_product": {}}, [])
        return ({"title": "Scythe", "source_url": url, "min_players": 1, "max_players": 5, "play_time_min": 120, "min_age": 14, "rules_url": "https://www.feuerland-spiele.de/regeln.pdf"}, "Scythe 1-5 Spieler, ab 14, 120 Minuten. Feuerland Verlagsgesellschaft mbH. Spielregel Download.", {"page_title": "Scythe - Feuerland Spiele", "jsonld_product": {}}, [])

    monkeypatch.setattr(mod, "extract_page", fake_extract)
    out = mod.research_game("Scythe", {"title": "Scythe"})
    assert out["sources"][0].startswith("https://www.feuerland-spiele.de/")
    assert "https://de.wikipedia.org/wiki/Scythe" in out["sources"]
    assert "https://example.org/scythe-test" not in out["sources"]
    assert out["research"]["selected"][0]["source_class"] == "official"
    assert out["research"]["pages_fetched"] == 3
    assert out["research"]["pages_used"] == 2

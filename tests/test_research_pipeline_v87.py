import importlib
import json
import os


def setup_module_env():
    os.environ["AUTO_SEARCH_PROVIDER"] = "searxng"
    os.environ["SEARXNG_BASE_URL"] = "http://searxng:8080"


def test_candidate_scoring_penalizes_reviews_and_expansions(monkeypatch):
    setup_module_env()
    import app.research_search as mod
    importlib.reload(mod)
    monkeypatch.setattr(mod, "source_trust", lambda url, settings=None: "normal")
    clean = mod.score_candidate({"title":"Cascadia Brettspiel", "content":"", "url":"https://example.com/cascadia"}, "Cascadia", {"title":"Cascadia"}, {})
    review = mod.score_candidate({"title":"Cascadia Review Testbericht", "content":"", "url":"https://example.com/blog/cascadia-review"}, "Cascadia", {"title":"Cascadia"}, {})
    expansion = mod.score_candidate({"title":"Cascadia Erweiterung", "content":"", "url":"https://example.com/cascadia-erweiterung"}, "Cascadia", {"title":"Cascadia"}, {})
    assert clean["score"] > review["score"]
    assert clean["score"] > expansion["score"]


def test_research_bundle_excludes_search_snippets(monkeypatch):
    setup_module_env()
    import app.research_search as mod
    importlib.reload(mod)
    candidates = [
        {"title":"Cascadia – KOSMOS", "content":"BAD SEARCH SNIPPET SHOULD NOT REACH AI", "url":"https://kosmos.de/cascadia", "trust":"primary", "score":85, "reasons":["Primärquelle"]},
        {"title":"Cascadia Test", "content":"BAD REVIEW SNIPPET", "url":"https://spieletest.at/cascadia", "trust":"low", "score":5, "reasons":["Review/Test"]},
    ]
    monkeypatch.setattr(mod, "search", lambda q, current_game=None: candidates)
    monkeypatch.setattr(mod, "identify_bgg", lambda q, current_game=None: {"score":96,"matched_name":"Cascadia","data":{"bgg_id":199792,"name":"Cascadia","alternate_names":[],"year":2021,"min_players":1,"max_players":4,"play_time_min":45,"min_age":10,"designers":["Randy Flynn"],"publishers":[],"mechanics":["Tile Placement"],"categories":[],"families":[],"description":"English structured description","image":"","thumbnail":"","expansion_of":[],"url":"https://boardgamegeek.com/boardgame/199792"}})
    monkeypatch.setattr(mod, "extract_page", lambda url: ({"title":"Cascadia","publisher":"KOSMOS"}, "Direkt abgerufener Seitentext", {"page_title":"Cascadia","meta_description":"","jsonld_product":{}}, []))
    out = mod.research_game("Cascadia", {"title":"Cascadia"})
    assert "BAD SEARCH SNIPPET" not in out["evidence"]
    assert "Direkt abgerufener Seitentext" in out["evidence"]
    assert len(out["sources"]) == 2
    payload = json.loads(out["evidence"])
    assert payload["pipeline"] == "v8.8-postfetch-ranked-field-evidence"
    assert payload["sources"][0]["kind"] == "bgg_structured"
    assert out["research"]["identity"]["bgg_id"] == 199792
    assert out["research"]["ignored"][0]["trust"] == "low"

import importlib
import os


def _env():
    os.environ["AUTO_SEARCH_PROVIDER"] = "searxng"
    os.environ["SEARXNG_BASE_URL"] = "http://searxng:8080"
    os.environ["AUTO_FETCH_PAGES"] = "2"


def test_search_retries_simple_multilingual_query(monkeypatch):
    _env()
    import app.research_search as mod
    importlib.reload(mod)
    calls=[]
    def fake(query, limit=None, *, language="de", safesearch=0, include_meta=False):
        calls.append((query, language, safesearch))
        rows=[]
        if language == "all" and query == "Scythe":
            rows=[{"url":"https://stonemaiergames.com/games/scythe/","title":"Scythe","content":"board game","engine":"duckduckgo"}]
        meta={"query":query,"language":language,"raw_results":len(rows),"accepted_https":len(rows),"rejected":{},"unresponsive_engines":[]}
        return (rows, meta) if include_meta else rows
    monkeypatch.setattr(mod, "searxng_search", fake)
    monkeypatch.setattr(mod, "validate_public_https_url", lambda u: u)
    rows, diag = mod.search("Scythe", {"title":"Scythe"}, return_diagnostics=True)
    assert rows and rows[0]["url"].startswith("https://stonemaiergames.com/")
    assert any(lang == "all" and q == "Scythe" for q, lang, _ in calls)
    assert diag[-1].get("fallback") == "language=all"


def test_structured_bgg_can_continue_when_searxng_fails(monkeypatch):
    _env()
    import app.research_search as mod
    importlib.reload(mod)
    identity={"score":99,"matched_name":"Scythe","data":{"bgg_id":169786,"name":"Scythe","alternate_names":[],"year":2016,"min_players":1,"max_players":5,"play_time_min":115,"min_age":14,"designers":["Jamey Stegmaier"],"publishers":["Stonemaier Games"],"mechanics":[],"categories":[],"families":[],"description":"","image":"","thumbnail":"","expansion_of":[],"url":"https://boardgamegeek.com/boardgame/169786"}}
    monkeypatch.setattr(mod, "identify_bgg", lambda *a, **k: identity)
    monkeypatch.setattr(mod, "search", lambda *a, **k: (_ for _ in ()).throw(mod.ResearchSearchError("SearXNG down")))
    out=mod.research_game("Scythe", {"title":"Scythe"})
    assert out["pages_fetched"] == 0
    assert out["sources"] == ["https://boardgamegeek.com/boardgame/169786"]
    assert out["research"]["identity"]["bgg_id"] == 169786



def test_empty_search_diagnostics_capture_engine_failures(monkeypatch):
    _env()
    import app.research_search as mod
    importlib.reload(mod)
    class Response:
        status_code=200
        def json(self):
            return {"results":[], "unresponsive_engines":[["google", "timeout"], ["bing", "429"]]}
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: Response())
    rows, meta=mod.searxng_search("Scythe", include_meta=True)
    assert rows == []
    assert meta["raw_results"] == 0
    assert meta["unresponsive_engines"][0][0] == "google"


def test_weak_german_results_trigger_multilingual_fallback(monkeypatch):
    _env()
    import app.research_search as mod
    importlib.reload(mod)
    calls=[]
    def fake(query, limit=None, *, language="de", safesearch=0, include_meta=False):
        calls.append((query, language))
        if language == "de":
            rows=[{"url":"https://reviews.example/random","title":"Unrelated Review","content":"","engine":"x"}]
        else:
            rows=[{"url":"https://stonemaiergames.com/games/scythe/","title":"Scythe","content":"board game","engine":"x"}]
        meta={"query":query,"language":language,"raw_results":len(rows),"accepted_https":len(rows),"rejected":{},"unresponsive_engines":[]}
        return (rows, meta) if include_meta else rows
    monkeypatch.setattr(mod, "searxng_search", fake)
    monkeypatch.setattr(mod, "source_trust", lambda url, settings=None: "primary" if "stonemaier" in url else "low")
    rows, diag = mod.search("Scythe", {"title":"Scythe"}, return_diagnostics=True)
    assert any(lang == "all" for _, lang in calls)
    assert rows[0]["url"].startswith("https://stonemaiergames.com/")
    assert any(d.get("phase") == "multilingual" for d in diag)


def test_http_search_result_is_upgraded_but_never_fetched_as_http(monkeypatch):
    _env()
    import app.research_search as mod
    importlib.reload(mod)
    class Response:
        status_code=200
        def json(self):
            return {"results":[{"url":"http://example.com/scythe","title":"Scythe","content":""}]}
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: Response())
    monkeypatch.setattr(mod, "validate_public_https_url", lambda u: u if u.startswith("https://") else (_ for _ in ()).throw(ValueError("https only")))
    rows, meta = mod.searxng_search("Scythe", include_meta=True)
    assert rows[0]["url"] == "https://example.com/scythe"
    assert meta["http_upgraded"] == 1

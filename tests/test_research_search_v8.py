import importlib
import os


def test_searxng_search_filters_non_https(monkeypatch):
    os.environ["AUTO_SEARCH_PROVIDER"] = "searxng"
    os.environ["SEARXNG_BASE_URL"] = "http://searxng:8080"
    import app.research_search as mod
    importlib.reload(mod)

    class Response:
        status_code = 200
        def json(self):
            return {"results": [
                {"url": "https://example.com/game", "title": "Game", "content": "ok"},
                {"url": "http://example.com/insecure", "title": "No", "content": "skip"},
            ]}

    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: Response())
    monkeypatch.setattr(mod, "validate_public_https_url", lambda u: u if u.startswith("https://") else (_ for _ in ()).throw(ValueError("no")))
    rows = mod.searxng_search("Sky Team")
    assert [x["url"] for x in rows] == ["https://example.com/game"]


def test_searxng_json_403_has_helpful_error(monkeypatch):
    os.environ["AUTO_SEARCH_PROVIDER"] = "searxng"
    os.environ["SEARXNG_BASE_URL"] = "http://searxng:8080"
    import app.research_search as mod
    importlib.reload(mod)

    class Response:
        status_code = 403
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: Response())
    try:
        mod.searxng_search("Cascadia")
        assert False
    except mod.ResearchSearchError as exc:
        assert "search.formats" in str(exc)

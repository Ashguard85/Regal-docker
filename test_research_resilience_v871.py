import importlib
import os


def _env():
    os.environ["AUTO_SEARCH_PROVIDER"] = "searxng"
    os.environ["SEARXNG_BASE_URL"] = "http://searxng:8080"
    os.environ["AUTO_FETCH_PAGES"] = "2"


def test_public_bgg_page_is_allowed_when_structured_bgg_unavailable(monkeypatch):
    _env()
    import app.research_search as mod
    importlib.reload(mod)
    candidates = [
        {"title":"Scythe | Board Game | BoardGameGeek", "content":"", "url":"https://boardgamegeek.com/boardgame/169786/scythe", "trust":"reference", "score":86, "reasons":["BGG-Spielseite"]},
    ]
    monkeypatch.setattr(mod, "search", lambda *a, **k: candidates)
    monkeypatch.setattr(mod, "identify_bgg", lambda *a, **k: (_ for _ in ()).throw(mod.BGGError("BGG_API_TOKEN fehlt")))
    monkeypatch.setattr(mod, "extract_page", lambda url: ({"title":"Scythe","designer":"Jamey Stegmaier"}, "Scythe board game", {"page_title":"Scythe","meta_description":"","jsonld_product":{}}, []))
    out = mod.research_game("Scythe", {"title":"Scythe"})
    assert out["pages_fetched"] == 1
    assert out["sources"][0].startswith("https://boardgamegeek.com/boardgame/169786")


def test_fetch_tries_next_candidate_after_blocked_page(monkeypatch):
    _env()
    import app.research_search as mod
    importlib.reload(mod)
    candidates = [
        {"title":"Scythe official", "content":"", "url":"https://publisher.example/scythe", "trust":"primary", "score":95, "reasons":["Primärquelle"]},
        {"title":"Scythe – Das Brettspiel", "content":"", "url":"https://de.wikipedia.org/wiki/Scythe", "trust":"normal", "score":50, "reasons":["Titel 100%"]},
        {"title":"Scythe details", "content":"", "url":"https://reference.example/scythe", "trust":"reference", "score":45, "reasons":["Referenzquelle"]},
    ]
    monkeypatch.setattr(mod, "search", lambda *a, **k: candidates)
    monkeypatch.setattr(mod, "identify_bgg", lambda *a, **k: None)
    def extract(url):
        if "publisher.example" in url:
            raise RuntimeError("HTTP 403")
        return ({"title":"Scythe"}, "usable page", {"page_title":"Scythe","meta_description":"","jsonld_product":{}}, [])
    monkeypatch.setattr(mod, "extract_page", extract)
    out = mod.research_game("Scythe", {"title":"Scythe"})
    assert out["pages_fetched"] == 2
    assert all("publisher.example" not in u for u in out["sources"])
    assert out["research"]["fetch_failures"] == 1


def test_structured_bgg_keeps_public_bgg_html_out_of_fetch_queue(monkeypatch):
    _env()
    import app.research_search as mod
    importlib.reload(mod)
    identity={"score":99,"matched_name":"Scythe","data":{"bgg_id":169786,"name":"Scythe","alternate_names":[],"year":2016,"min_players":1,"max_players":5,"play_time_min":115,"min_age":14,"designers":["Jamey Stegmaier"],"publishers":["Stonemaier Games"],"mechanics":[],"categories":[],"families":[],"description":"","image":"","thumbnail":"","expansion_of":[],"url":"https://boardgamegeek.com/boardgame/169786"}}
    candidates = [
        {"title":"Scythe | BoardGameGeek", "content":"", "url":"https://boardgamegeek.com/boardgame/169786/scythe", "trust":"reference", "score":86, "reasons":["BGG-Spielseite"]},
        {"title":"Scythe publisher", "content":"", "url":"https://publisher.example/scythe", "trust":"primary", "score":90, "reasons":["Primärquelle"]},
    ]
    monkeypatch.setattr(mod, "search", lambda *a, **k: candidates)
    monkeypatch.setattr(mod, "identify_bgg", lambda *a, **k: identity)
    seen=[]
    monkeypatch.setattr(mod, "extract_page", lambda url: (seen.append(url) or ({"title":"Scythe"}, "publisher page", {"page_title":"Scythe","meta_description":"","jsonld_product":{}}, [])))
    out=mod.research_game("Scythe", {"title":"Scythe"})
    assert seen == ["https://publisher.example/scythe"]
    assert out["sources"][0] == "https://boardgamegeek.com/boardgame/169786"

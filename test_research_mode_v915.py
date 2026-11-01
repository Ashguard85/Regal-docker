import importlib
import json
import os
import tempfile


def _bgg_record():
    return {"score": 98, "matched_name": "Scythe", "data": {
        "bgg_id":169786, "name":"Scythe", "url":"https://boardgamegeek.com/boardgame/169786",
        "year":2016,"min_players":1,"max_players":5,"play_time_min":115,
        "designers":["Jamey Stegmaier"], "publishers":["Stonemaier Games"],
        "description":"Engine building", "image":"https://images.example/scythe.jpg",
        "mechanics":["Area Majority / Influence"], "categories":[]}}


def test_policy_title_link_ean_and_manual_refresh():
    from app.research_policy import choose_mode
    cfg={"initial_bgg_only": True}
    assert choose_mode({"search_scope":"initial","query":"Scythe"},{"title":"Scythe"},cfg)=="bgg_only"
    assert choose_mode({"search_scope":"full","query":"Scythe"},{"title":"Scythe"},cfg)=="full"
    assert choose_mode({"search_scope":"initial","query":"4002051697860"},{"title":"EAN 4002051697860"},cfg)=="full"
    assert choose_mode({"search_scope":"initial","query":"Scythe"},{"title":"Scythe","source_url":"https://publisher.example/scythe"},cfg)=="full"
    assert choose_mode({"search_scope":"initial","query":"Scythe"},{"title":"Scythe"},{"initial_bgg_only":False})=="full"


def test_bgg_only_research_never_calls_web_search_or_page_fetch(monkeypatch):
    import app.research_search as mod
    monkeypatch.setattr(mod,"identify_bgg",lambda *a,**kw:_bgg_record())
    monkeypatch.setattr(mod,"search",lambda *a,**kw: (_ for _ in ()).throw(AssertionError("SearXNG called")))
    monkeypatch.setattr(mod,"extract_page",lambda *a,**kw: (_ for _ in ()).throw(AssertionError("Website fetched")))
    result=mod.research_game("Scythe",{"title":"Scythe"},mode="bgg_only")
    assert result["research"]["mode"]=="bgg_only"
    assert result["pages_fetched"]==0
    assert result["sources"]==["https://boardgamegeek.com/boardgame/169786"]
    assert result["_field_source_bundles"][0]["data"]["bgg_id"]==169786
    assert "Nur strukturierte BGG-API-Daten" in json.loads(result["evidence"])["important"]


def test_bgg_no_match_requires_explicit_full_research(monkeypatch):
    import app.research_search as mod
    monkeypatch.setattr(mod,"identify_bgg",lambda *a,**kw:None)
    monkeypatch.setattr(mod,"search",lambda *a,**kw: (_ for _ in ()).throw(AssertionError("SearXNG should not run")))
    try:
        mod.research_game("Unbekannt",{"title":"Unbekannt"},mode="bgg_only")
        assert False, "expected explicit failure"
    except mod.ResearchSearchError as exc:
        assert "Neu recherchieren" in str(exc)


def test_direct_link_survives_searxng_outage_and_is_first(monkeypatch):
    import app.research_search as mod
    monkeypatch.setattr(mod,"identify_bgg",lambda *a,**kw:None)
    monkeypatch.setattr(mod,"search",lambda *a,**kw: (_ for _ in ()).throw(mod.ResearchSearchError("SearXNG down")))
    def fake_fetch(url):
        assert url=="https://publisher.example/scythe"
        return {"source_url":url,"title":"Scythe","publisher":"Example"}, "Scythe Brettspiel Verlag", {}, []
    monkeypatch.setattr(mod,"extract_page",fake_fetch)
    result=mod.research_game("Scythe",{"title":"Scythe","source_url":"https://publisher.example/scythe"})
    assert result["sources"][0]=="https://publisher.example/scythe"
    assert result["research"]["mode"]=="full"
    assert result["pages_fetched"]==1


def test_setting_and_job_scope_persist_non_destructively():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DATA_DIR"]=tmp
        import app.db as db
        importlib.reload(db)
        db.init_db()
        import app.research_config as cfg
        importlib.reload(cfg)
        assert cfg.get_settings()["initial_bgg_only"] is True
        cfg.save_settings({"initial_bgg_only":False})
        assert cfg.get_settings()["initial_bgg_only"] is False
        cfg.save_settings({"initial_bgg_only":True})
        db.save_game(db.normalize_game({"id":"g1","title":"Scythe"}))
        first=db.enqueue_import_job("g1","Scythe",search_scope="initial")
        assert first["search_scope"]=="initial"
        second=db.enqueue_import_job("g1","Scythe",replace_active=True,search_scope="full")
        assert second["search_scope"]=="full"
        db.init_db()
        assert db.get_game("g1")["title"]=="Scythe"
        assert db.get_import_job(second["id"])["search_scope"]=="full"


def test_ui_offers_manual_full_fallback_and_checkbox():
    from pathlib import Path
    base=Path(__file__).resolve().parents[1]
    html=(base/"frontend"/"index.html").read_text()
    js=(base/"frontend"/"app.js").read_text()
    assert 'id="initialBggOnlyInput"' in html
    assert 'initial_bgg_only:$("initialBggOnlyInput").checked' in js
    assert 'data-full-research' in js
    assert 'Weitere Quellen durchsuchen' in js

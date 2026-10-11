import importlib
import os
import tempfile


def load_app(tmp):
    os.environ["DATA_DIR"] = tmp
    os.environ["PWA_ALLOWED_ORIGIN"] = "https://app.example.com"
    os.environ["AI_IMPORT_ENABLED"] = "false"
    os.environ["AI_PROVIDER"] = "none"
    os.environ["RULE_SEARCH_PROVIDER"] = "none"
    os.environ["WEB_FALLBACK_PROVIDER"] = "none"
    import app.db as db
    import app.app as appmod
    importlib.reload(db)
    importlib.reload(appmod)
    return appmod.create_app({"TESTING": True})


def test_health_config_and_crud():
    with tempfile.TemporaryDirectory() as tmp:
        app = load_app(tmp)
        c = app.test_client()
        assert c.get("/health").json == {"status": "ok"}
        cfg = c.get("/api/config").json
        assert cfg["version"] == "7.0.0"
        assert cfg["ai_provider"] == "none"
        assert cfg["ai_import_enabled"] is False
        created = c.post("/api/games", json={
            "title": "Sky Team", "tags": ["Koop"], "designer": "Luc Rémond",
            "ean": "4002051684044", "award": "Spiel des Jahres 2024"
        })
        assert created.status_code == 201
        game = created.json
        assert game["designer"] == "Luc Rémond"
        assert game["ean"] == "4002051684044"
        listed = c.get("/api/games").json
        assert len(listed) == 1
        updated = c.put(f"/api/games/{game['id']}", json={"title": "Sky Team", "min_players": 2, "max_players": 2})
        assert updated.status_code == 200
        assert updated.json["min_players"] == 2
        assert c.delete(f"/api/games/{game['id']}").status_code == 200
        assert c.get("/api/games").json == []


def test_backup_import_and_cors():
    with tempfile.TemporaryDirectory() as tmp:
        app = load_app(tmp)
        c = app.test_client()
        c.post("/api/games", json={"title": "Azul"})
        backup = c.get("/api/export").json
        assert backup["format"] == "brettspielregal-backup"
        assert backup["version"] == 3
        preview = c.post("/api/import/preview", json={"backup": backup})
        assert preview.status_code == 200
        preflight = c.options("/api/games", headers={"Origin":"https://app.example.com","Access-Control-Request-Method":"GET"})
        assert preflight.headers["Access-Control-Allow-Origin"] == "https://app.example.com"
        denied = c.options("/api/games", headers={"Origin":"https://evil.example","Access-Control-Request-Method":"GET"})
        assert "Access-Control-Allow-Origin" not in denied.headers


def test_ai_endpoints_are_disabled_by_default():
    with tempfile.TemporaryDirectory() as tmp:
        app = load_app(tmp)
        c = app.test_client()
        assert c.post("/api/ai/from-url", json={"url":"https://example.com"}).status_code == 503
        assert c.post("/api/ai/from-text", json={"text":"Titel: Azul"}).status_code == 503
        assert c.post("/api/ai/from-image").status_code == 503
        assert c.post("/api/ai/rules-search", json={"game":{"title":"Azul"}}).status_code == 503

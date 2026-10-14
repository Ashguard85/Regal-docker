import importlib
import os
import tempfile


def load_app(tmp):
    os.environ["DATA_DIR"] = tmp
    os.environ.pop("PWA_ALLOWED_ORIGIN", None)
    os.environ["PWA_ALLOWED_ORIGINS"] = "https://app.example.com,https://second.example.com"
    os.environ["AI_IMPORT_ENABLED"] = "false"
    os.environ["AI_PROVIDER"] = "none"
    os.environ["RULE_SEARCH_PROVIDER"] = "none"
    os.environ["WEB_FALLBACK_PROVIDER"] = "none"
    os.environ["AUTO_SEARCH_PROVIDER"] = "none"
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
        system = c.get("/api/system/status", headers={"Origin":"https://app.example.com"})
        assert system.status_code == 200
        assert system.json["api"]["status"] == "ok"
        assert system.json["cors"]["allowed"] is True
        assert system.json["search"]["status"] == "disabled"
        cfg = c.get("/api/config").json
        assert cfg["version"] == "8.8.0"
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
        assert backup["version"] == 4
        preview = c.post("/api/import/preview", json={"backup": backup})
        assert preview.status_code == 200
        preflight = c.options("/api/games", headers={"Origin":"https://app.example.com","Access-Control-Request-Method":"GET"})
        assert preflight.headers["Access-Control-Allow-Origin"] == "https://app.example.com"
        second = c.options("/api/games", headers={"Origin":"https://second.example.com","Access-Control-Request-Method":"GET"})
        assert second.headers["Access-Control-Allow-Origin"] == "https://second.example.com"
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


def test_quick_capture_creates_persistent_queue_jobs():
    with tempfile.TemporaryDirectory() as tmp:
        app = load_app(tmp)
        os.environ["AI_IMPORT_ENABLED"] = "true"
        os.environ["AUTO_ENRICH_ENABLED"] = "true"
        c = app.test_client()
        result = c.post("/api/import-queue/quick", json={"text": "Sky Team\n4002051698973", "storage_location":"1. Tablar"})
        assert result.status_code == 201
        assert result.json["count"] == 2
        queue = c.get("/api/import-queue").json
        assert len(queue["jobs"]) == 2
        assert {j["status"] for j in queue["jobs"]} == {"queued"}
        games = c.get("/api/games").json
        assert len(games) == 2
        assert any(g["ean"] == "4002051698973" for g in games)
        assert all(g["storage_location"] == "1. Tablar" for g in games)


def test_review_job_can_be_approved_via_api():
    with tempfile.TemporaryDirectory() as tmp:
        app = load_app(tmp)
        import app.db as db
        c = app.test_client()
        created = c.post('/api/games', json={'title':'Brändi Dog'}).json
        job = db.enqueue_import_job(created['id'], 'Brändi Dog')
        proposed=db.normalize_game({**created,'publisher':'Brändi'},created)
        db.replace_import_suggestions(job['id'],created['id'],proposed,created)
        db.update_import_job(job['id'], status='review', progress='1 Vorschlag bereit', warnings=['Bitte prüfen'], finished=True)
        approved = c.post(f"/api/import-queue/{job['id']}/suggestions/apply", json={"fields":["publisher"]})
        assert approved.status_code == 200
        assert approved.json['applied'] == ['publisher']
        assert c.get(f"/api/games/{created['id']}").json['publisher'] == 'Brändi'
        assert db.get_import_job(job['id'])['status'] == 'verified'

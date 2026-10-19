import importlib
import os
import tempfile


def setup(tmp):
    os.environ["DATA_DIR"] = tmp
    os.environ["AI_IMPORT_ENABLED"] = "true"
    os.environ["AUTO_ENRICH_ENABLED"] = "true"
    import app.db as db
    importlib.reload(db)
    db.init_db()
    import app.import_worker as worker
    importlib.reload(worker)
    return db, worker


def test_worker_processes_job_and_stages_suggestions(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db, worker = setup(tmp)
        game = db.normalize_game({"id": "g1", "title": "Sky Team"})
        db.save_game(game)
        job = db.enqueue_import_job("g1", "Sky Team")
        job = db.claim_import_job()

        monkeypatch.setattr(worker, "research_game", lambda q, game=None: {
            "sources": ["https://example.com/sky-team"],
            "evidence": "Sky Team; 2 Spieler; 20 Minuten; Verlag Beispiel",
        })
        monkeypatch.setattr(worker, "import_from_research", lambda q, game, evidence, sources: {
            "game": {**game, "description": "Kooperatives Spiel", "publisher": "Beispiel", "min_players": 2, "max_players": 2, "play_time_min": 20},
            "warnings": [],
        })

        worker.process_job(job)
        updated = db.get_game("g1")
        final = db.get_import_job(job["id"])
        assert updated["publisher"] == ""
        assert updated["play_time_min"] is None
        assert final["status"] == "review"
        assert final["sources"] == ["https://example.com/sky-team"]
        pending={x["field"]:x["value"] for x in final["suggestions"] if x["status"]=="pending"}
        assert pending["publisher"] == "Beispiel"
        assert pending["play_time_min"] == 20
        applied=db.apply_import_suggestions(job["id"],["publisher"])
        assert applied["applied"] == ["publisher"]
        assert db.get_game("g1")["publisher"] == "Beispiel"
        assert db.get_game("g1")["play_time_min"] is None


def test_worker_stops_after_cancel_requested_during_research(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db, worker = setup(tmp)
        game = db.normalize_game({"id": "g1", "title": "Skull Queen"})
        db.save_game(game)
        job = db.enqueue_import_job("g1", "Skull Queen")
        job = db.claim_import_job()
        called = {"ai": False}

        def fake_research(query, game=None):
            db.request_cancel_import_job(job["id"])
            return {"sources": ["https://example.com/skull"], "evidence": "Daten"}

        def fake_ai(*args, **kwargs):
            called["ai"] = True
            return {"game": game, "warnings": []}

        monkeypatch.setattr(worker, "research_game", fake_research)
        monkeypatch.setattr(worker, "import_from_research", fake_ai)
        worker.process_job(job)

        final = db.get_import_job(job["id"])
        assert final["status"] == "cancelled"
        assert called["ai"] is False

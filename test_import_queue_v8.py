import importlib
import os
import tempfile


def load_db(tmp):
    os.environ["DATA_DIR"] = tmp
    import app.db as db
    importlib.reload(db)
    db.init_db()
    return db


def test_queue_persists_and_claims_one_at_a_time():
    with tempfile.TemporaryDirectory() as tmp:
        db = load_db(tmp)
        game = db.normalize_game({"id": "g1", "title": "Sky Team", "ean": "12345678"})
        db.save_game(game)
        job = db.enqueue_import_job("g1", "Sky Team")
        assert job["status"] == "queued"
        claimed = db.claim_import_job()
        assert claimed["id"] == job["id"]
        assert claimed["status"] == "running"
        assert claimed["attempts"] == 1
        assert db.claim_import_job() is None
        db.update_import_job(job["id"], status="done", progress="Fertig", sources=["https://example.com"], finished=True)
        final = db.get_import_job(job["id"])
        assert final["status"] == "done"
        assert final["sources"] == ["https://example.com"]


def test_duplicate_active_job_is_reused():
    with tempfile.TemporaryDirectory() as tmp:
        db = load_db(tmp)
        game = db.normalize_game({"id": "g1", "title": "Cascadia"})
        db.save_game(game)
        first = db.enqueue_import_job("g1", "Cascadia")
        second = db.enqueue_import_job("g1", "Cascadia")
        assert first["id"] == second["id"]


def test_find_game_for_quick_capture():
    with tempfile.TemporaryDirectory() as tmp:
        db = load_db(tmp)
        game = db.normalize_game({"id": "g1", "title": "Dorfromantik", "ean": "4000000000001"})
        db.save_game(game)
        assert db.find_game_by_ean("4000 0000 0000 1")["id"] == "g1"
        assert db.find_game_by_title("dorfromantik")["id"] == "g1"


def test_review_job_can_be_approved():
    with tempfile.TemporaryDirectory() as tmp:
        db = load_db(tmp)
        game = db.normalize_game({"id": "g1", "title": "Brändi Dog"})
        db.save_game(game)
        job = db.enqueue_import_job("g1", "Brändi Dog")
        db.update_import_job(job["id"], status="review", progress="Bitte prüfen", warnings=["Cover unsicher"], finished=True)
        approved = db.approve_import_job(job["id"])
        assert approved["status"] == "verified"
        assert approved["progress"] == "Vorschläge geprüft"
        assert approved["warnings"] == ["Cover unsicher"]


def test_only_review_job_can_be_approved():
    with tempfile.TemporaryDirectory() as tmp:
        db = load_db(tmp)
        game = db.normalize_game({"id": "g1", "title": "Sky Team"})
        db.save_game(game)
        job = db.enqueue_import_job("g1", "Sky Team")
        try:
            db.approve_import_job(job["id"])
            assert False, "queued job must not be approved"
        except ValueError:
            pass


def test_cleanup_import_jobs_keeps_running_and_can_remove_reviews():
    with tempfile.TemporaryDirectory() as tmp:
        db = load_db(tmp)
        for idx, title in enumerate(["Running", "Failed", "Review", "Queued"], 1):
            db.save_game(db.normalize_game({"id": f"g{idx}", "title": title}))
        running = db.enqueue_import_job("g1", "Running")
        db.claim_import_job()
        failed = db.enqueue_import_job("g2", "Failed")
        db.update_import_job(failed["id"], status="failed", progress="Fehler", finished=True)
        review = db.enqueue_import_job("g3", "Review")
        db.update_import_job(review["id"], status="review", progress="Prüfen", finished=True)
        db.replace_import_suggestions(review["id"], "g3", {"title":"Review", "description":"Vorschlag"}, db.get_game("g3"))
        queued = db.enqueue_import_job("g4", "Queued")

        result = db.cleanup_import_jobs("history")
        assert result["deleted"] == 1
        assert db.get_import_job(running["id"])["status"] == "running"
        assert db.get_import_job(review["id"])["status"] == "review"
        assert db.get_import_job(queued["id"])["status"] == "queued"

        result = db.cleanup_import_jobs("including_review")
        assert result["deleted"] == 1
        assert db.get_import_job(review["id"]) is None
        assert db.list_import_suggestions(review["id"]) == []

        result = db.cleanup_import_jobs("all_non_running")
        assert result["deleted"] == 1
        assert result["running_protected"] == 1
        assert db.get_import_job(running["id"])["status"] == "running"


def test_running_job_can_request_cancel_and_late_worker_update_is_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        db = load_db(tmp)
        db.save_game(db.normalize_game({"id": "g1", "title": "Skull Queen"}))
        job = db.enqueue_import_job("g1", "Skull Queen")
        running = db.claim_import_job()
        assert running["status"] == "running"

        requested = db.request_cancel_import_job(job["id"])
        assert requested["status"] == "running"
        assert requested["cancel_requested"] is True
        assert requested["cancel_requested_at"]

        # A late worker response must not resurrect or mutate a cancelling job.
        late = db.update_import_job(job["id"], status="review", progress="Zu spät", finished=True)
        assert late["status"] == "running"
        assert late["cancel_requested"] is True
        assert late["progress"].startswith("Abbruch angefordert")

        final = db.finalize_cancel_import_job(job["id"])
        assert final["status"] == "cancelled"
        assert final["cancel_requested"] is True


def test_force_release_running_job_discards_temporary_suggestions():
    with tempfile.TemporaryDirectory() as tmp:
        db = load_db(tmp)
        db.save_game(db.normalize_game({"id": "g1", "title": "Patchwork"}))
        job = db.enqueue_import_job("g1", "Patchwork")
        db.claim_import_job()
        assert db.replace_import_suggestions(
            job["id"], "g1", {"title": "Patchwork", "description": "Vorschlag"}, db.get_game("g1")
        ) == 1
        assert db.list_import_suggestions(job["id"])

        released = db.force_release_import_job(job["id"])
        assert released["status"] == "cancelled"
        assert released["progress"] == "Hängender Auftrag freigegeben"
        assert db.list_import_suggestions(job["id"]) == []


def test_queued_job_is_cancelled_immediately():
    with tempfile.TemporaryDirectory() as tmp:
        db = load_db(tmp)
        db.save_game(db.normalize_game({"id": "g1", "title": "Flip 7"}))
        job = db.enqueue_import_job("g1", "Flip 7")
        cancelled = db.request_cancel_import_job(job["id"])
        assert cancelled["status"] == "cancelled"
        assert cancelled["cancel_requested"] is True
        assert db.claim_import_job() is None

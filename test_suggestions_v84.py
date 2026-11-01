import importlib
import os
import tempfile


def setup(tmp):
    os.environ["DATA_DIR"] = tmp
    import app.db as db
    importlib.reload(db)
    db.init_db()
    return db


def test_storage_location_roundtrip_and_backup():
    with tempfile.TemporaryDirectory() as tmp:
        db=setup(tmp)
        game=db.normalize_game({"id":"g1","title":"Cascadia","storage_location":"1. Tablar"})
        db.save_game(game)
        assert db.get_game("g1")["storage_location"] == "1. Tablar"
        backup=db.backup_payload()
        assert backup["version"] == 5
        assert backup["data"]["games"][0]["storage_location"] == "1. Tablar"


def test_suggestions_do_not_touch_game_until_explicit_apply():
    with tempfile.TemporaryDirectory() as tmp:
        db=setup(tmp)
        game=db.normalize_game({"id":"g1","title":"Looping Chewie","storage_location":"2. Tablar"})
        db.save_game(game)
        job=db.enqueue_import_job("g1","Looping Chewie")
        proposed=db.normalize_game({**game,"publisher":"Hasbro","year":2015,"tags":["Geschicklichkeit"]},game)
        count=db.replace_import_suggestions(job["id"],"g1",proposed,game)
        assert count >= 3
        assert db.get_game("g1")["publisher"] == ""
        db.update_import_job(job["id"],status="review",progress="Vorschläge bereit")
        result=db.apply_import_suggestions(job["id"],["publisher","year"])
        assert set(result["applied"]) == {"publisher","year"}
        saved=db.get_game("g1")
        assert saved["publisher"] == "Hasbro"
        assert saved["year"] == 2015
        assert saved["storage_location"] == "2. Tablar"
        assert saved["tags"] == []
        db.reject_import_suggestions(job["id"],["tags"])
        assert db.get_import_job(job["id"])["status"] == "verified"

def test_manual_values_survive_research_until_user_accepts():
    with tempfile.TemporaryDirectory() as tmp:
        db=setup(tmp)
        game=db.normalize_game({"id":"g1","title":"Azul","publisher":"Mein Verlag"})
        db.save_game(game)
        job=db.enqueue_import_job("g1","Azul")
        proposed=db.normalize_game({**game,"publisher":"Next Move Games","description":"Abstraktes Legespiel"},game)
        db.replace_import_suggestions(job["id"],"g1",proposed,game)
        assert db.get_game("g1")["publisher"] == "Mein Verlag"
        suggestions={x["field"]:x["value"] for x in db.get_import_job(job["id"])["suggestions"]}
        assert suggestions["publisher"] == "Next Move Games"


def test_safe_bulk_apply_uses_backend_evidence_only():
    with tempfile.TemporaryDirectory() as tmp:
        db=setup(tmp)
        game=db.normalize_game({"id":"g1","title":"Scythe"})
        db.save_game(game)
        job=db.enqueue_import_job("g1","Scythe")
        proposed=db.normalize_game({**game,"publisher":"Feuerland Spiele","year":2016,"description":"KI-Text"},game)
        evidence={
            "publisher":{"level":"primary","safe_to_apply":True,"label":"Primärquelle"},
            "year":{"level":"strong","safe_to_apply":True,"label":"Gut belegt"},
            "description":{"level":"derived","safe_to_apply":False,"label":"KI-abgeleitet"},
        }
        db.replace_import_suggestions(job["id"],"g1",proposed,game,field_evidence=evidence)
        db.update_import_job(job["id"],status="review",progress="Vorschläge bereit")
        result=db.apply_safe_import_suggestions(job["id"])
        assert set(result["applied"]) == {"publisher","year"}
        saved=db.get_game("g1")
        assert saved["publisher"] == "Feuerland Spiele"
        assert saved["year"] == 2016
        assert saved["description"] == ""
        pending={x["field"]:x for x in db.get_import_job(job["id"])["suggestions"] if x["status"]=="pending"}
        assert "description" in pending
        assert pending["description"]["evidence"]["level"] == "derived"

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
        assert backup["version"] == 4
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

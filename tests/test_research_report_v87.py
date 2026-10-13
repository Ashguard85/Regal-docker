import importlib
import os
import tempfile


def test_research_report_persists_on_job():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DATA_DIR"] = tmp
        import app.db as db
        importlib.reload(db)
        db.init_db()
        game = db.normalize_game({"id":"g1","title":"Cascadia"})
        db.save_game(game)
        job = db.enqueue_import_job("g1", "Cascadia")
        report = {"pipeline":"v8.7","identity":{"provider":"BoardGameGeek","bgg_id":199792,"title":"Cascadia","score":97},"selected":[],"ignored":[]}
        db.update_import_job(job["id"], research=report, sources=["https://boardgamegeek.com/boardgame/199792"])
        loaded = db.get_import_job(job["id"])
        assert loaded["research"]["identity"]["bgg_id"] == 199792
        assert loaded["sources"] == ["https://boardgamegeek.com/boardgame/199792"]
        assert db.SCHEMA_VERSION == 8

import importlib
import json
import os
import sqlite3
import tempfile


def load_db(tmp):
    os.environ["DATA_DIR"] = tmp
    import app.db as db
    importlib.reload(db)
    return db


def test_v1_sqlite_migrates_without_data_loss():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "app.sqlite")
        conn = sqlite3.connect(path)
        conn.executescript("""
        CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
        INSERT INTO schema_migrations VALUES (1, '2026-01-01T00:00:00Z');
        CREATE TABLE games (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
          source_url TEXT NOT NULL DEFAULT '', rules_url TEXT NOT NULL DEFAULT '', rules_text TEXT NOT NULL DEFAULT '',
          min_players INTEGER, max_players INTEGER, play_time_min INTEGER, min_age INTEGER,
          publisher TEXT NOT NULL DEFAULT '', year INTEGER, tags_json TEXT NOT NULL DEFAULT '[]',
          notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        """)
        conn.execute("INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            "g1", "Sky Team", "alt", "https://example.com", "", "", 2, 2, 20, 10,
            "Kosmos", 2024, "[]", "Notiz", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"
        ))
        conn.commit(); conn.close()
        db = load_db(tmp)
        db.init_db()
        game = db.get_game("g1")
        assert game["title"] == "Sky Team"
        assert game["designer"] == ""
        assert game["ean"] == ""
        assert game["cover_url"] == ""
        assert game["award"] == ""
        with db.connect() as c:
            assert {r[0] for r in c.execute("SELECT version FROM schema_migrations")} == {1, 2}


def test_v1_backup_is_accepted_and_upgraded_on_export():
    with tempfile.TemporaryDirectory() as tmp:
        db = load_db(tmp); db.init_db()
        old = {
            "format": "brettspielregal-backup", "version": 1,
            "data": {"games": [{"id": "old", "title": "Azul", "tags": ["Familie"]}], "settings": {}}
        }
        result = db.import_backup(old, "merge")
        assert result["imported"] == 1
        assert db.get_game("old")["designer"] == ""
        assert db.backup_payload()["version"] == 2


def test_new_fields_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        db = load_db(tmp); db.init_db()
        game = db.normalize_game({
            "id": "sky", "title": "Sky Team", "designer": "Luc Rémond", "ean": "4002051684044",
            "cover_url": "https://example.com/sky.jpg", "award": "Spiel des Jahres 2024"
        })
        db.save_game(game)
        saved = db.get_game("sky")
        assert saved["designer"] == "Luc Rémond"
        assert saved["ean"] == "4002051684044"
        assert saved["award"] == "Spiel des Jahres 2024"

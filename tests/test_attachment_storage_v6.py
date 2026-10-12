"""Tests that run without Flask, including migration and file/backup roundtrip."""
import base64
import importlib
import os
import sqlite3
import tempfile

import pytest

PNG = b"\x89PNG\r\n\x1a\n" + b"small image payload"
PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00"


def setup(tmp):
    os.environ["DATA_DIR"] = tmp
    import app.db as db
    import app.attachments as att
    importlib.reload(db)
    importlib.reload(att)
    db.init_db()
    return db, att


def test_migration_from_v2_preserves_games_and_adds_attachment_table():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "app.sqlite")
        conn = sqlite3.connect(path)
        conn.executescript("""
        CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
        INSERT INTO schema_migrations VALUES (1,'2026-01-01'),(2,'2026-01-01');
        CREATE TABLE games (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '', rules_url TEXT NOT NULL DEFAULT '', rules_text TEXT NOT NULL DEFAULT '',
            min_players INTEGER, max_players INTEGER, play_time_min INTEGER, min_age INTEGER,
            publisher TEXT NOT NULL DEFAULT '', year INTEGER, designer TEXT NOT NULL DEFAULT '',
            ean TEXT NOT NULL DEFAULT '', cover_url TEXT NOT NULL DEFAULT '', award TEXT NOT NULL DEFAULT '',
            tags_json TEXT NOT NULL DEFAULT '[]', notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        INSERT INTO games(id,title,created_at,updated_at) VALUES('old','Altes Spiel','2026','2026');
        """)
        conn.close()
        db, att = setup(tmp)
        assert db.get_game("old")["title"] == "Altes Spiel"
        assert db.get_game("old")["cover_attachment_id"] == ""
        with db.connect() as conn:
            assert conn.execute("SELECT count(*) FROM attachments").fetchone()[0] == 0
            assert {r[0] for r in conn.execute("SELECT version FROM schema_migrations")} == {1,2,3,4}


def test_attachment_backup_and_merge_preserve_files():
    with tempfile.TemporaryDirectory() as tmp:
        db, att = setup(tmp)
        db.save_game(db.normalize_game({"id":"g1","title":"Azul"}))
        image=att.make_record("g1","foto.png",PNG)
        manual=att.make_record("g1","anleitung.pdf",PDF)
        for record,data in [(image,PNG),(manual,PDF)]:
            att.write_file(record,data)
            db.add_attachment(record)
        game=db.get_game("g1")
        game["cover_attachment_id"]=image["id"]
        db.save_game(db.normalize_game(game,game))
        assert len(db.get_game("g1")["attachments"])==2
        backup=db.backup_payload()
        assert backup["version"]==3
        assert len(backup["data"]["attachments"])==2
        assert base64.b64decode(backup["data"]["attachments"][0]["content_base64"]) in (PNG,PDF)
        assert db.preview_import(backup)["same"]==1
        db.import_backup(backup,"replace")
        assert len(db.get_game("g1")["attachments"])==2
        assert att.read_file(image["id"])==PNG
        db.import_backup(backup,"merge")
        assert len(db.get_game("g1")["attachments"])==2
        legacy={"format":"brettspielregal-backup","version":2,"data":{"games":backup["data"]["games"],"settings":{}}}
        db.import_backup(legacy,"merge")
        assert len(db.get_game("g1")["attachments"])==2
        db.import_backup(legacy,"replace")
        assert db.get_game("g1")["attachments"]==[]
        assert not (att.attachment_dir()/image["id"]).exists()


def test_rejects_invalid_backup_before_changing_db():
    with tempfile.TemporaryDirectory() as tmp:
        db, att=setup(tmp)
        db.save_game(db.normalize_game({"id":"g1","title":"Original"}))
        image=att.make_record("g1","photo.png",PNG)
        backup=db.backup_payload()
        backup["data"]["attachments"]=[{**image,"content_base64":base64.b64encode(b"<script>").decode()}]
        with pytest.raises(ValueError):db.preview_import(backup)
        with pytest.raises(ValueError):db.import_backup(backup,"replace")
        assert db.get_game("g1")["title"]=="Original"
        assert att.detect_mime(HEIC)=="image/heic"
        with pytest.raises(ValueError):att.check_bytes(b"bad")
        with pytest.raises(ValueError):att.check_bytes(PNG+b"x"*(10*1024*1024))

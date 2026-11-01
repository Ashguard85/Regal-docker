"""v9.1 regression: ZIP safety, AI provenance restrictions, shared frontend hooks."""
import importlib
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

import pytest


def setup(folder):
    os.environ["DATA_DIR"]=folder
    from app import db,attachments
    importlib.reload(db);importlib.reload(attachments)
    db.init_db()
    return db,attachments


def test_full_zip_roundtrip_restores_settings_db_files_and_keeps_safety_backup():
    from app import zip_backup
    with tempfile.TemporaryDirectory() as folder:
        db,attachments=setup(folder)
        db.save_game(db.normalize_game({"id":"g1","title":"Scythe","bgg_id":169786,"storage_location":"Wohnzimmer"}))
        data=b"\x89PNG\r\n\x1a\n"+b"image-data"
        row=attachments.make_record("g1","cover.png",data)
        attachments.write_file(row,data);db.add_attachment(row)
        db.set_app_setting("v91_test_setting","special")
        z=zip_backup.create_zip(db.DATA_DIR)
        assert z.is_file()
        with zipfile.ZipFile(z) as f:
            assert "manifest.json" in f.namelist()
            assert "database.sqlite" in f.namelist()
            assert "attachments/"+row["id"] in f.namelist()
        db.save_game(db.normalize_game({"id":"g2","title":"New, should disappear"}))
        db.set_app_setting("v91_test_setting","changed")
        out=zip_backup.stage_restore(db.DATA_DIR,io.BytesIO(z.read_bytes()))
        assert out["games"]==1 and out["attachments"]==1 and out["pending"]
        # Non-restart calls must not activate a pending restore.
        db.init_db()
        assert db.get_game("g2") is not None
        assert zip_backup.apply_pending_on_start(db.DATA_DIR)
        db.init_db()
        assert db.get_game("g2") is None
        assert db.get_game("g1")["bgg_id"]==169786
        assert attachments.read_file(row["id"])==data
        assert db.get_app_settings(["v91_test_setting"])["v91_test_setting"]=="special"
        assert list(db.BACKUP_DIR.glob("before-restore-*.zip"))


def test_full_zip_detects_corruption_and_bad_paths():
    from app import zip_backup
    with tempfile.TemporaryDirectory() as folder:
        db,_=setup(folder)
        db.save_game(db.normalize_game({"id":"g1","title":"Azul"}))
        z=zip_backup.create_zip(db.DATA_DIR)
        with zipfile.ZipFile(z) as original, io.BytesIO() as dest:
            with zipfile.ZipFile(dest,"w") as wrong:
                for item in original.namelist():
                    content=original.read(item)
                    wrong.writestr(item,b"corrupted" if item=="database.sqlite" else content)
            with pytest.raises(ValueError,match="Prüfsumme"):
                zip_backup.stage_restore(db.DATA_DIR,io.BytesIO(dest.getvalue()))
        with io.BytesIO() as buf:
            with zipfile.ZipFile(buf,"w") as wrong:
                wrong.writestr("../evil.txt","bad")
                wrong.writestr("manifest.json",'{}')
            with pytest.raises(ValueError,match="Unzulässiger Dateiname"):
                zip_backup.stage_restore(db.DATA_DIR,io.BytesIO(buf.getvalue()))


def test_auto_approval_must_be_opted_in_and_has_source_protection():
    with tempfile.TemporaryDirectory() as folder:
        db,_=setup(folder)
        assert db.get_auto_approval_settings()["enabled"] is False
        with pytest.raises(ValueError):db.save_auto_approval_settings({"enabled":True,"fields":["description"]})
        prefs=db.save_auto_approval_settings({"enabled":True,"fields":["publisher","year"]})
        assert prefs["fields"]==["publisher","year"]
        original=db.normalize_game({"id":"g1","title":"Scythe"});db.save_game(original)
        job=db.enqueue_import_job("g1","Scythe")
        proposed=db.normalize_game({**original,"publisher":"Feuerland","year":2016,"description":"KI-Text"},original)
        ev={"publisher":{"safe_to_apply":True,"level":"primary"},"year":{"safe_to_apply":False,"level":"conflict"},"description":{"safe_to_apply":False,"level":"derived"}}
        db.replace_import_suggestions(job["id"],"g1",proposed,original,ev)
        db.update_import_job(job["id"],status="review")
        result=db.auto_approve_import_suggestions(job["id"])
        assert result["applied"]==["publisher"]
        game=db.get_game("g1")
        assert game["publisher"]=="Feuerland" and game["year"] is None and not game["description"]
        assert db.get_import_job(job["id"])["status"]=="review"
        db.save_auto_approval_settings({"enabled":False,"fields":["publisher"]})
        assert db.get_auto_approval_settings()["enabled"] is False


def test_frontend_has_offline_scanner_and_restore_controls():
    root=Path(__file__).resolve().parents[1]
    js=(root/"frontend/app.js").read_text()
    html=(root/"frontend/index.html").read_text()
    providers=(root/"frontend/providers.js").read_text()
    assert "getUserMedia" in js and "BarcodeDetector" in js and "stopScanner()" in js
    assert "useOfflineSnapshot" in js and "createOfflineSnapshot" in providers
    assert "class OfflineProvider" in providers and "Offline-Regal ist schreibgeschützt" in providers
    assert 'id="fullRestoreToken"' in html and 'id="aiApprovalEnabled"' in html
    assert 'id="diagSqlite"' in html and 'id="diagBackup"' in html

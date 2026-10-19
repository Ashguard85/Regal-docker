"""Validated full-volume backups; staged restore activates on full stack restart.

The ZIP intentionally omits environment variables/Cloudflare secrets. It preserves
SQLite (including app/research settings and job history) and original attachments.
"""
import fcntl
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

MAX_ZIP_BYTES = 1024 * 1024 * 1024
MAX_UNPACKED_BYTES = 2 * 1024 * 1024 * 1024
MAX_FILES = 4000
ID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")


def sha(path):
    digest=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda: f.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_files(data_dir, snapshot):
    items=[("database.sqlite",snapshot)]
    root=data_dir/"attachments"
    if root.exists():
        for p in sorted(root.iterdir()):
            if p.is_file() and not p.is_symlink() and ID_RE.fullmatch(p.name):
                items.append(("attachments/"+p.name,p))
    return items


def create_zip(data_dir, destination=None):
    data_dir=Path(data_dir)
    (data_dir/"backups").mkdir(parents=True,exist_ok=True)
    target=Path(destination) if destination else data_dir/"backups"/("full-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+".zip")
    if target.parent.resolve()!= (data_dir/"backups").resolve():
        raise ValueError("Backup-Pfad ausserhalb des Backup-Ordners nicht erlaubt.")
    with tempfile.TemporaryDirectory(prefix="snapshot-",dir=data_dir/"backups") as tmp:
        snap=Path(tmp)/"database.sqlite"
        src=sqlite3.connect(data_dir/"app.sqlite")
        dst=sqlite3.connect(snap)
        try:src.backup(dst)
        finally:src.close();dst.close()
        files=_manifest_files(data_dir,snap)
        _inspect_db(snap,{n:None for n,_ in files})
        if len(files)>MAX_FILES:raise ValueError("Zu viele Dateien für ZIP-Backup.")
        total=sum(f.stat().st_size for _,f in files)
        if total>MAX_UNPACKED_BYTES:raise ValueError("Backup zu gross.")
        manifest={"format":"brettspielregal-full-zip","version":1,"created_at":datetime.now(timezone.utc).isoformat(),"files":{n:{"size":p.stat().st_size,"sha256":sha(p)} for n,p in files}}
        pending=target.with_suffix(".tmp")
        try:
            with zipfile.ZipFile(pending,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=4,allowZip64=True) as z:
                z.writestr("manifest.json",json.dumps(manifest,ensure_ascii=False,indent=2))
                for name,p in files:z.write(p,name)
            os.replace(pending,target)
            try:keep=max(1,min(30,int(os.environ.get("FULL_BACKUP_KEEP","5"))))
            except ValueError:keep=5
            backups=sorted((data_dir/"backups").glob("full-*.zip"),key=lambda f:f.stat().st_mtime,reverse=True)
            for old in backups[keep:]:old.unlink(missing_ok=True)
        finally:pending.unlink(missing_ok=True)
    return target


def _validate_zip(path, extract_to=None):
    path=Path(path)
    if path.stat().st_size>MAX_ZIP_BYTES:raise ValueError("ZIP ist grösser als 1 GB.")
    with zipfile.ZipFile(path) as z:
        info=z.infolist()
        if len(info)>MAX_FILES+2 or sum(i.file_size for i in info)>MAX_UNPACKED_BYTES:raise ValueError("ZIP enthält zu viele Daten.")
        names=[i.filename for i in info]
        if len(names)!=len(set(names)) or "manifest.json" not in names:raise ValueError("ZIP-Einträge fehlen oder sind doppelt.")
        for i in info:
            if i.is_dir() or ((i.external_attr>>16)&0o170000)==0o120000:raise ValueError("Ordner/Links im ZIP nicht erlaubt.")
            if i.filename!="manifest.json" and i.filename!="database.sqlite" and not (i.filename.startswith("attachments/") and ID_RE.fullmatch(i.filename.split("/",1)[1])):
                raise ValueError("Unzulässiger Dateiname im ZIP.")
        if z.getinfo("manifest.json").file_size > 1024*1024: raise ValueError("Manifest zu gross.")
        try:manifest=json.loads(z.read("manifest.json"))
        except Exception as exc:raise ValueError("Manifest ungültig.") from exc
        if manifest.get("format")!="brettspielregal-full-zip" or manifest.get("version")!=1:raise ValueError("Unbekanntes ZIP-Backup-Format.")
        files=manifest.get("files")
        if not isinstance(files,dict) or "database.sqlite" not in files or set(names)!={"manifest.json",*files}:raise ValueError("ZIP-Inhalt stimmt nicht mit dem Manifest überein.")
        root=Path(extract_to) if extract_to else None
        for name,meta in files.items():
            if not isinstance(meta,dict) or not isinstance(meta.get("size"),int):raise ValueError("Ungültiges Datei-Manifest.")
            h=hashlib.sha256();count=0
            dest=root/name if root else None
            if dest:
                dest.parent.mkdir(parents=True,exist_ok=True)
                out=open(dest,"wb")
            else:out=None
            try:
                with z.open(name) as f:
                    while True:
                        b=f.read(1024*1024)
                        if not b:break
                        count+=len(b);h.update(b)
                        if out:out.write(b)
                if count!=meta["size"] or h.hexdigest()!=meta.get("sha256"):raise ValueError(f"Prüfsumme ungültig: {name}")
            finally:
                if out:out.close()
        # Validate SQLite, its schema, and every declared attachment relation.
        dbpath=(root/"database.sqlite") if root else None
        if dbpath is None:
            with tempfile.TemporaryDirectory() as d:
                dbpath=Path(d)/"backup.sqlite"
                with z.open("database.sqlite") as f,open(dbpath,"wb") as target:shutil.copyfileobj(f,target)
                counts=_inspect_db(dbpath,files)
        else:counts=_inspect_db(dbpath,files)
        return {"games":counts[0],"attachments":counts[1],"size_bytes":sum(v["size"] for v in files.values()),"created_at":manifest.get("created_at")}


def _inspect_db(path,files):
    try:
        c=sqlite3.connect(f"file:{path}?mode=ro",uri=True)
        try:
            if c.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise ValueError("SQLite-Integritätsprüfung fehlgeschlagen.")
            tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"games","attachments","schema_migrations","import_jobs","app_settings"}.issubset(tables):raise ValueError("SQLite-Schema unvollständig.")
            if c.execute("PRAGMA foreign_key_check").fetchone():raise ValueError("SQLite-Fremdschlüsselprüfung fehlgeschlagen.")
            games=c.execute("SELECT COUNT(*) FROM games").fetchone()[0]
            ids={r[0] for r in c.execute("SELECT id FROM attachments")}
            archive_ids={x.split("/",1)[1] for x in files if x.startswith("attachments/")}
            if ids!=archive_ids:raise ValueError("Dateien und Attachment-Einträge stimmen nicht überein.")
            return games,len(ids)
        finally:c.close()
    except sqlite3.DatabaseError as exc:raise ValueError("SQLite-Datenbank ungültig.") from exc


def stage_restore(data_dir,upload):
    data_dir=Path(data_dir);data_dir.mkdir(parents=True,exist_ok=True)
    pending=data_dir/"restore-pending.zip";tmp=data_dir/"restore-upload.tmp"
    try:
        size=0
        with open(tmp,"wb") as f:
            while True:
                buf=upload.read(1024*1024)
                if not buf:break
                size+=len(buf)
                if size>MAX_ZIP_BYTES:raise ValueError("ZIP ist grösser als 1 GB.")
                f.write(buf)
        info=_validate_zip(tmp)
        os.replace(tmp,pending)
        return {**info,"pending":True}
    finally:tmp.unlink(missing_ok=True)


def apply_pending_on_start(data_dir):
    """Called before db.init_db; all stack services should be restarted together."""
    data_dir=Path(data_dir);pending=data_dir/"restore-pending.zip"
    if not pending.exists():return False
    data_dir.mkdir(parents=True,exist_ok=True)
    with open(data_dir/"restore.lock","a+b") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if not pending.exists():return False
        with tempfile.TemporaryDirectory(prefix="restore-stage-",dir=data_dir) as temp:
            src=Path(temp);_validate_zip(pending,src)
            if (data_dir/"app.sqlite").exists():
                create_zip(data_dir,data_dir/"backups"/("before-restore-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+".zip"))
            old=data_dir/"attachments";new=src/"attachments";safety=data_dir/"attachments-before-restore"
            if safety.exists():shutil.rmtree(safety)
            moved_old=False;installed_new=False
            try:
                if old.exists():os.replace(old,safety);moved_old=True
                if new.exists():os.replace(new,old)
                else:old.mkdir(exist_ok=True)
                installed_new=True
                for suffix in ("-wal","-shm"):
                    (data_dir/("app.sqlite"+suffix)).unlink(missing_ok=True)
                os.replace(src/"database.sqlite",data_dir/"app.sqlite")
            except Exception:
                if installed_new and old.exists():shutil.rmtree(old)
                if moved_old and safety.exists():os.replace(safety,old)
                raise
            pending.unlink()
            if safety.exists():shutil.rmtree(safety)
            # Generated thumbnails are not originals; they can be rebuilt.
            thumbs=data_dir/"thumbnails"
            if thumbs.exists():shutil.rmtree(thumbs)
        return True


if __name__ == "__main__":
    import sys
    if sys.argv[1:] != ["--apply-pending"]:
        raise SystemExit("Expected --apply-pending")
    from . import db
    applied=apply_pending_on_start(db.DATA_DIR)
    print("[restore] staged ZIP applied" if applied else "[restore] no pending ZIP",flush=True)

"""Validated user-uploaded images and PDF rules; stored under DATA_DIR/attachments."""
import base64
import binascii
import os
import re
import uuid
from pathlib import Path

from . import db
from PIL import UnidentifiedImageError

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES_PER_GAME = 15
MAX_BACKUP_ATTACHMENTS = 1000


def detect_mime(data):
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis"}:
            return "image/heic"
        if brand in {b"mif1", b"msf1", b"heif"}:
            return "image/heif"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def check_bytes(data):
    if not data or len(data) > MAX_FILE_BYTES:
        raise ValueError("Eine Datei muss zwischen 1 Byte und 10 MB groß sein.")
    mime = detect_mime(data)
    if not mime:
        raise ValueError("Erlaubt sind JPG, PNG, GIF, WebP, HEIC/HEIF und PDF.")
    return mime


def kind_for_mime(mime):
    return "rules" if mime == "application/pdf" else "image"


def clean_filename(name):
    name = str(name or "Anhang").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip().strip(".")
    return name[:180] or "Anhang"


def filename_for_mime(name, mime):
    name = clean_filename(name)
    valid = {
        "image/jpeg": (".jpg", ".jpeg"), "image/png": (".png",),
        "image/gif": (".gif",), "image/webp": (".webp",),
        "image/heic": (".heic",), "image/heif": (".heif",),
        "application/pdf": (".pdf",),
    }
    suffixes = valid[mime]
    return name if name.lower().endswith(suffixes) else name[:175] + suffixes[0]


def attachment_dir():
    return db.DATA_DIR / "attachments"


def file_path(attachment_id):
    # IDs are never used without UUID validation.
    uuid.UUID(attachment_id)
    return attachment_dir() / attachment_id


def make_record(game_id, filename, data, attachment_id=None, created_at=None):
    mime = check_bytes(data)
    return {
        "id": str(uuid.UUID(attachment_id)) if attachment_id else str(uuid.uuid4()),
        "game_id": game_id,
        "filename": filename_for_mime(filename, mime),
        "mime_type": mime,
        "kind": kind_for_mime(mime),
        "size": len(data),
        "created_at": created_at or db.utcnow(),
    }


def write_file(record, data):
    root = attachment_dir()
    root.mkdir(parents=True, exist_ok=True)
    target = file_path(record["id"])
    tmp = root / f".{record['id']}.{uuid.uuid4().hex}.tmp"
    try:
        with tmp.open("xb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
        thumbnail_path(record["id"]).unlink(missing_ok=True)
    finally:
        tmp.unlink(missing_ok=True)


def remove_file(attachment_id):
    file_path(attachment_id).unlink(missing_ok=True)
    thumbnail_path(attachment_id).unlink(missing_ok=True)


def read_file(attachment_id):
    try:
        return file_path(attachment_id).read_bytes()
    except FileNotFoundError:
        raise ValueError("Die Datei fehlt im Server-Datenverzeichnis.")


def decode_backup_attachments(backup, game_ids):
    if backup.get("version") not in {3, 4, 5}:
        return []
    raw = backup.get("data", {}).get("attachments", [])
    if not isinstance(raw, list) or len(raw) > MAX_BACKUP_ATTACHMENTS:
        raise ValueError("Ungültige Anzahl an Anhängen im Backup.")
    result = []
    seen = set()
    counts = {}
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("Ungültiger Anhang im Backup.")
        game_id = entry.get("game_id")
        if game_id not in game_ids:
            raise ValueError("Ein Anhang gehört zu keinem Spiel im Backup.")
        counts[game_id] = counts.get(game_id, 0) + 1
        if counts[game_id] > MAX_FILES_PER_GAME:
            raise ValueError("Mehr als 15 Anhänge für ein Spiel im Backup.")
        try:
            att_id = str(uuid.UUID(str(entry.get("id", ""))))
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Ungültige Anhang-ID im Backup.")
        if att_id in seen:
            raise ValueError("Doppelte Anhang-ID im Backup.")
        seen.add(att_id)
        encoded = entry.get("content_base64")
        if not isinstance(encoded, str) or len(encoded) > ((MAX_FILE_BYTES + 2) // 3 * 4) + 16:
            raise ValueError("Ungültiger oder zu großer Dateiinhalt im Backup.")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("Ungültige Base64-Daten im Backup.")
        record = make_record(game_id, entry.get("filename"), data, att_id, entry.get("created_at"))
        if entry.get("mime_type") and entry["mime_type"] != record["mime_type"]:
            raise ValueError("Dateityp stimmt nicht mit dem Dateiinhalt überein.")
        result.append((record, data))
    return result


def thumbnail_path(attachment_id):
    return db.DATA_DIR / "thumbnails" / (str(uuid.UUID(attachment_id)) + ".webp")


def generate_thumbnail(attachment_id):
    from io import BytesIO
    from PIL import Image, ImageOps, UnidentifiedImageError
    target = thumbnail_path(attachment_id)
    source = read_file(attachment_id)
    with Image.open(BytesIO(source)) as image:
        image = ImageOps.exif_transpose(image)
        image.thumbnail((480, 600))
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(".tmp")
        try:
            image.save(temp, "WEBP", quality=78, method=4)
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
    return target


def store_public_asset(game_id, url, kind):
    from .security import fetch_public_asset
    from urllib.parse import urlparse, unquote
    if kind not in {"cover", "rules"}:
        raise ValueError("Unbekannter Archivtyp.")
    game = db.get_game(game_id)
    if not game:
        raise ValueError("Spiel nicht gefunden.")
    raw, final_url = fetch_public_asset(url)
    mime = check_bytes(raw)
    if kind == "cover" and not mime.startswith("image/"):
        raise ValueError("Der Link enthält kein gültiges Bild.")
    if kind == "rules" and mime != "application/pdf":
        raise ValueError("Der Link enthält keine PDF-Anleitung.")
    name = unquote(Path(urlparse(final_url).path).name) or ("Cover" if kind == "cover" else "Anleitung")
    record = make_record(game_id, name, raw)
    write_file(record, raw)
    try:
        db.add_attachment(record)
        if kind == "cover":
            updated = db.normalize_game({"cover_attachment_id": record["id"]}, game)
            updated["id"] = game_id
            db.save_game(updated)
            try:
                generate_thumbnail(record["id"])
            except (OSError, ValueError, UnidentifiedImageError):
                pass  # original remains intact for HEIC and unsupported formats
    except Exception:
        remove_file(record["id"])
        raise
    return record

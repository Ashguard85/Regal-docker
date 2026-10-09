import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
DB_PATH = DATA_DIR / "app.sqlite"
BACKUP_DIR = DATA_DIR / "backups"
SCHEMA_VERSION = 2
BACKUP_VERSION = 2
SUPPORTED_BACKUP_VERSIONS = {1, 2}

GAME_COLUMNS = [
    "id", "title", "description", "source_url", "rules_url", "rules_text",
    "min_players", "max_players", "play_time_min", "min_age", "publisher", "year",
    "designer", "ean", "cover_url", "award", "tags_json", "notes", "created_at", "updated_at"
]


def utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def init_db():
    with connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        if 1 not in applied:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS games (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    rules_url TEXT NOT NULL DEFAULT '',
                    rules_text TEXT NOT NULL DEFAULT '',
                    min_players INTEGER,
                    max_players INTEGER,
                    play_time_min INTEGER,
                    min_age INTEGER,
                    publisher TEXT NOT NULL DEFAULT '',
                    year INTEGER,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_games_title ON games(title COLLATE NOCASE);
                CREATE INDEX IF NOT EXISTS idx_games_updated ON games(updated_at);
            """)
            conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?,?)", (1, utcnow()))

        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        if 2 not in applied:
            existing = _columns(conn, "games")
            additions = {
                "designer": "TEXT NOT NULL DEFAULT ''",
                "ean": "TEXT NOT NULL DEFAULT ''",
                "cover_url": "TEXT NOT NULL DEFAULT ''",
                "award": "TEXT NOT NULL DEFAULT ''",
            }
            for name, definition in additions.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE games ADD COLUMN {name} {definition}")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_games_ean ON games(ean)")
            conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?,?)", (2, utcnow()))


def _int_or_none(value, minimum=None, maximum=None):
    if value in (None, ""):
        return None
    try:
        n = int(value)
    except (ValueError, TypeError):
        return None
    if minimum is not None and n < minimum:
        return None
    if maximum is not None and n > maximum:
        return None
    return n


def _text(raw, existing, key, limit):
    return str(raw.get(key, existing.get(key, "")) or "").strip()[:limit]


def normalize_game(raw, existing=None):
    raw = raw or {}
    existing = existing or {}
    tags = raw.get("tags", existing.get("tags", []))
    if isinstance(tags, str):
        tags = [x.strip() for x in tags.split(",") if x.strip()]
    if not isinstance(tags, list):
        tags = []
    tags = list(dict.fromkeys(str(x).strip() for x in tags if str(x).strip()))
    now = utcnow()
    title = _text(raw, existing, "title", 180)
    if not title:
        raise ValueError("Titel ist erforderlich.")
    return {
        "id": _text(raw, existing, "id", 80),
        "title": title,
        "description": _text(raw, existing, "description", 6000),
        "source_url": _text(raw, existing, "source_url", 2000),
        "rules_url": _text(raw, existing, "rules_url", 2000),
        "rules_text": _text(raw, existing, "rules_text", 12000),
        "min_players": _int_or_none(raw.get("min_players", existing.get("min_players")), 1, 99),
        "max_players": _int_or_none(raw.get("max_players", existing.get("max_players")), 1, 99),
        "play_time_min": _int_or_none(raw.get("play_time_min", existing.get("play_time_min")), 1, 9999),
        "min_age": _int_or_none(raw.get("min_age", existing.get("min_age")), 0, 99),
        "publisher": _text(raw, existing, "publisher", 180),
        "year": _int_or_none(raw.get("year", existing.get("year")), 1800, 2200),
        "designer": _text(raw, existing, "designer", 240),
        "ean": _text(raw, existing, "ean", 32),
        "cover_url": _text(raw, existing, "cover_url", 2000),
        "award": _text(raw, existing, "award", 500),
        "tags": tags[:30],
        "notes": _text(raw, existing, "notes", 6000),
        "created_at": str(existing.get("created_at") or raw.get("created_at") or now),
        "updated_at": str(raw.get("updated_at") or now),
    }


def row_to_game(row):
    if row is None:
        return None
    d = dict(row)
    try:
        d["tags"] = json.loads(d.pop("tags_json") or "[]")
    except json.JSONDecodeError:
        d["tags"] = []
    for key in ("designer", "ean", "cover_url", "award"):
        d.setdefault(key, "")
    return d


def list_games():
    with connect() as conn:
        return [row_to_game(r) for r in conn.execute("SELECT * FROM games ORDER BY title COLLATE NOCASE")]


def get_game(game_id):
    with connect() as conn:
        return row_to_game(conn.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone())


def _db_values(game):
    values = [game.get(c if c != "tags_json" else "tags") for c in GAME_COLUMNS]
    values[GAME_COLUMNS.index("tags_json")] = json.dumps(game.get("tags", []), ensure_ascii=False)
    return values


def save_game(game):
    with connect() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO games ({','.join(GAME_COLUMNS)}) VALUES ({','.join('?' for _ in GAME_COLUMNS)})",
            _db_values(game),
        )
    return game


def delete_game(game_id):
    with connect() as conn:
        cur = conn.execute("DELETE FROM games WHERE id=?", (game_id,))
        return cur.rowcount > 0


def make_backup(reason="manual"):
    if not DB_PATH.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = BACKUP_DIR / f"app-{stamp}-{reason}.sqlite"
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    rotate_backups()
    return target


def rotate_backups():
    keep = max(1, int(os.environ.get("BACKUP_KEEP", "50")))
    files = sorted(BACKUP_DIR.glob("app-*.sqlite"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        old.unlink(missing_ok=True)


def backup_payload(source="server"):
    return {
        "format": "brettspielregal-backup",
        "version": BACKUP_VERSION,
        "exported_at": utcnow(),
        "meta": {"source": source, "schema_version": SCHEMA_VERSION},
        "data": {"games": list_games(), "settings": {}},
    }


def validate_backup(backup):
    if not isinstance(backup, dict) or backup.get("format") != "brettspielregal-backup" or backup.get("version") not in SUPPORTED_BACKUP_VERSIONS:
        raise ValueError("Ungültiges oder nicht unterstütztes Backup-Format.")
    data = backup.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("games"), list):
        raise ValueError("Backup enthält keine gültige Spieleliste.")
    games = []
    for raw in data["games"]:
        if not isinstance(raw, dict):
            raise ValueError("Backup enthält einen ungültigen Datensatz.")
        g = normalize_game(raw)
        if not g["id"]:
            raise ValueError("Ein Backup-Datensatz hat keine ID.")
        games.append(g)
    return games


def _comparable(game):
    x = dict(game)
    x.pop("updated_at", None)
    return json.dumps(x, sort_keys=True, ensure_ascii=False)


def preview_import(backup):
    incoming = validate_backup(backup)
    current = {g["id"]: g for g in list_games()}
    fresh = conflicts = same = 0
    for g in incoming:
        old = current.get(g["id"])
        if old is None:
            fresh += 1
        elif _comparable(old) == _comparable(g):
            same += 1
        else:
            conflicts += 1
    return {"total": len(incoming), "new": fresh, "conflicts": conflicts, "same": same}


def import_backup(backup, strategy="merge"):
    games = validate_backup(backup)
    if strategy not in {"merge", "replace"}:
        raise ValueError("Unbekannte Importstrategie.")
    make_backup("before-import")
    with connect() as conn:
        if strategy == "replace":
            conn.execute("DELETE FROM games")
        for g in games:
            conn.execute(
                f"INSERT OR REPLACE INTO games ({','.join(GAME_COLUMNS)}) VALUES ({','.join('?' for _ in GAME_COLUMNS)})",
                _db_values(g),
            )
    return {"imported": len(games), "strategy": strategy}

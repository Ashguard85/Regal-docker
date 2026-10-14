import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
DB_PATH = DATA_DIR / "app.sqlite"
BACKUP_DIR = DATA_DIR / "backups"
SCHEMA_VERSION = 8
BACKUP_VERSION = 4
SUPPORTED_BACKUP_VERSIONS = {1, 2, 3, 4}

GAME_COLUMNS = [
    "id", "title", "description", "source_url", "rules_url", "rules_text",
    "min_players", "max_players", "play_time_min", "min_age", "publisher", "year",
    "designer", "ean", "cover_url", "award", "cover_attachment_id", "storage_location", "tags_json", "notes", "created_at", "updated_at"
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

        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        if 3 not in applied:
            if "cover_attachment_id" not in _columns(conn, "games"):
                conn.execute("ALTER TABLE games ADD COLUMN cover_attachment_id TEXT NOT NULL DEFAULT ''")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS attachments (
                    id TEXT PRIMARY KEY,
                    game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_attachments_game ON attachments(game_id);
            """)
            conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?,?)", (3, utcnow()))

        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        if 4 not in applied:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS import_jobs (
                    id TEXT PRIMARY KEY,
                    game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                    query TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    progress TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT '',
                    warnings_json TEXT NOT NULL DEFAULT '[]',
                    sources_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_import_jobs_status_created ON import_jobs(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_import_jobs_game ON import_jobs(game_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS runtime_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );
            """)
            conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?,?)", (4, utcnow()))

        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        if 5 not in applied:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );
            """)
            conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?,?)", (5, utcnow()))

        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        if 6 not in applied:
            if "storage_location" not in _columns(conn, "games"):
                conn.execute("ALTER TABLE games ADD COLUMN storage_location TEXT NOT NULL DEFAULT ''")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS import_suggestions (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES import_jobs(id) ON DELETE CASCADE,
                    game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                    field TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(job_id, field)
                );
                CREATE INDEX IF NOT EXISTS idx_import_suggestions_job ON import_suggestions(job_id, status);
                CREATE INDEX IF NOT EXISTS idx_import_suggestions_game ON import_suggestions(game_id, status);
            """)
            conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?,?)", (6, utcnow()))

        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        if 7 not in applied:
            existing = _columns(conn, "import_jobs")
            if "cancel_requested" not in existing:
                conn.execute("ALTER TABLE import_jobs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0")
            if "cancel_requested_at" not in existing:
                conn.execute("ALTER TABLE import_jobs ADD COLUMN cancel_requested_at TEXT NOT NULL DEFAULT ''")
            conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?,?)", (7, utcnow()))

        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        if 8 not in applied:
            existing = _columns(conn, "import_jobs")
            if "research_json" not in existing:
                conn.execute("ALTER TABLE import_jobs ADD COLUMN research_json TEXT NOT NULL DEFAULT '{}'")
            conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?,?)", (8, utcnow()))

        applied = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        if 9 not in applied:
            existing = _columns(conn, "import_suggestions")
            if "evidence_json" not in existing:
                conn.execute("ALTER TABLE import_suggestions ADD COLUMN evidence_json TEXT NOT NULL DEFAULT '{}'")
            conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?,?)", (9, utcnow()))


def get_app_settings(keys=None):
    with connect() as conn:
        if keys:
            keys = [str(x)[:200] for x in keys]
            placeholders = ",".join("?" for _ in keys)
            rows = conn.execute(f"SELECT key,value FROM app_settings WHERE key IN ({placeholders})", keys).fetchall()
        else:
            rows = conn.execute("SELECT key,value FROM app_settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


def set_app_setting(key, value):
    key = str(key or "").strip()[:200]
    if not key:
        raise ValueError("Einstellungsschlüssel fehlt.")
    value = str(value or "")
    with connect() as conn:
        conn.execute("INSERT INTO app_settings(key,value,updated_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at", (key, value, utcnow()))


def delete_app_settings(keys):
    keys = [str(x)[:200] for x in (keys or []) if str(x).strip()]
    if not keys:
        return
    placeholders = ",".join("?" for _ in keys)
    with connect() as conn:
        conn.execute(f"DELETE FROM app_settings WHERE key IN ({placeholders})", keys)


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
        "cover_attachment_id": _text(raw, existing, "cover_attachment_id", 80),
        "storage_location": _text(raw, existing, "storage_location", 180),
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
    for key in ("designer", "ean", "cover_url", "award", "cover_attachment_id", "storage_location"):
        d.setdefault(key, "")
    return d


def _attachments_for(conn, game_id=None):
    if game_id is None:
        rows = conn.execute("SELECT * FROM attachments ORDER BY created_at, id").fetchall()
    else:
        rows = conn.execute("SELECT * FROM attachments WHERE game_id=? ORDER BY created_at, id", (game_id,)).fetchall()
    return [dict(r) for r in rows]


def list_attachments(game_id):
    with connect() as conn:
        return _attachments_for(conn, game_id)


def get_attachment(game_id, attachment_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM attachments WHERE id=? AND game_id=?", (attachment_id, game_id)).fetchone()
        return dict(row) if row else None


def add_attachment(record):
    with connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM attachments WHERE game_id=?", (record["game_id"],)).fetchone()[0]
        if count >= 15:
            raise ValueError("Maximal 15 Anhänge pro Spiel erlaubt.")
        conn.execute("INSERT INTO attachments(id,game_id,filename,mime_type,kind,size,created_at) VALUES (:id,:game_id,:filename,:mime_type,:kind,:size,:created_at)", record)
    return record


def delete_attachment(game_id, attachment_id):
    with connect() as conn:
        row = conn.execute("SELECT id FROM attachments WHERE id=? AND game_id=?", (attachment_id, game_id)).fetchone()
        if not row: return False
        conn.execute("DELETE FROM attachments WHERE id=? AND game_id=?", (attachment_id, game_id))
        conn.execute("UPDATE games SET cover_attachment_id='' WHERE id=? AND cover_attachment_id=?", (game_id, attachment_id))
        return True


def list_games():
    with connect() as conn:
        games = [row_to_game(r) for r in conn.execute("SELECT * FROM games ORDER BY title COLLATE NOCASE")]
        grouped = {}
        for att in _attachments_for(conn):
            grouped.setdefault(att["game_id"], []).append(att)
        for game in games:
            game["attachments"] = grouped.get(game["id"], [])
        return games


def get_game(game_id):
    with connect() as conn:
        game = row_to_game(conn.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone())
        if game: game["attachments"] = _attachments_for(conn, game_id)
        return game


def _db_values(game):
    values = [game.get(c if c != "tags_json" else "tags") for c in GAME_COLUMNS]
    values[GAME_COLUMNS.index("tags_json")] = json.dumps(game.get("tags", []), ensure_ascii=False)
    return values


def _upsert_game(conn, game):
    columns = ','.join(GAME_COLUMNS)
    placeholders = ','.join('?' for _ in GAME_COLUMNS)
    changes = ','.join(f'{col}=excluded.{col}' for col in GAME_COLUMNS if col != 'id')
    conn.execute(f"INSERT INTO games ({columns}) VALUES ({placeholders}) ON CONFLICT(id) DO UPDATE SET {changes}", _db_values(game))


def save_game(game):
    with connect() as conn:
        _upsert_game(conn, game)
    return game


def delete_game(game_id):
    with connect() as conn:
        cur = conn.execute("DELETE FROM games WHERE id=?", (game_id,))
        return cur.rowcount > 0


def _job_row(row):
    if row is None:
        return None
    data = dict(row)
    for key in ("warnings_json", "sources_json", "research_json"):
        try:
            default = "{}" if key == "research_json" else "[]"
            data[key[:-5]] = json.loads(data.pop(key) or default)
        except json.JSONDecodeError:
            data[key[:-5]] = {} if key == "research_json" else []
    data["cancel_requested"] = bool(data.get("cancel_requested"))
    return data


def find_game_by_ean(ean):
    digits = "".join(ch for ch in str(ean or "") if ch.isdigit())
    if not digits:
        return None
    with connect() as conn:
        return row_to_game(conn.execute("SELECT * FROM games WHERE ean=? LIMIT 1", (digits,)).fetchone())


def find_game_by_title(title):
    title = str(title or "").strip()
    if not title:
        return None
    with connect() as conn:
        return row_to_game(conn.execute("SELECT * FROM games WHERE title=? COLLATE NOCASE LIMIT 1", (title,)).fetchone())


def enqueue_import_job(game_id, query, *, replace_active=False):
    query = str(query or "").strip()[:500]
    if not query:
        raise ValueError("Für die automatische Ergänzung fehlt Titel oder EAN.")
    now = utcnow()
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM games WHERE id=?", (game_id,)).fetchone():
            raise ValueError("Spiel wurde nicht gefunden.")
        active = conn.execute("SELECT * FROM import_jobs WHERE game_id=? AND status IN ('queued','running') ORDER BY created_at DESC LIMIT 1", (game_id,)).fetchone()
        if active and not replace_active:
            return _job_row(active)
        if active and replace_active:
            conn.execute("UPDATE import_jobs SET status='cancelled', progress='Durch neuen Auftrag ersetzt', cancel_requested=1, cancel_requested_at=?, updated_at=?, finished_at=? WHERE id=?", (now, now, now, active['id']))
        import uuid
        job_id = str(uuid.uuid4())
        conn.execute("INSERT INTO import_jobs(id,game_id,query,status,progress,attempts,error,warnings_json,sources_json,created_at,updated_at,started_at,finished_at,cancel_requested,cancel_requested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (job_id, game_id, query, 'queued', 'Wartet auf automatische Ergänzung', 0, '', '[]', '[]', now, now, '', '', 0, ''))
        row = conn.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone()
        return _job_row(row)


def _suggestion_row(row):
    if row is None:
        return None
    data = dict(row)
    try:
        data["value"] = json.loads(data.pop("value_json"))
    except (json.JSONDecodeError, TypeError):
        data["value"] = None
    evidence_raw = data.pop("evidence_json", "{}")
    try:
        data["evidence"] = json.loads(evidence_raw or "{}")
    except (json.JSONDecodeError, TypeError):
        data["evidence"] = {}
    return data


def _suggestions_for_conn(conn, job_id):
    rows = conn.execute("SELECT * FROM import_suggestions WHERE job_id=? ORDER BY created_at, field", (job_id,)).fetchall()
    return [_suggestion_row(r) for r in rows]


def list_import_jobs(limit=100):
    try:
        limit = max(1, min(int(limit), 500))
    except Exception:
        limit = 100
    with connect() as conn:
        rows = conn.execute("""SELECT j.*, g.title AS game_title, g.ean AS game_ean, g.storage_location AS game_storage_location
                             FROM import_jobs j JOIN games g ON g.id=j.game_id
                             ORDER BY CASE j.status WHEN 'running' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END, j.created_at DESC
                             LIMIT ?""", (limit,)).fetchall()
        jobs = [_job_row(r) for r in rows]
        for job in jobs:
            job["suggestions"] = _suggestions_for_conn(conn, job["id"])
        return jobs


def get_import_job(job_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone()
        job = _job_row(row)
        if job:
            job["suggestions"] = _suggestions_for_conn(conn, job_id)
        return job


def retry_import_job(job_id):
    now = utcnow()
    with connect() as conn:
        row = conn.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        if row['status'] == 'running':
            raise ValueError("Ein laufender Auftrag kann nicht erneut gestartet werden.")
        conn.execute("DELETE FROM import_suggestions WHERE job_id=?", (job_id,))
        conn.execute("UPDATE import_jobs SET status='queued', progress='Wartet auf erneuten Versuch', error='', warnings_json='[]', sources_json='[]', research_json='{}', cancel_requested=0, cancel_requested_at='', updated_at=?, started_at='', finished_at='' WHERE id=?", (now, job_id))
        return _job_row(conn.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone())


def approve_import_job(job_id):
    """Compatibility helper: approval means explicitly applying all pending suggestions."""
    result = apply_import_suggestions(job_id)
    return get_import_job(job_id) if result is not None else None


def request_cancel_import_job(job_id):
    """Request cancellation of a queued/running job.

    Queued jobs can be cancelled immediately. Running jobs are marked for
    cancellation; the worker supervisor terminates the job process.
    """
    now = utcnow()
    with connect() as conn:
        row = conn.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        if row["status"] == "queued":
            conn.execute("DELETE FROM import_suggestions WHERE job_id=?", (job_id,))
            conn.execute("""UPDATE import_jobs
                            SET status='cancelled', progress='Abgebrochen', cancel_requested=1,
                                cancel_requested_at=?, updated_at=?, finished_at=?
                            WHERE id=?""", (now, now, now, job_id))
        elif row["status"] == "running":
            if not row["cancel_requested"]:
                conn.execute("""UPDATE import_jobs
                                SET cancel_requested=1, cancel_requested_at=?,
                                    progress='Abbruch angefordert – laufender Schritt wird beendet …',
                                    updated_at=?
                                WHERE id=?""", (now, now, job_id))
        elif row["status"] in {"review", "failed", "done", "verified", "cancelled"}:
            raise ValueError("Dieser Auftrag läuft nicht mehr.")
        return _job_row(conn.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone())


def finalize_cancel_import_job(job_id, progress="Abgebrochen"):
    """Finalize cancellation and discard temporary proposals. Idempotent."""
    now = utcnow()
    with connect() as conn:
        row = conn.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM import_suggestions WHERE job_id=?", (job_id,))
        conn.execute("""UPDATE import_jobs
                        SET status='cancelled', progress=?, cancel_requested=1,
                            cancel_requested_at=CASE WHEN cancel_requested_at='' THEN ? ELSE cancel_requested_at END,
                            updated_at=?, finished_at=?
                        WHERE id=?""", (str(progress)[:500], now, now, now, job_id))
        return _job_row(conn.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone())


def force_release_import_job(job_id):
    """Release an orphaned/stuck running job without deleting the game."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        if row["status"] != "running":
            raise ValueError("Nur ein laufender Auftrag kann freigegeben werden.")
    return finalize_cancel_import_job(job_id, "Hängender Auftrag freigegeben")


def cancel_import_job(job_id):
    """Compatibility: cancel queued jobs and request cancellation for running jobs."""
    job = request_cancel_import_job(job_id)
    return job is not None


def cleanup_import_jobs(mode="history"):
    """Delete queue/history rows without deleting games. Running jobs are always protected.

    history: failed/cancelled/done/verified
    including_review: history + review (pending suggestions cascade with the job)
    all_non_running: every job except running, including queued jobs and review suggestions
    """
    mode = str(mode or "history")
    if mode not in {"history", "including_review", "all_non_running"}:
        raise ValueError("Unbekannter Aufräummodus.")
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        before = conn.execute("SELECT COUNT(*) FROM import_jobs").fetchone()[0]
        running = conn.execute("SELECT COUNT(*) FROM import_jobs WHERE status='running'").fetchone()[0]
        if mode == "history":
            conn.execute("DELETE FROM import_jobs WHERE status IN ('failed','cancelled','done','verified')")
        elif mode == "including_review":
            conn.execute("DELETE FROM import_jobs WHERE status IN ('failed','cancelled','done','verified','review')")
        else:
            conn.execute("DELETE FROM import_jobs WHERE status<>'running'")
        after = conn.execute("SELECT COUNT(*) FROM import_jobs").fetchone()[0]
        conn.commit()
        return {"deleted": before - after, "remaining": after, "running_protected": running}


def claim_import_job(stale_minutes=30):
    now = utcnow()
    stale_before = (datetime.now(timezone.utc) - timedelta(minutes=max(5, int(stale_minutes)))).isoformat().replace('+00:00', 'Z')
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        # A cancellation request must never be revived after a worker restart.
        conn.execute("""UPDATE import_jobs
                        SET status='cancelled', progress='Abbruch abgeschlossen',
                            updated_at=?, finished_at=?
                        WHERE status='running' AND cancel_requested=1""", (now, now))
        conn.execute("""UPDATE import_jobs
                        SET status='queued', progress='Nach Worker-Neustart erneut eingereiht',
                            updated_at=?, started_at='', cancel_requested=0, cancel_requested_at=''
                        WHERE status='running' AND cancel_requested=0
                          AND started_at<>'' AND started_at<?""", (now, stale_before))
        row = conn.execute("SELECT * FROM import_jobs WHERE status='queued' AND cancel_requested=0 ORDER BY created_at ASC LIMIT 1").fetchone()
        if not row:
            conn.commit()
            return None
        conn.execute("""UPDATE import_jobs
                        SET status='running', progress='Recherche wird gestartet',
                            attempts=attempts+1, error='', cancel_requested=0, cancel_requested_at='',
                            updated_at=?, started_at=?, finished_at=''
                        WHERE id=? AND status='queued'""", (now, now, row['id']))
        claimed = conn.execute("SELECT * FROM import_jobs WHERE id=?", (row['id'],)).fetchone()
        conn.commit()
        return _job_row(claimed)


def update_import_job(job_id, *, status=None, progress=None, error=None, warnings=None, sources=None, research=None, finished=False):
    # A cancelled/cancelling job is immutable for normal worker updates. This
    # prevents a late HTTP/Ollama response from resurrecting the job.
    with connect() as conn:
        current = conn.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone()
        if current is None:
            return None
        if current["status"] == "cancelled" or current["cancel_requested"]:
            return _job_row(current)

    fields = ["updated_at=?"]
    values = [utcnow()]
    if status is not None:
        fields.append("status=?"); values.append(str(status)[:30])
    if progress is not None:
        fields.append("progress=?"); values.append(str(progress)[:500])
    if error is not None:
        fields.append("error=?"); values.append(str(error)[:2000])
    if warnings is not None:
        fields.append("warnings_json=?"); values.append(json.dumps(list(warnings)[:20], ensure_ascii=False))
    if sources is not None:
        fields.append("sources_json=?"); values.append(json.dumps(list(sources)[:20], ensure_ascii=False))
    if research is not None:
        fields.append("research_json=?"); values.append(json.dumps(research if isinstance(research, dict) else {}, ensure_ascii=False))
    if finished:
        fields.append("finished_at=?"); values.append(utcnow())
    values.append(job_id)
    with connect() as conn:
        conn.execute(f"UPDATE import_jobs SET {', '.join(fields)} WHERE id=?", values)
        return _job_row(conn.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone())


AI_SUGGESTIBLE_FIELDS = {
    "title", "description", "source_url", "rules_url", "rules_text",
    "min_players", "max_players", "play_time_min", "min_age", "publisher",
    "year", "designer", "ean", "cover_url", "award", "tags"
}


def replace_import_suggestions(job_id, game_id, proposed_game, current_game, field_evidence=None):
    """Replace temporary AI proposals for a job without touching the approved game row."""
    now = utcnow()
    import uuid
    rows = []
    field_evidence = field_evidence or {}
    for field in sorted(AI_SUGGESTIBLE_FIELDS):
        proposed = proposed_game.get(field)
        current = current_game.get(field)
        if proposed in (None, "", []):
            continue
        if proposed == current:
            continue
        rows.append((
            str(uuid.uuid4()), job_id, game_id, field,
            json.dumps(proposed, ensure_ascii=False),
            json.dumps(field_evidence.get(field) or {}, ensure_ascii=False),
            "pending", now, now
        ))
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        job = conn.execute("SELECT status,cancel_requested FROM import_jobs WHERE id=?", (job_id,)).fetchone()
        if not job or job["status"] == "cancelled" or job["cancel_requested"]:
            conn.rollback()
            return 0
        conn.execute("DELETE FROM import_suggestions WHERE job_id=?", (job_id,))
        conn.executemany("INSERT INTO import_suggestions(id,job_id,game_id,field,value_json,evidence_json,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)", rows)
        conn.commit()
    return len(rows)


def list_import_suggestions(job_id, status=None):
    with connect() as conn:
        if status:
            rows = conn.execute("SELECT * FROM import_suggestions WHERE job_id=? AND status=? ORDER BY created_at, field", (job_id, status)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM import_suggestions WHERE job_id=? ORDER BY created_at, field", (job_id,)).fetchall()
        return [_suggestion_row(r) for r in rows]


def _finish_job_if_no_pending(conn, job_id):
    pending = conn.execute("SELECT COUNT(*) FROM import_suggestions WHERE job_id=? AND status='pending'", (job_id,)).fetchone()[0]
    if pending == 0:
        now = utcnow()
        conn.execute("UPDATE import_jobs SET status='verified', progress='Vorschläge geprüft', updated_at=?, finished_at=? WHERE id=?", (now, now, job_id))
    else:
        conn.execute("UPDATE import_jobs SET status='review', progress=?, updated_at=? WHERE id=?", (f"{pending} Vorschlag{' ist' if pending == 1 else 'e sind'} noch offen", utcnow(), job_id))
    return pending


def apply_import_suggestions(job_id, fields=None):
    """Apply explicitly approved proposal fields to the current game row."""
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        job = conn.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            conn.rollback(); return None
        if job["status"] != "review":
            conn.rollback(); raise ValueError("Nur offene KI-Vorschläge können übernommen werden.")
        game_row = conn.execute("SELECT * FROM games WHERE id=?", (job["game_id"],)).fetchone()
        if not game_row:
            conn.rollback(); raise ValueError("Spiel wurde nicht gefunden.")
        game = row_to_game(game_row)
        params = [job_id]
        sql = "SELECT * FROM import_suggestions WHERE job_id=? AND status='pending'"
        if fields is not None:
            allowed = [str(f) for f in fields if str(f) in AI_SUGGESTIBLE_FIELDS]
            if not allowed:
                conn.rollback(); raise ValueError("Keine gültigen Vorschlagsfelder ausgewählt.")
            sql += " AND field IN (" + ",".join("?" for _ in allowed) + ")"
            params.extend(allowed)
        rows = conn.execute(sql, params).fetchall()
        if not rows:
            pending = _finish_job_if_no_pending(conn, job_id)
            conn.commit()
            return {"game": game, "applied": [], "pending": pending}
        payload = dict(game)
        applied = []
        ids = []
        for row in rows:
            item = _suggestion_row(row)
            payload[item["field"]] = item["value"]
            applied.append(item["field"]); ids.append(item["id"])
        normalized = normalize_game(payload, game); normalized["id"] = game["id"]
        _upsert_game(conn, normalized)
        placeholders = ",".join("?" for _ in ids)
        now = utcnow()
        conn.execute(f"UPDATE import_suggestions SET status='accepted', updated_at=? WHERE id IN ({placeholders})", [now, *ids])
        pending = _finish_job_if_no_pending(conn, job_id)
        conn.commit()
        return {"game": normalized, "applied": applied, "pending": pending}


def apply_safe_import_suggestions(job_id):
    """Apply only pending proposals that backend evidence marked safe for bulk approval."""
    with connect() as conn:
        job = conn.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            return None
        if job["status"] != "review":
            raise ValueError("Nur offene KI-Vorschläge können übernommen werden.")
        rows = conn.execute("SELECT * FROM import_suggestions WHERE job_id=? AND status='pending'", (job_id,)).fetchall()
        fields = []
        for row in rows:
            item = _suggestion_row(row)
            if bool((item.get("evidence") or {}).get("safe_to_apply")):
                fields.append(item["field"])
    if not fields:
        return {"game": None, "applied": [], "pending": len(rows)}
    return apply_import_suggestions(job_id, fields)


def reject_import_suggestions(job_id, fields=None):
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        job = conn.execute("SELECT * FROM import_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            conn.rollback(); return None
        if job["status"] != "review":
            conn.rollback(); raise ValueError("Nur offene KI-Vorschläge können verworfen werden.")
        params = [utcnow(), job_id]
        sql = "UPDATE import_suggestions SET status='rejected', updated_at=? WHERE job_id=? AND status='pending'"
        if fields is not None:
            allowed = [str(f) for f in fields if str(f) in AI_SUGGESTIBLE_FIELDS]
            if not allowed:
                conn.rollback(); raise ValueError("Keine gültigen Vorschlagsfelder ausgewählt.")
            sql += " AND field IN (" + ",".join("?" for _ in allowed) + ")"
            params.extend(allowed)
        conn.execute(sql, params)
        pending = _finish_job_if_no_pending(conn, job_id)
        conn.commit()
        return {"pending": pending}


def set_runtime_state(key, value):
    now = utcnow()
    with connect() as conn:
        conn.execute("INSERT INTO runtime_state(key,value,updated_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at", (str(key)[:100], str(value)[:1000], now))


def get_runtime_state(key):
    with connect() as conn:
        row = conn.execute("SELECT value,updated_at FROM runtime_state WHERE key=?", (key,)).fetchone()
        return dict(row) if row else None


def worker_state():
    state = get_runtime_state('import_worker')
    if not state:
        return {"status": "offline", "updated_at": "", "message": "Noch kein Worker-Heartbeat empfangen."}
    try:
        updated = datetime.fromisoformat(state['updated_at'].replace('Z', '+00:00'))
        age = (datetime.now(timezone.utc) - updated).total_seconds()
    except Exception:
        age = 999999
    return {"status": "online" if age < 30 else "offline", "updated_at": state['updated_at'], "message": state['value']}


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
    import base64
    from . import attachments as files
    all_games = list_games()
    items = []
    for game in all_games:
        for meta in game.pop("attachments", []):
            content = files.read_file(meta["id"])
            items.append({**meta, "content_base64": base64.b64encode(content).decode("ascii")})
    return {
        "format": "brettspielregal-backup",
        "version": BACKUP_VERSION,
        "exported_at": utcnow(),
        "meta": {"source": source, "schema_version": SCHEMA_VERSION},
        "data": {"games": all_games, "attachments": items, "settings": {}},
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
    x.pop("attachments", None)
    return json.dumps(x, sort_keys=True, ensure_ascii=False)


def preview_import(backup):
    incoming = validate_backup(backup)
    from . import attachments as files
    incoming_files = files.decode_backup_attachments(backup, {g["id"] for g in incoming})
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
    return {"total": len(incoming), "attachments": len(incoming_files), "new": fresh, "conflicts": conflicts, "same": same}


def import_backup(backup, strategy="merge"):
    from . import attachments as files
    games = validate_backup(backup)
    if strategy not in {"merge", "replace"}:
        raise ValueError("Unbekannte Importstrategie.")
    incoming_files = files.decode_backup_attachments(backup, {g["id"] for g in games})
    make_backup("before-import")
    # Store files first; database entries are only inserted after successful writes.
    # Replacing a backup can overwrite files with the same UUID; users should retain
    # an external copy of the JSON backup before importing.
    existing_ids = set()
    if strategy == "replace":
        with connect() as conn:
            existing_ids = {r[0] for r in conn.execute("SELECT id FROM attachments")}
    new_ids = {r["id"] for r, _ in incoming_files}
    for record, data in incoming_files:
        files.write_file(record, data)
    with connect() as conn:
        if strategy == "replace":
            conn.execute("DELETE FROM games")
        for g in games:
            _upsert_game(conn, g)
        for record, _ in incoming_files:
            conn.execute("INSERT OR REPLACE INTO attachments(id,game_id,filename,mime_type,kind,size,created_at) VALUES (:id,:game_id,:filename,:mime_type,:kind,:size,:created_at)", record)
    if strategy == "replace":
        for attachment_id in existing_ids - new_ids:
            files.remove_file(attachment_id)
    return {"imported": len(games), "attachments": len(incoming_files), "strategy": strategy}

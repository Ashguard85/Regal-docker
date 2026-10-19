import os
import uuid
import shutil
import sqlite3
import secrets
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, send_file
from io import BytesIO

from . import db, attachments, zip_backup
from .ai_import import import_from_url, import_from_text, import_from_images, search_official_rules
from .ai_provider import AIProviderError, provider_public_config, provider_status
from .research_search import search_provider_name as auto_search_provider_name, provider_status as search_provider_status, ResearchSearchError
from .research_config import get_settings as get_research_settings, save_settings as save_research_settings, reset_settings as reset_research_settings
from .tags import tag_catalog, normalize_tags
from .security import parse_allowed_origins

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"


def _configured_cors_origins():
    # v8.7: plural variable supports GitHub Pages, custom domains and optional LAN frontends.
    # The singular v8.5 variable remains a backwards-compatible fallback.
    plural = os.environ.get("PWA_ALLOWED_ORIGINS", "")
    legacy = os.environ.get("PWA_ALLOWED_ORIGIN", "")
    return parse_allowed_origins(plural, legacy)


def _cors_status_for_request():
    allowed, invalid = _configured_cors_origins()
    origin = (request.headers.get("Origin") or "").rstrip("/")
    if not origin:
        status = "not_required"
        permitted = True
    else:
        permitted = origin in set(allowed)
        status = "ok" if permitted else "blocked"
    return {
        "status": status,
        "allowed": permitted,
        "origin": origin,
        "configured_count": len(allowed),
        "invalid_entries": invalid,
    }


def create_app(test_config=None):
    app = Flask(__name__, static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=100 * 1024 * 1024, SECRET_KEY=os.environ.get("SECRET_KEY", "change-me"))
    if test_config:
        app.config.update(test_config)
    db.init_db()

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
        origin = request.headers.get("Origin")
        allowed_origins, _invalid_origins = _configured_cors_origins()
        if origin and origin.rstrip("/") in set(allowed_origins):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, CF-Access-Client-Id, CF-Access-Client-Secret, X-Brettspielregal-Restore-Token"
            response.headers["Access-Control-Max-Age"] = "600"
        return response

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify(status="ok")

    def _storage_diagnostics():
        try:
            usage = shutil.disk_usage(db.DATA_DIR)
            with db.connect() as conn:
                integrity=conn.execute("PRAGMA quick_check(1)").fetchone()[0]
                schema=conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
                games=conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
                files=conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0]
            latest=sorted(db.BACKUP_DIR.glob("full-*.zip"),key=lambda f:f.stat().st_mtime,reverse=True)
            return {"status":"ok" if integrity=="ok" else "error","database":"ok" if integrity=="ok" else "error","schema_version":schema,"games":games,"attachments":files,"free_bytes":usage.free,"last_full_backup":latest[0].stat().st_mtime if latest else None,"restore_pending":(db.DATA_DIR/"restore-pending.zip").exists()}
        except (OSError,sqlite3.DatabaseError) as exc:
            return {"status":"error","error":type(exc).__name__}

    @app.route("/api/system/status", methods=["GET", "OPTIONS"])
    def system_status():
        if request.method == "OPTIONS": return ("", 204)
        worker = db.worker_state()
        ai_enabled = os.environ.get("AI_IMPORT_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
        if not ai_enabled:
            ai = {"status": "disabled", "provider": provider_public_config().get("ai_provider", "none")}
        else:
            try:
                ai = provider_status()
            except AIProviderError as exc:
                ai = {"status": "error", "error": str(exc), "provider": provider_public_config().get("ai_provider", "none")}
        try:
            search = search_provider_status()
        except ResearchSearchError as exc:
            try:
                search_provider = auto_search_provider_name()
            except ResearchSearchError:
                search_provider = "invalid"
            search = {"status": "error", "provider": search_provider, "error": str(exc)}
        return jsonify(
            status="ok",
            version="9.1.1",
            backend={"status": "ok"},
            api={"status": "ok"},
            worker=worker,
            ai=ai,
            search=search,
            research={"pipeline":"v8.8-postfetch-ranked-field-evidence","bgg_enabled":os.environ.get("BGG_ENABLED", "true").lower() in {"1","true","yes","on"},"bgg_configured":bool(os.environ.get("BGG_API_TOKEN", "").strip())},
            cors=_cors_status_for_request(),
            bgg={"status":"configured" if os.environ.get("BGG_API_TOKEN", "").strip() else "no_token", "enabled":os.environ.get("BGG_ENABLED", "true").lower() in {"1","true","yes","on"}},
            storage=_storage_diagnostics(),
        )

    @app.route("/api/config", methods=["GET", "OPTIONS"])
    def api_config():
        if request.method == "OPTIONS": return ("", 204)
        ai_enabled = os.environ.get("AI_IMPORT_ENABLED", "false").lower() in {"1","true","yes","on"}
        public_ai = provider_public_config()
        return jsonify(
            title=os.environ.get("APP_TITLE", "Brettspielregal"),
            version="9.1.1",
            app_url=os.environ.get("APP_URL", ""),
            ai_import_enabled=ai_enabled,
            rules_search_enabled=ai_enabled,
            auto_enrich_enabled=ai_enabled and os.environ.get("AUTO_ENRICH_ENABLED", "true").lower() in {"1","true","yes","on"},
            auto_search_provider=auto_search_provider_name(),
            research_pipeline="v8.8-postfetch-ranked-field-evidence",
            bgg_enabled=os.environ.get("BGG_ENABLED", "true").lower() in {"1","true","yes","on"},
            bgg_configured=bool(os.environ.get("BGG_API_TOKEN", "").strip()),
            tag_catalog=tag_catalog(),
            **public_ai,
        )


    @app.route("/api/ai/approval-settings", methods=["GET", "PUT", "OPTIONS"])
    def ai_approval_settings():
        if request.method == "OPTIONS": return ("", 204)
        if request.method == "GET": return jsonify(db.get_auto_approval_settings())
        try: return jsonify(db.save_auto_approval_settings(request.get_json(silent=True) or {}))
        except ValueError as exc: return jsonify(error=str(exc)), 400

    @app.route("/api/backup/full", methods=["GET", "OPTIONS"])
    def full_zip_backup():
        if request.method == "OPTIONS": return ("", 204)
        try:
            target = zip_backup.create_zip(db.DATA_DIR)
            response = send_file(target, as_attachment=True, download_name=target.name, mimetype="application/zip")
            response.headers["Cache-Control"] = "private, no-store"
            return response
        except (ValueError, OSError) as exc: return jsonify(error=str(exc)), 400

    @app.route("/api/backup/full/restore", methods=["POST", "OPTIONS"])
    def stage_zip_restore():
        if request.method == "OPTIONS": return ("", 204)
        request.max_content_length = zip_backup.MAX_ZIP_BYTES + 1024 * 1024
        token = os.environ.get("BACKUP_RESTORE_TOKEN", "").strip()
        if len(token) < 20: return jsonify(error="Für den vollständigen Restore muss BACKUP_RESTORE_TOKEN (mindestens 20 Zeichen) in Portainer gesetzt werden."), 503
        if not secrets.compare_digest(request.headers.get("X-Brettspielregal-Restore-Token", ""), token): return jsonify(error="Ungültiger Restore-Schlüssel."), 403
        if request.form.get("confirmation") != "RESTORE": return jsonify(error="Bestätigung RESTORE erforderlich."), 400
        upload = request.files.get("file")
        if not upload: return jsonify(error="ZIP-Datei fehlt."), 400
        try: return jsonify(zip_backup.stage_restore(db.DATA_DIR, upload.stream)), 202
        except (ValueError, OSError, zip_backup.zipfile.BadZipFile) as exc: return jsonify(error=str(exc)), 400

    @app.route("/api/research-settings", methods=["GET", "PUT", "POST", "OPTIONS"])
    def research_settings():
        if request.method == "OPTIONS": return ("", 204)
        if request.method == "GET":
            return jsonify(get_research_settings())
        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
            if payload.get("action") != "reset":
                return jsonify(error="Unbekannte Aktion."), 400
            return jsonify(reset_research_settings())
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify(save_research_settings(payload))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400




    @app.route("/api/tags/cleanup", methods=["POST", "OPTIONS"])
    def cleanup_tags():
        if request.method == "OPTIONS": return ("", 204)
        changed = 0
        removed = 0
        for game in db.list_games():
            old = list(game.get("tags") or [])
            new = normalize_tags(old, limit=12)
            if old == new:
                continue
            removed += max(0, len(old) - len(new))
            payload = dict(game)
            payload["tags"] = new
            db.save_game(db.normalize_game(payload, game))
            changed += 1
        return jsonify(changed_games=changed, removed_tags=removed, tag_catalog=tag_catalog())

    @app.route("/api/ai/status", methods=["GET", "OPTIONS"])
    def ai_status():
        if request.method == "OPTIONS": return ("", 204)
        if os.environ.get("AI_IMPORT_ENABLED", "false").lower() not in {"1","true","yes","on"}:
            return jsonify(status="disabled", provider=provider_public_config().get("ai_provider", "none")), 503
        try:
            return jsonify(provider_status())
        except AIProviderError as exc:
            return jsonify(error=str(exc)), 503

    @app.route("/api/games", methods=["GET", "POST", "OPTIONS"])
    def games_collection():
        if request.method == "OPTIONS": return ("", 204)
        if request.method == "GET": return jsonify(db.list_games())
        payload = request.get_json(silent=True) or {}
        auto_enrich_requested = payload.pop("_auto_enrich", True) is not False
        payload["id"] = str(uuid.uuid4())
        try: game = db.normalize_game(payload)
        except ValueError as exc: return jsonify(error=str(exc)), 400
        db.save_game(game)
        if auto_enrich_requested and os.environ.get("AUTO_ENRICH_NEW_GAMES", "false").lower() in {"1","true","yes","on"} and os.environ.get("AI_IMPORT_ENABLED", "false").lower() in {"1","true","yes","on"}:
            try:
                db.enqueue_import_job(game["id"], game.get("ean") or game.get("title"))
            except ValueError:
                pass
        return jsonify(game), 201

    @app.route("/api/import-queue", methods=["GET", "OPTIONS"])
    def import_queue():
        if request.method == "OPTIONS": return ("", 204)
        try:
            stuck_minutes = min(max(int(os.environ.get("AUTO_ENRICH_STUCK_MINUTES", "10")), 2), 60)
        except ValueError:
            stuck_minutes = 10
        return jsonify(
            jobs=db.list_import_jobs(150),
            worker=db.worker_state(),
            force_release_after_seconds=stuck_minutes * 60,
            force_release_cancel_grace_seconds=15,
        )

    @app.route("/api/import-queue/cleanup", methods=["POST", "OPTIONS"])
    def cleanup_import_queue():
        if request.method == "OPTIONS": return ("", 204)
        payload = request.get_json(silent=True) or {}
        try: result = db.cleanup_import_jobs(payload.get("mode") or "history")
        except ValueError as exc: return jsonify(error=str(exc)), 400
        return jsonify(result)

    @app.route("/api/import-queue/quick", methods=["POST", "OPTIONS"])
    def quick_capture():
        if request.method == "OPTIONS": return ("", 204)
        payload = request.get_json(silent=True) or {}
        enrich_requested = payload.get("enrich", True) is not False
        if enrich_requested and (os.environ.get("AUTO_ENRICH_ENABLED", "true").lower() not in {"1","true","yes","on"} or os.environ.get("AI_IMPORT_ENABLED", "false").lower() not in {"1","true","yes","on"}):
            return jsonify(error='Die automatische Hintergrund-Ergänzung oder KI ist deaktiviert. Deaktiviere "Mit KI recherchieren", um nur zu erfassen.'), 503
        raw_text = str(payload.get("text") or "")
        raw_items = payload.get("items")
        if isinstance(raw_items, list):
            lines = [str(x).strip() for x in raw_items if str(x).strip()]
        else:
            lines = [x.strip() for x in raw_text.splitlines() if x.strip()]
        if not lines:
            return jsonify(error="Bitte mindestens einen Titel oder eine EAN eingeben."), 400
        storage_location = str(payload.get("storage_location") or "").strip()[:180]
        if len(lines) > 100:
            return jsonify(error="Pro Schnellerfassung sind maximal 100 Einträge erlaubt."), 400
        created = []
        for line in lines:
            digits = "".join(ch for ch in line if ch.isdigit())
            is_ean = 8 <= len(digits) <= 14 and all(ch.isdigit() or ch in " -" for ch in line)
            existing = db.find_game_by_ean(digits) if is_ean else db.find_game_by_title(line)
            if existing:
                game = existing
                reused = True
                if storage_location and not game.get("storage_location"):
                    payload_game = dict(game); payload_game["storage_location"] = storage_location
                    game = db.normalize_game(payload_game, game); game["id"] = existing["id"]
                    db.save_game(game)
            else:
                game_id = str(uuid.uuid4())
                raw = {"id": game_id, "title": f"EAN {digits}" if is_ean else line[:180], "ean": digits if is_ean else "", "storage_location": storage_location}
                try:
                    game = db.normalize_game(raw)
                except ValueError as exc:
                    return jsonify(error=str(exc)), 400
                db.save_game(game)
                reused = False
            query = digits if is_ean else line
            job = db.enqueue_import_job(game["id"], query) if enrich_requested else None
            created.append({"game": game, "job": job, "reused": reused, "enrichment_queued": bool(job)})
        return jsonify(items=created, count=len(created)), 201

    @app.route("/api/import-queue/games/<game_id>", methods=["POST", "OPTIONS"])
    def enqueue_existing_game(game_id):
        if request.method == "OPTIONS": return ("", 204)
        game = db.get_game(game_id)
        if not game: return jsonify(error="Spiel wurde nicht gefunden."), 404
        payload = request.get_json(silent=True) or {}
        query = str(payload.get("query") or game.get("ean") or game.get("title") or "").strip()
        try: job = db.enqueue_import_job(game_id, query, replace_active=bool(payload.get("replace_active")))
        except ValueError as exc: return jsonify(error=str(exc)), 400
        return jsonify(job), 201

    @app.route("/api/import-queue/<job_id>/retry", methods=["POST", "OPTIONS"])
    def retry_import_job(job_id):
        if request.method == "OPTIONS": return ("", 204)
        try: job = db.retry_import_job(job_id)
        except ValueError as exc: return jsonify(error=str(exc)), 409
        if not job: return jsonify(error="Import-Auftrag wurde nicht gefunden."), 404
        return jsonify(job)

    @app.route("/api/import-queue/<job_id>/cancel", methods=["POST", "OPTIONS"])
    def request_cancel_import_job(job_id):
        if request.method == "OPTIONS": return ("", 204)
        try: job = db.request_cancel_import_job(job_id)
        except ValueError as exc: return jsonify(error=str(exc)), 409
        if not job: return jsonify(error="Import-Auftrag wurde nicht gefunden."), 404
        return jsonify(job)

    @app.route("/api/import-queue/<job_id>/force-release", methods=["POST", "OPTIONS"])
    def force_release_import_job(job_id):
        if request.method == "OPTIONS": return ("", 204)
        try: job = db.force_release_import_job(job_id)
        except ValueError as exc: return jsonify(error=str(exc)), 409
        if not job: return jsonify(error="Import-Auftrag wurde nicht gefunden."), 404
        return jsonify(job)

    @app.route("/api/import-queue/<job_id>/approve", methods=["POST", "OPTIONS"])
    def approve_import_job(job_id):
        """Compatibility endpoint: v8.5 applies all pending AI suggestions explicitly."""
        if request.method == "OPTIONS": return ("", 204)
        try: result = db.apply_import_suggestions(job_id)
        except ValueError as exc: return jsonify(error=str(exc)), 409
        if not result: return jsonify(error="Import-Auftrag wurde nicht gefunden."), 404
        return jsonify(result)

    @app.route("/api/import-queue/<job_id>/suggestions/apply", methods=["POST", "OPTIONS"])
    def apply_import_suggestions(job_id):
        if request.method == "OPTIONS": return ("", 204)
        payload = request.get_json(silent=True) or {}
        fields = payload.get("fields")
        if fields is not None and not isinstance(fields, list):
            return jsonify(error="fields muss eine Liste sein."), 400
        try: result = db.apply_import_suggestions(job_id, fields)
        except ValueError as exc: return jsonify(error=str(exc)), 409
        if not result: return jsonify(error="Import-Auftrag wurde nicht gefunden."), 404
        return jsonify(result)

    @app.route("/api/import-queue/<job_id>/suggestions/apply-safe", methods=["POST", "OPTIONS"])
    def apply_safe_import_suggestions(job_id):
        if request.method == "OPTIONS": return ("", 204)
        try: result = db.apply_safe_import_suggestions(job_id)
        except ValueError as exc: return jsonify(error=str(exc)), 409
        if result is None: return jsonify(error="Import-Auftrag wurde nicht gefunden."), 404
        return jsonify(result)

    @app.route("/api/import-queue/<job_id>/suggestions/reject", methods=["POST", "OPTIONS"])
    def reject_import_suggestions(job_id):
        if request.method == "OPTIONS": return ("", 204)
        payload = request.get_json(silent=True) or {}
        fields = payload.get("fields")
        if fields is not None and not isinstance(fields, list):
            return jsonify(error="fields muss eine Liste sein."), 400
        try: result = db.reject_import_suggestions(job_id, fields)
        except ValueError as exc: return jsonify(error=str(exc)), 409
        if not result: return jsonify(error="Import-Auftrag wurde nicht gefunden."), 404
        return jsonify(result)

    @app.route("/api/import-queue/<job_id>", methods=["DELETE", "OPTIONS"])
    def cancel_import_job(job_id):
        if request.method == "OPTIONS": return ("", 204)
        try: ok = db.cancel_import_job(job_id)
        except ValueError as exc: return jsonify(error=str(exc)), 409
        if not ok: return jsonify(error="Import-Auftrag wurde nicht gefunden."), 404
        return jsonify(status="cancelled")

    @app.route("/api/games/<game_id>", methods=["GET", "PUT", "PATCH", "DELETE", "OPTIONS"])
    def game_item(game_id):
        if request.method == "OPTIONS": return ("", 204)
        existing = db.get_game(game_id)
        if not existing: return jsonify(error="Spiel wurde nicht gefunden."), 404
        if request.method == "GET": return jsonify(existing)
        if request.method == "DELETE":
            ids = [a["id"] for a in db.list_attachments(game_id)]
            db.delete_game(game_id)
            for attachment_id in ids: attachments.remove_file(attachment_id)
            return jsonify(status="deleted")
        payload = request.get_json(silent=True) or {}
        payload["id"] = game_id
        try: game = db.normalize_game(payload, existing)
        except ValueError as exc: return jsonify(error=str(exc)), 400
        game["id"] = game_id
        db.save_game(game)
        return jsonify(game)


    @app.route("/api/games/<game_id>/attachments", methods=["GET", "POST", "OPTIONS"])
    def game_attachments(game_id):
        if request.method == "OPTIONS": return ("", 204)
        if not db.get_game(game_id): return jsonify(error="Spiel wurde nicht gefunden."), 404
        if request.method == "GET": return jsonify(db.list_attachments(game_id))
        if len(db.list_attachments(game_id)) >= attachments.MAX_FILES_PER_GAME:
            return jsonify(error="Maximal 15 Anhänge pro Spiel erlaubt."), 400
        uploaded = request.files.get("file")
        if not uploaded: return jsonify(error="Bitte eine Datei auswählen."), 400
        content = uploaded.stream.read(attachments.MAX_FILE_BYTES + 1)
        try:
            record = attachments.make_record(game_id, uploaded.filename, content)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        try:
            attachments.write_file(record, content)
            db.add_attachment(record)
        except ValueError as exc:
            attachments.remove_file(record["id"])
            return jsonify(error=str(exc)), 400
        except Exception:
            attachments.remove_file(record["id"])
            raise
        return jsonify(record), 201

    @app.route("/api/games/<game_id>/attachments/<attachment_id>", methods=["GET", "DELETE", "OPTIONS"])
    def game_attachment_item(game_id, attachment_id):
        if request.method == "OPTIONS": return ("", 204)
        meta = db.get_attachment(game_id, attachment_id)
        if not meta: return jsonify(error="Anhang wurde nicht gefunden."), 404
        if request.method == "DELETE":
            db.delete_attachment(game_id, attachment_id)
            attachments.remove_file(attachment_id)
            return jsonify(status="deleted")
        try:
            content = attachments.read_file(attachment_id)
        except ValueError as exc:
            return jsonify(error=str(exc)), 404
        response = send_file(BytesIO(content), mimetype=meta["mime_type"], as_attachment=False,
                             download_name=meta["filename"], max_age=0)
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.route("/api/locations/rename", methods=["POST", "OPTIONS"])
    def rename_location():
        if request.method == "OPTIONS": return ("", 204)
        payload = request.get_json(silent=True) or {}
        try: return jsonify(db.rename_location(payload.get("old"), payload.get("new")))
        except ValueError as exc: return jsonify(error=str(exc)), 400

    @app.route("/api/games/<game_id>/archive", methods=["POST", "OPTIONS"])
    def archive_external(game_id):
        if request.method == "OPTIONS": return ("", 204)
        payload = request.get_json(silent=True) or {}
        game = db.get_game(game_id)
        if not game: return jsonify(error="Spiel nicht gefunden."), 404
        kind = str(payload.get("kind") or "")
        url = str(payload.get("url") or (game.get("cover_url") if kind == "cover" else game.get("rules_url")) or "")
        if not url or len(url) > 2000: return jsonify(error="Gültiger HTTPS-Link fehlt."), 400
        try:
            record = attachments.store_public_asset(game_id, url, kind)
        except (ValueError, OSError) as exc:
            return jsonify(error=str(exc)), 400
        return jsonify(attachment=record, game=db.get_game(game_id)), 201

    @app.route("/api/games/<game_id>/attachments/<attachment_id>/thumbnail", methods=["GET", "OPTIONS"])
    def attachment_thumbnail(game_id, attachment_id):
        if request.method == "OPTIONS": return ("", 204)
        meta = db.get_attachment(game_id, attachment_id)
        if not meta or meta.get("kind") != "image": return jsonify(error="Bild nicht gefunden."), 404
        try:
            target = attachments.thumbnail_path(attachment_id)
            if not target.is_file(): target = attachments.generate_thumbnail(attachment_id)
            response = send_file(target, mimetype="image/webp", as_attachment=False, max_age=0)
            response.headers["Cache-Control"] = "private, no-store"
            return response
        except Exception:
            return jsonify(error="Vorschau nicht verfügbar; Originalbild öffnen."), 415

    @app.route("/api/export", methods=["GET", "OPTIONS"])
    def export_all():
        if request.method == "OPTIONS": return ("", 204)
        response = jsonify(db.backup_payload())
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.route("/api/import/preview", methods=["POST", "OPTIONS"])
    def import_preview():
        if request.method == "OPTIONS": return ("", 204)
        payload = request.get_json(silent=True) or {}
        try: return jsonify(db.preview_import(payload.get("backup")))
        except ValueError as exc: return jsonify(error=str(exc)), 400

    @app.route("/api/import", methods=["POST", "OPTIONS"])
    def import_commit():
        if request.method == "OPTIONS": return ("", 204)
        payload = request.get_json(silent=True) or {}
        try: result = db.import_backup(payload.get("backup"), payload.get("strategy", "merge"))
        except ValueError as exc: return jsonify(error=str(exc)), 400
        return jsonify(result)

    @app.route("/api/ai/from-url", methods=["POST", "OPTIONS"])
    def ai_from_url():
        if request.method == "OPTIONS": return ("", 204)
        if os.environ.get("AI_IMPORT_ENABLED", "false").lower() not in {"1","true","yes","on"}:
            return jsonify(error="Die Link-Auswertung ist serverseitig deaktiviert."), 503
        payload = request.get_json(silent=True) or {}
        url = str(payload.get("url", "")).strip()
        if not url: return jsonify(error="URL fehlt."), 400
        try:
            result = import_from_url(url)
            return jsonify(result)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except AIProviderError as exc:
            return jsonify(error=str(exc)), 503
        except Exception:
            app.logger.exception("AI/link import failed")
            return jsonify(error="Die externe Seite konnte momentan nicht ausgewertet werden."), 502


    @app.route("/api/ai/from-text", methods=["POST", "OPTIONS"])
    def ai_from_text():
        if request.method == "OPTIONS": return ("", 204)
        if os.environ.get("AI_IMPORT_ENABLED", "false").lower() not in {"1","true","yes","on"}:
            return jsonify(error="Die KI-Auswertung ist serverseitig deaktiviert."), 503
        payload = request.get_json(silent=True) or {}
        prepared_text = str(payload.get("text", "")).strip()
        source_url = str(payload.get("source_url", "")).strip()
        if not prepared_text: return jsonify(error="Vorbereitete Importdaten fehlen."), 400
        try:
            return jsonify(import_from_text(prepared_text, source_url))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except AIProviderError as exc:
            return jsonify(error=str(exc)), 503
        except Exception:
            app.logger.exception("AI/prepared-text import failed")
            return jsonify(error="Die vorbereiteten Importdaten konnten momentan nicht ausgewertet werden."), 502


    @app.route("/api/ai/from-image", methods=["POST", "OPTIONS"])
    def ai_from_image():
        if request.method == "OPTIONS": return ("", 204)
        if os.environ.get("AI_IMPORT_ENABLED", "false").lower() not in {"1","true","yes","on"}:
            return jsonify(error="Die KI-Auswertung ist serverseitig deaktiviert."), 503
        uploads = request.files.getlist("images")
        if not uploads:
            one = request.files.get("image")
            uploads = [one] if one else []
        if not uploads:
            return jsonify(error="Bitte mindestens einen Screenshot auswählen."), 400
        if len(uploads) > 4:
            return jsonify(error="Maximal 4 Screenshots gleichzeitig."), 400
        source_url = str(request.form.get("source_url", "")).strip()
        image_bytes = []
        total = 0
        for uploaded in uploads:
            content = uploaded.stream.read(10 * 1024 * 1024 + 1)
            if len(content) > 10 * 1024 * 1024:
                return jsonify(error=f"{uploaded.filename or 'Bild'} ist größer als 10 MB."), 400
            total += len(content)
            if total > 30 * 1024 * 1024:
                return jsonify(error="Die Bilder sind zusammen größer als 30 MB."), 400
            image_bytes.append(content)
        try:
            return jsonify(import_from_images(image_bytes, source_url))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except AIProviderError as exc:
            return jsonify(error=str(exc)), 503
        except Exception:
            app.logger.exception("AI/image import failed")
            return jsonify(error="Die Screenshots konnten momentan nicht ausgewertet werden."), 502


    @app.route("/api/ai/rules-search", methods=["POST", "OPTIONS"])
    def ai_rules_search():
        if request.method == "OPTIONS": return ("", 204)
        if os.environ.get("AI_IMPORT_ENABLED", "false").lower() not in {"1","true","yes","on"}:
            return jsonify(error="Die Link-/KI-Funktionen sind serverseitig deaktiviert."), 503
        payload = request.get_json(silent=True) or {}
        game = payload.get("game") or {}
        try:
            return jsonify(search_official_rules(game))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        except AIProviderError as exc:
            return jsonify(error=str(exc)), 503
        except Exception:
            app.logger.exception("official rules search failed")
            return jsonify(error="Die offizielle Anleitung konnte momentan nicht gesucht werden."), 502

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def frontend(path):
        if path.startswith("api/"):
            return jsonify(error="API-Endpunkt nicht gefunden."), 404
        candidate = STATIC_DIR / path
        if path and candidate.is_file():
            return send_from_directory(STATIC_DIR, path)
        return send_from_directory(STATIC_DIR, "index.html")

    @app.errorhandler(413)
    def too_large(_): return jsonify(error="Anfrage ist zu groß."), 413

    return app


app = create_app()

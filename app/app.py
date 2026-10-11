import os
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, send_file
from io import BytesIO

from . import db, attachments
from .ai_import import import_from_url, import_from_text, import_from_images, search_official_rules
from .ai_provider import AIProviderError, provider_public_config, provider_status

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"


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
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        origin = request.headers.get("Origin")
        allowed = os.environ.get("PWA_ALLOWED_ORIGIN", "").rstrip("/")
        if origin and allowed and origin.rstrip("/") == allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, CF-Access-Client-Id, CF-Access-Client-Secret"
            response.headers["Access-Control-Max-Age"] = "600"
        return response

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify(status="ok")

    @app.route("/api/config", methods=["GET", "OPTIONS"])
    def api_config():
        if request.method == "OPTIONS": return ("", 204)
        ai_enabled = os.environ.get("AI_IMPORT_ENABLED", "false").lower() in {"1","true","yes","on"}
        public_ai = provider_public_config()
        return jsonify(
            title=os.environ.get("APP_TITLE", "Brettspielregal"),
            version="7.0.0",
            app_url=os.environ.get("APP_URL", ""),
            ai_import_enabled=ai_enabled,
            rules_search_enabled=ai_enabled,
            **public_ai,
        )


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
        payload["id"] = str(uuid.uuid4())
        try: game = db.normalize_game(payload)
        except ValueError as exc: return jsonify(error=str(exc)), 400
        db.save_game(game)
        return jsonify(game), 201

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
        response = send_file(BytesIO(content), mimetype=meta["mime_type"], as_attachment=True,
                             download_name=meta["filename"], max_age=0)
        response.headers["Cache-Control"] = "private, no-store"
        return response

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

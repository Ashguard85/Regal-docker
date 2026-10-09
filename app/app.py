import os
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from . import db
from .ai_import import import_from_url, search_official_rules
from .ai_provider import AIProviderError, provider_public_config, provider_status

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"


def create_app(test_config=None):
    app = Flask(__name__, static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=4 * 1024 * 1024, SECRET_KEY=os.environ.get("SECRET_KEY", "change-me"))
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
            version="4.0.0",
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
        if request.method == "DELETE": db.delete_game(game_id); return jsonify(status="deleted")
        payload = request.get_json(silent=True) or {}
        payload["id"] = game_id
        try: game = db.normalize_game(payload, existing)
        except ValueError as exc: return jsonify(error=str(exc)), 400
        game["id"] = game_id
        db.save_game(game)
        return jsonify(game)

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

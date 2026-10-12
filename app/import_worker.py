import os
import signal
import time
import threading

from . import db
from .ai_import import import_from_research
from .ai_provider import AIProviderError
from .research_search import ResearchSearchError, research_game

RUNNING = True
CURRENT_MESSAGE = "Worker gestartet"


def _stop(*_args):
    global RUNNING
    RUNNING = False


def _set_message(message):
    global CURRENT_MESSAGE
    CURRENT_MESSAGE = str(message)[:1000]
    db.set_runtime_state("import_worker", CURRENT_MESSAGE)


def _heartbeat_loop():
    while RUNNING:
        try:
            db.set_runtime_state("import_worker", CURRENT_MESSAGE)
        except Exception:
            pass
        time.sleep(10)


def _env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _poll_seconds():
    try:
        return min(max(int(os.environ.get("AUTO_ENRICH_POLL_SECONDS", "5")), 2), 60)
    except ValueError:
        return 5


def process_job(job):
    job_id = job["id"]
    game = db.get_game(job["game_id"])
    if not game:
        db.update_import_job(job_id, status="failed", progress="Spiel nicht mehr vorhanden", error="Spiel wurde gelöscht.", finished=True)
        return

    db.update_import_job(job_id, progress="Suche passende Quellen im Internet …")
    research = research_game(job["query"])
    db.update_import_job(job_id, progress=f"{len(research['sources'])} Quellen gefunden; Ollama wertet die Daten aus …", sources=research["sources"])
    result = import_from_research(job["query"], game, research["evidence"], research["sources"])
    proposal = result["game"]
    proposal["id"] = game["id"]
    normalized = db.normalize_game(proposal, game)
    normalized["id"] = game["id"]
    db.save_game(normalized)

    warnings = result.get("warnings") or []
    useful = sum(1 for key in ("description", "publisher", "year", "designer", "ean", "cover_url", "rules_url", "min_players", "play_time_min", "min_age") if normalized.get(key) not in (None, "", []))
    status = "review" if warnings or useful < 3 else "done"
    progress = "Automatisch ergänzt – bitte kurz prüfen" if status == "review" else "Automatisch ergänzt"
    db.update_import_job(job_id, status=status, progress=progress, error="", warnings=warnings, sources=research["sources"], finished=True)


def run():
    db.init_db()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    poll = _poll_seconds()
    _set_message("Worker gestartet")
    heartbeat = threading.Thread(target=_heartbeat_loop, name="worker-heartbeat", daemon=True)
    heartbeat.start()
    while RUNNING:
        if not _env_bool("AUTO_ENRICH_ENABLED", True) or not _env_bool("AI_IMPORT_ENABLED", False):
            _set_message("Worker aktiv; automatische Ergänzung/KI ist deaktiviert")
            time.sleep(poll)
            continue
        job = db.claim_import_job()
        if not job:
            _set_message("Bereit – keine wartenden Aufträge")
            time.sleep(poll)
            continue
        _set_message(f"Verarbeitet: {job['query'][:120]}")
        try:
            process_job(job)
        except ResearchSearchError as exc:
            if int(job.get("attempts") or 0) < 3:
                db.update_import_job(job["id"], status="queued", progress="Websuche vorübergehend nicht erreichbar – erneuter Versuch", error=str(exc))
                time.sleep(min(20, poll * 2))
            else:
                db.update_import_job(job["id"], status="failed", progress="Automatische Websuche fehlgeschlagen", error=str(exc), finished=True)
        except (AIProviderError, ValueError) as exc:
            db.update_import_job(job["id"], status="failed", progress="Automatische Ergänzung fehlgeschlagen", error=str(exc), finished=True)
        except Exception as exc:
            db.update_import_job(job["id"], status="failed", progress="Unerwarteter Fehler im Worker", error=f"{type(exc).__name__}: {exc}", finished=True)
        finally:
            _set_message("Bereit")
    _set_message("Worker beendet")


if __name__ == "__main__":
    run()

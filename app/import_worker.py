import fcntl
import multiprocessing
import os
import signal
import time
import threading
import re
import unicodedata
from urllib.parse import urlparse

from . import db
from .ai_import import import_from_research
from .ai_provider import AIProviderError
from .research_search import ResearchSearchError, research_game
from .evidence import build_field_evidence

RUNNING = True
CURRENT_MESSAGE = "Worker gestartet"
LAST_LOG_MESSAGE = None


def _stop(*_args):
    global RUNNING
    RUNNING = False


def _set_message(message):
    global CURRENT_MESSAGE, LAST_LOG_MESSAGE
    CURRENT_MESSAGE = str(message)[:1000]
    db.set_runtime_state("import_worker", CURRENT_MESSAGE)
    if CURRENT_MESSAGE != LAST_LOG_MESSAGE:
        print(f"[worker] {CURRENT_MESSAGE}", flush=True)
        LAST_LOG_MESSAGE = CURRENT_MESSAGE


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


def _job_timeout_seconds():
    try:
        return min(max(int(os.environ.get("AUTO_ENRICH_JOB_TIMEOUT_SECONDS", "900")), 120), 3600)
    except ValueError:
        return 900


def _job_cancelled(job_id):
    current = db.get_import_job(job_id)
    if not current:
        return True
    if current.get("status") == "cancelled":
        return True
    if current.get("cancel_requested"):
        db.finalize_cancel_import_job(job_id, "Abbruch abgeschlossen")
        return True
    return False


def process_job(job):
    job_id = job["id"]
    if _job_cancelled(job_id):
        return
    game = db.get_game(job["game_id"])
    if not game:
        db.update_import_job(job_id, status="failed", progress="Spiel nicht mehr vorhanden", error="Spiel wurde gelöscht.", finished=True)
        return

    _set_message(f"Suche Quellen: {job['query'][:120]}")
    db.update_import_job(job_id, progress="Suche passende Quellen im Internet …")
    research = research_game(job["query"], game)
    if _job_cancelled(job_id):
        return

    _set_message(f"{len(research['sources'])} Quellen gefunden; Ollama: {job['query'][:90]}")
    identity = (research.get("research") or {}).get("identity")
    # Ohne BGG-API-Key: nur einen eindeutig passenden, tatsächlich geladenen
    # BoardGameGeek-Spiel-Link als ID-Anker nutzen, niemals einen beliebigen
    # SearXNG-Snippet. Erweiterungs-Slugs werden nicht als Grundspiel erkannt.
    if not identity and not game.get("bgg_id"):
        def slug(value):
            text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
            return re.sub(r"[^a-z0-9]+", "-", text).strip("-")
        for url in research.get("sources") or []:
            parsed = urlparse(url)
            if (parsed.hostname or "").lower().removeprefix("www.") != "boardgamegeek.com":
                continue
            match = re.fullmatch(r"/boardgame/(\d+)/([^/]+)/?", parsed.path)
            if match and slug(match.group(2)) == slug(game.get("title")):
                identity = {"bgg_id": int(match.group(1)), "score": 90, "title": game["title"]}
                break
    if identity and identity.get("bgg_id") and not game.get("bgg_id") and int(identity.get("score") or 0) >= 90:
        updated = db.normalize_game({"bgg_id": identity["bgg_id"]}, game)
        updated["id"] = game["id"]
        db.save_game(updated)
        game = db.get_game(game["id"])
    identity_text = f" · BGG: {identity.get('title')} ({identity.get('score')} %)" if identity else ""
    db.update_import_job(
        job_id,
        progress=f"{len(research['sources'])} gute Quellen ausgewählt; Ollama wertet die Daten aus …{identity_text}",
        sources=research["sources"],
        research=research.get("research") or {},
    )
    if _job_cancelled(job_id):
        return

    result = import_from_research(job["query"], game, research["evidence"], research["sources"])
    if _job_cancelled(job_id):
        return

    proposal = result["game"]
    proposal["id"] = game["id"]
    normalized = db.normalize_game(proposal, game)
    normalized["id"] = game["id"]

    # KI-Daten werden niemals direkt in games geschrieben. Sie bleiben als
    # temporäre Feldvorschläge, bis der Benutzer sie ausdrücklich übernimmt.
    field_evidence = build_field_evidence(normalized, research.get("_field_source_bundles") or [])
    suggestion_count = db.replace_import_suggestions(
        job_id, game["id"], normalized, game, field_evidence=field_evidence
    )
    if _job_cancelled(job_id):
        return

    warnings = result.get("warnings") or []
    if suggestion_count:
        progress = f"{suggestion_count} KI-Vorschlag{' ist' if suggestion_count == 1 else 'e sind'} zur Prüfung bereit"
        db.update_import_job(job_id, status="review", progress=progress, error="", warnings=warnings, sources=research["sources"], research=research.get("research") or {}, finished=True)
        if not _job_cancelled(job_id):
            db.auto_approve_import_suggestions(job_id)
        _set_message(f"Vorschläge bereit ({suggestion_count}): {game.get('title') or job['query']}")
    else:
        progress = "Recherche abgeschlossen – keine neuen Angaben gefunden"
        db.update_import_job(job_id, status="verified", progress=progress, error="", warnings=warnings, sources=research["sources"], research=research.get("research") or {}, finished=True)
        _set_message(f"Keine neuen Vorschläge: {game.get('title') or job['query']}")


def _execute_job(job):
    # The supervisor must be able to terminate this process. Do not inherit the
    # parent's graceful SIGTERM handler, otherwise a blocked HTTP request would
    # continue after terminate().
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    try:
        process_job(job)
    except ResearchSearchError as exc:
        if int(job.get("attempts") or 0) < 3:
            db.update_import_job(job["id"], status="queued", progress="Websuche vorübergehend nicht erreichbar – erneuter Versuch", error=str(exc))
        else:
            db.update_import_job(job["id"], status="failed", progress="Automatische Websuche fehlgeschlagen", error=str(exc), finished=True)
    except (AIProviderError, ValueError) as exc:
        db.update_import_job(job["id"], status="failed", progress="Automatische Ergänzung fehlgeschlagen", error=str(exc), finished=True)
    except Exception as exc:
        db.update_import_job(job["id"], status="failed", progress="Unerwarteter Fehler im Worker", error=f"{type(exc).__name__}: {exc}", finished=True)


def _terminate_job_process(proc):
    if not proc.is_alive():
        return
    proc.terminate()
    proc.join(timeout=3)
    if proc.is_alive():
        try:
            proc.kill()
        except AttributeError:
            pass
        proc.join(timeout=3)


def _run_claimed_job(job):
    """Run one job in a child process so a stuck network/Ollama call is killable."""
    # Use spawn rather than fork: the worker also owns a heartbeat thread and
    # forking a multithreaded Python process is unsafe.
    ctx = multiprocessing.get_context("spawn")
    proc = ctx.Process(target=_execute_job, args=(job,), name=f"import-{job['id'][:8]}")
    proc.start()
    deadline = time.monotonic() + _job_timeout_seconds()

    while proc.is_alive() and RUNNING:
        current = db.get_import_job(job["id"])
        if not current:
            _terminate_job_process(proc)
            return
        if current.get("status") == "cancelled" or current.get("cancel_requested"):
            _terminate_job_process(proc)
            db.finalize_cancel_import_job(job["id"], "Abbruch abgeschlossen")
            _set_message(f"Abgebrochen: {job['query'][:100]}")
            return
        if time.monotonic() >= deadline:
            _terminate_job_process(proc)
            db.update_import_job(
                job["id"],
                status="failed",
                progress="Zeitlimit überschritten",
                error=f"Der Hintergrundauftrag wurde nach {_job_timeout_seconds() // 60} Minuten beendet.",
                finished=True,
            )
            _set_message(f"Zeitlimit: {job['query'][:100]}")
            return
        time.sleep(1)

    if not RUNNING:
        _terminate_job_process(proc)
        current = db.get_import_job(job["id"])
        if current and current.get("status") == "running":
            # Leave the job recoverable; claim_import_job will requeue it after
            # the stale window on the next worker start.
            _set_message("Worker wird beendet; laufender Auftrag bleibt wiederaufnehmbar")
        return

    proc.join(timeout=1)
    current = db.get_import_job(job["id"])
    if current and current.get("status") == "running":
        db.update_import_job(
            job["id"],
            status="failed",
            progress="Worker-Unterprozess unerwartet beendet",
            error=f"Unterprozess endete mit Code {proc.exitcode}.",
            finished=True,
        )


def run():
    # Keep a shared lock for the worker lifetime. Full ZIP restore needs an
    # exclusive lock at container startup, so it waits until old worker stops.
    db.DATA_DIR.mkdir(parents=True, exist_ok=True)
    restore_guard = open(db.DATA_DIR / "restore.lock", "a+b")
    fcntl.flock(restore_guard, fcntl.LOCK_SH)
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
        _run_claimed_job(job)
        _set_message("Bereit")
    _set_message("Worker beendet")


if __name__ == "__main__":
    run()

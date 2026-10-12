# Testbericht – Brettspielregal v8.1.0

## Automatisch geprüft

- Python-Syntax aller geänderten Backend-Module (`py_compile`)
- JavaScript-Syntax (`node --check`) für `app.js`, `providers.js`, `db.js` und `service-worker.js`
- HTML/JS-DOM-Abgleich: 101 per JavaScript referenzierte IDs, keine fehlenden IDs
- CSS mit `tinycss2`: 271 Regeln, 0 Parserfehler
- Docker-Frontend wurde erneut nach `app/static` gebaut
- Service Worker: `brettspielregal-pwa-v8-1`
- Portainer-/Compose-Datei enthält `app`, `worker`, `searxng`, `pull_policy: build` und deaktivierten Worker-HTTP-Healthcheck

## Python-Tests ohne Flask-Abhängigkeit

**26 bestanden.** Abgedeckt sind unter anderem:

- bestehende AI-/Ollama-Extraktion
- Text- und Vision-Modellkonfiguration
- SQLite-Migrationen bis Schema 4
- Backup-Kompatibilität
- Attachment-Storage
- persistente Import-Queue
- atomisches Claiming eines Jobs
- Vermeidung doppelter aktiver Jobs
- Titel-/EAN-Wiederverwendung bei Schnellerfassung
- SearXNG-JSON-Auswertung und HTTPS-Filter
- Background-Worker aktualisiert Spiele und Jobstatus
- neuer Review→Verified-Workflow
- Ablehnung einer Bestätigung für nicht prüfbare Queue-Zustände

## Flask-Integrationstests

Im Repository liegen 7 Flask-API-/Attachment-Tests. In der aktuellen Ausführungsumgebung konnten sie nicht gestartet werden, weil Flask dort nicht installiert ist (`ModuleNotFoundError: flask`). Das ist kein festgestellter Codefehler; im Docker-Build wird Flask regulär aus `requirements.txt` installiert.

## Nicht live getestet

- echter Docker-/Portainer-Start
- echte SearXNG-Suche gegen externe Suchmaschinen
- echte Ollama-Inferenz mit `qwen3:14b`/`gemma3:12b`
- iPhone-PWA auf physischer Hardware

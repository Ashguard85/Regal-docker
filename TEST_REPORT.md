# Testbericht – Brettspielregal v8.0.0

## Automatisch geprüft

- Python-Syntax aller Backend-Module (`py_compile`)
- JavaScript-Syntax (`node --check`) für `app.js`, `providers.js`, `db.js`, `config.js`, `service-worker.js`
- HTML/JS-DOM-Abgleich: 107 referenzierte/definierte IDs, keine fehlenden oder doppelten IDs
- CSS mit `tinycss2`: 246 Regeln, 0 Parserfehler
- `manifest.webmanifest`: gültiges JSON
- Docker-/Pages-/Docker-static Frontend-Parität für alle gemeinsamen Dateien
- Docker-Compose-Beispiel: YAML erfolgreich geparst; Services `app`, `worker`, `searxng`
- Service Worker: `brettspielregal-pwa-v8`

## Python-Tests ohne Flask-Abhängigkeit

**24 bestanden.** Abgedeckt sind unter anderem:

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
- hilfreicher Fehler bei deaktiviertem SearXNG-JSON-Format
- Background-Worker aktualisiert Spiele und Jobstatus
- Research→Ollama-Merge erhält vorhandene Nutzerdaten

## Flask-Integrationstests

Im Repository liegen **7 Flask-API-Tests**, inklusive v8-Schnellerfassungs-/Queue-Endpunkt.

In der aktuellen Build-Umgebung konnten sie nicht gestartet werden, weil Flask nicht vorinstalliert ist. Ein Versuch, die Requirements in eine isolierte venv zu installieren, scheiterte an deaktivierter DNS/Internet-Auflösung der Ausführungsumgebung (`pip` konnte PyPI nicht erreichen). Das ist kein festgestellter Codefehler. Im Docker-Build wird Flask aus `requirements.txt` installiert.

Gesamter lokaler Pytest-Lauf in dieser Umgebung: **24 passed, 7 nicht ausführbar wegen `ModuleNotFoundError: flask`**.

## Nicht live getestet

- echter Docker-/Portainer-Start
- echte SearXNG-Suche gegen externe Suchmaschinen
- echte Ollama-Inferenz mit `qwen3:14b`/`gemma3:12b`
- iPhone-PWA auf physischer Hardware

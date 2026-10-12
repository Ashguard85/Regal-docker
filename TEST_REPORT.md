# Testbericht – Brettspielregal v8.2.0

## Automatisch geprüft

- Python-Syntax aller Backend-Module (`py_compile`)
- JavaScript-Syntax (`node --check`) für `app.js`, `providers.js`, `db.js`, `config.js` und `service-worker.js`
- HTML/JS-DOM-Abgleich: 109 per JavaScript referenzierte IDs, keine fehlenden IDs
- CSS mit `tinycss2`: 271 Regeln, 0 Parserfehler
- Manifest JSON validiert
- Docker-Frontend erneut nach `app/static` gebaut
- Docker-/Pages-Frontend-Parität geprüft (außer zielabhängiger `config.js`)
- Service Worker: `brettspielregal-pwa-v8-2`
- Portainer-/Compose-YAML geparst; Services `app`, `worker`, `searxng` vorhanden

## Python-Kern-/Worker-Tests ohne Flask-Abhängigkeit

**29 bestanden.** Abgedeckt sind unter anderem:

- bestehende AI-/Ollama-Extraktion
- Text- und Vision-Modellkonfiguration
- SQLite-Migrationen bis Schema 5
- persistente Backend-Rechercheeinstellungen
- Validierung der Prompt-Pflicht-Platzhalter
- Primär-/Low-Trust-Domain-Normalisierung
- GTIN/EAN-Prüfziffer und Ablehnung `0000000000000`
- Schutz des vom Benutzer erfassten Spieltitels vor Review-/Seitentiteln
- Ablehnung von Review-/Fazit-Text als Kurzregeln
- Backup-Kompatibilität der Spieldaten
- Attachment-Storage
- persistente Import-Queue
- atomisches Claiming eines Jobs
- Vermeidung doppelter aktiver Jobs
- Titel-/EAN-Wiederverwendung bei Schnellerfassung
- SearXNG-JSON-Auswertung und HTTPS-Filter
- Background-Worker aktualisiert Spiele und Jobstatus
- Review→Verified-Workflow

## Flask-Integrationstests

Im Repository liegen **8 Flask-API-/Attachment-Tests**. In der aktuellen Ausführungsumgebung konnten sie nicht gestartet werden, weil Flask dort nicht installiert ist (`ModuleNotFoundError: flask`). Im Docker-Build wird Flask regulär aus `requirements.txt` installiert.

## Nicht live getestet

- echter Docker-/Portainer-Start
- echte SearXNG-Suche gegen externe Suchmaschinen
- echte Ollama-Inferenz mit `qwen3:14b`/`gemma3:12b`
- externe Asset-Probes gegen reale Cover/PDF-CDNs
- iPhone-PWA auf physischer Hardware

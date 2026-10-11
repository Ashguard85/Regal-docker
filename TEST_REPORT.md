# Testbericht – Brettspielregal v7.0.0

## Erfolgreich geprüft

- JavaScript-Syntax: `app.js`, `providers.js`, `service-worker.js`
- Python-Syntax: alle Module unter `app/`
- DOM-Abgleich: alle per `$()` referenzierten IDs sind in `index.html` vorhanden
- Docker `frontend/` ↔ `app/static/` Parität (außer zielabhängiger `config.js`)
- Docker ↔ GitHub-Pages-Frontend Parität der gemeinsamen Dateien
- Service Worker: `brettspielregal-pwa-v7`
- Separates Textmodell (`OLLAMA_TEXT_MODEL`) und Vision-Modell (`OLLAMA_VISION_MODEL`)
- Ollama-Vision-Anfrage enthält `images` und verwendet das konfigurierte Vision-Modell
- Magic-/Textimport und Screenshot-Import verwenden keinen direkten Abruf der gespeicherten Quell-URL
- Anhang-/Backup-/Datenbanktests im verfügbaren Testumfang

## Pytest

17 Tests bestanden:

```text
17 passed
```

Geprüfte Bereiche: AI-Import, AI-Provider, Vision-Modell, Datenbank-Migration/Import und Dateispeicher.

Die 6 Flask-basierten API-/Integrations-Tests konnten in dieser Build-Umgebung nicht gestartet werden, weil das Python-Paket `flask` hier nicht installiert ist (`ModuleNotFoundError: No module named 'flask'`). Das Docker-Image installiert Flask regulär über `requirements.txt`.

## Nicht als echter Integrationstest ausgeführt

- realer Ollama-Host mit `qwen3:14b`
- realer Ollama-Host mit `gemma3:12b`
- echtes Portainer-Deployment
- iPhone/PWA auf physischem Gerät

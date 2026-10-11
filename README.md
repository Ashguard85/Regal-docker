# Brettspielregal – Docker Fullstack v7.0.0

Brettspiel-Sammlung als responsive PWA mit Docker/Flask/SQLite, Dateianhängen und lokalem Ollama. **Docker v7 und GitHub Pages v7 gehören zusammen.**

## Neu in v7: zwei lokale Ollama-Modelle

- **Text-/Link-Import:** standardmäßig `qwen3:14b`.
- **Screenshot-/Bild-Import:** standardmäßig `gemma3:12b` über Ollama Vision.
- In „Spiel erfassen / bearbeiten“ gibt es **Screenshot auslesen**. Bis zu 4 JPG/PNG/WebP-Bilder können gemeinsam ausgewertet werden.
- Produktlinks, die der Server wegen HTTP 403 nicht abrufen kann (z. B. manche Shopseiten), können über einen vorbereiteten **Magic Import Link** oder über Screenshots importiert werden. Die App versucht nicht, den Bot-Schutz des Shops zu umgehen.
- Magic Import Links verwenden `#import=<base64url-json>` mit Version 1. Im Server-Modus wird der enthaltene Text mit Ollama strukturiert; optionale Fallback-Daten funktionieren auch ohne KI.
- Bilder für die KI-Auswertung werden nur transient an dein lokales Ollama gesendet und von der Importfunktion nicht gespeichert. Normale Bilder/PDF-Anleitungen bleiben wie in v6 als Anhänge speicherbar.

## Ollama vorbereiten

Auf dem Rechner, auf dem Ollama läuft:

```bash
ollama pull qwen3:14b
ollama pull gemma3:12b
ollama list
```

Gemma 3 Vision benötigt eine aktuelle Ollama-Version. Danach sollte `ollama list` beide Modelle zeigen.

### Empfohlene Portainer-Variablen

```yaml
AI_IMPORT_ENABLED: "true"
AI_PROVIDER: "ollama"
OLLAMA_BASE_URL: "http://host.docker.internal:11434"
OLLAMA_TEXT_MODEL: "qwen3:14b"
OLLAMA_VISION_MODEL: "gemma3:12b"
OLLAMA_TIMEOUT_SECONDS: "600"
AI_MAX_PAGE_CHARS: "16000"
RULE_SEARCH_PROVIDER: "none"
WEB_FALLBACK_PROVIDER: "none"
```

`OLLAMA_MODEL` wird aus Kompatibilitätsgründen weiterhin als Alias für das Textmodell akzeptiert. Für neue Installationen `OLLAMA_TEXT_MODEL` verwenden.

## Nutzung des Screenshot-Imports

1. Spiel hinzufügen oder bearbeiten.
2. Optional den ursprünglichen Produktlink bei **Quell-Link** eintragen. Er wird beim Screenshot-Import nur gespeichert, nicht abgerufen.
3. **Screenshot auslesen** drücken.
4. 1–4 Screenshots oder Fotos als JPG, PNG oder WebP auswählen (max. 10 MB pro Bild, zusammen max. 30 MB).
5. Gemma 3 liest die sichtbaren Angaben aus und zeigt eine Import-Vorschau.
6. **Vorschläge übernehmen** drücken und das Spiel speichern.

HEIC/HEIF ist weiterhin als normaler Spielanhang erlaubt, für die KI-Auswertung aber bewusst nicht freigeschaltet, weil die Ollama-Vision-Pipeline diese Formate nicht zuverlässig auf allen Hosts dekodiert. iPhone-Screenshots sind üblicherweise PNG und funktionieren direkt.

## KI-Verbindung prüfen

Unter **Setup → KI / Link-Auswertung → KI-Verbindung testen** zeigt v7 getrennt an, ob Textmodell und Bildmodell auf dem Ollama-Host vorhanden sind.

## Bestehende Bilder und PDF-Anleitungen

Die v6-Anhangsfunktion bleibt erhalten:

- JPG/JPEG, PNG, GIF, WebP, HEIC/HEIF und PDF
- bis 10 MB pro Datei
- maximal 15 Anhänge pro Spiel
- Bild als Cover auswählbar
- Docker: Dateien unter `/app/data/attachments/`
- Pages/Lokal: Dateien in IndexedDB
- JSON-Backup-Format Version 3 enthält Anhänge als Base64

## Update von v6 auf v7

1. Vorher JSON-Backup und bei Docker möglichst das komplette Datenvolume sichern.
2. v7 neu deployen und `/app/data` unverändert weiterverwenden. Für v7 ist **keine neue Datenbankmigration** nötig.
3. Beide Ollama-Modelle laden.
4. Docker und Pages gemeinsam auf v7 aktualisieren.
5. PWA neu öffnen; der Service Worker heißt `brettspielregal-pwa-v7`.

## Beispiel für Portainer / Docker Compose

```yaml
services:
  app:
    build:
      context: https://github.com/USER/brettspielregal.git#main
    ports:
      - "8190:8080"
    volumes:
      - /home/USER/docker/brettspielregal/data:/app/data
      - /home/USER/docker/brettspielregal/backups:/app/data/backups
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      APP_TITLE: "Brettspielregal"
      APP_URL: "http://192.168.1.127:8190"
      SECRET_KEY: "${SECRET_KEY}"
      PWA_ALLOWED_ORIGIN: "http://192.168.1.127:8190"
      BACKUP_KEEP: "50"
      AI_IMPORT_ENABLED: "true"
      AI_PROVIDER: "ollama"
      OLLAMA_BASE_URL: "http://host.docker.internal:11434"
      OLLAMA_TEXT_MODEL: "qwen3:14b"
      OLLAMA_VISION_MODEL: "gemma3:12b"
      OLLAMA_TIMEOUT_SECONDS: "600"
      AI_MAX_PAGE_CHARS: "16000"
      RULE_SEARCH_PROVIDER: "none"
      WEB_FALLBACK_PROVIDER: "none"
    restart: unless-stopped
```

Ollama-Port 11434 nicht öffentlich freigeben. Auf Linux muss Ollama Verbindungen aus dem Docker-Netz erreichen können.

## Neue API-Routen

- `POST /api/ai/from-text` – vorbereiteten Text strukturiert importieren.
- `POST /api/ai/from-image` – Multipart, Feld `images`, bis zu 4 JPG/PNG/WebP-Bilder; optional `source_url`.

Die bisherigen Routen und die Anhang-API bleiben unverändert.

## Tests

```bash
pip install -r requirements-dev.txt
PYTHONPATH=. pytest -q
```

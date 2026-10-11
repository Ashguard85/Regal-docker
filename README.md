# Brettspielregal – Docker Fullstack v6.0.0

Brettspiel-Sammlung als responsive PWA mit Docker/Flask/SQLite und optional Ollama. **Docker v6 und GitHub Pages v6 gehören zusammen.** Die bestehenden Funktionen aus v4/v5 (KI-/Link-Import, Backup, Suche, Regalansicht, Detailansicht) bleiben erhalten.

## Neu: Eigene Bilder und Anleitungen als Anhänge

- In **Spiel bearbeiten / Spiel erfassen** unter „Bilder und Anleitungen als Dateien“ Dateien auswählen. Bei einem neuen Spiel werden sie nach dem Speichern des Spiels hochgeladen.
- In der **Spiel-Detailansicht** lassen sich Dateien direkt hinzufügen, ansehen, herunterladen oder löschen. Ein hochgeladenes Bild kann als Cover markiert werden; das erste hochgeladene Bild wird sonst automatisch als Cover genutzt.
- **Dateitypen:** JPG/JPEG, PNG, GIF, WebP, HEIC/HEIF und PDF. Maximal **10 MB pro Datei**, **15 Anhänge pro Spiel**. HEIC/HEIF-Vorschauen hängen vom Browser ab; die Datei kann trotzdem gespeichert und heruntergeladen werden.
- Der bisherige externe Cover-Link und der Anleitungs-Link bleiben optional nutzbar. Lokale Cover-Dateien werden bevorzugt angezeigt.
- Die **Regalansicht** aus v5 ist weiterhin per Umschalter „Liste / Regal“ verfügbar.

## Speicherung und Backups

- **Docker/Server:** SQLite unter `/app/data/app.sqlite`, Anhänge unter `/app/data/attachments/` (Dateiname intern eine UUID). Den bestehenden Volume-Mount **nicht verändern** und für ein vollständiges Server-Backup **das gesamte `/app/data`-Verzeichnis** sichern.
- **Pages/Lokal:** Spiele und Anhang-Dateien in IndexedDB auf dem jeweiligen Gerät. Sie sind nicht automatisch auf anderen Geräten verfügbar.
- **JSON-Export:** Backup-Format `brettspielregal-backup`, **Version 3**, mit `data.games`, `data.attachments` und `data.settings`. Die Anhänge sind als Base64 enthalten. Export/Import sowie Lokal↔Server-Übertragungen übernehmen jetzt die Dateien. Backups werden dadurch deutlich größer.
- **Ältere Backups v1/v2** bleiben importierbar, enthalten aber noch keine Anhänge. „Zusammenführen“ behält vorhandene Anhänge, „Ersetzen“ entfernt den bisherigen Bestand einschließlich seiner Anhänge.
- Die rotierenden automatischen **SQLite**-Snapshots unter `/app/data/backups/` enthalten **keine Bild-/PDF-Dateien**. Für eine vollständige Wiederherstellung JSON-Export oder das gesamte Datenvolume sichern.
- Bei sehr vielen Anhängen kann die Größe des JSON-Imports das serverseitige Anfrage-Limit (100 MB) überschreiten. Große Sammlungen besser über das vollständige Docker-Datenvolume sichern.

## Update von v4/v5 auf v6

1. Vor dem Update ein JSON-Backup erstellen und bei Docker möglichst das komplette Datenvolume sichern.
2. Docker v6 neu deployen, den bestehenden Mount `/app/data` unverändert lassen. SQLite migriert automatisch von Schema 2 auf Schema 3.
3. Bei GitHub Pages das Pages-v6-Frontend deployen. Der IndexedDB-Speicher migriert automatisch von Version 2 auf 3.
4. PWA/Browser neu öffnen; der Service Worker verwendet `brettspielregal-pwa-v6`.
5. Docker v6 und Pages v6 gemeinsam verwenden. Pages v6 mit einem alten Backend kann keine Dateien hochladen.

## Deployment

Das Beispiel `docker-compose.example.yml` kann wie bisher für Portainer/Git verwendet werden. Wesentliche Werte:

```yaml
services:
  app:
    build:
      context: https://github.com/USER/brettspielregal.git#main
    ports:
      - "8090:8080"
    volumes:
      - /home/USER/docker/brettspielregal/data:/app/data
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      APP_TITLE: Brettspielregal
      APP_URL: https://api.example.com
      SECRET_KEY: ${SECRET_KEY}
      PWA_ALLOWED_ORIGIN: https://app.example.com
      BACKUP_KEEP: "50"
      AI_IMPORT_ENABLED: "true"
      AI_PROVIDER: ollama
      OLLAMA_BASE_URL: http://host.docker.internal:11434
      OLLAMA_MODEL: qwen3:8b
      RULE_SEARCH_PROVIDER: none
      WEB_FALLBACK_PROVIDER: none
    restart: unless-stopped
```

Liegt der Docker-Code im Repository-Unterordner `docker`, beim Git-Build `#main:docker` verwenden. Ollama bleibt ausschließlich serverseitig; Port `11434` nicht öffentlich freigeben.

## API-Erweiterung

Zusätzlich zu den bisherigen Routen:

- `GET|POST /api/games/<game_id>/attachments` – Metadaten bzw. Datei-Upload als Multipart-Formular (`file`)
- `GET|DELETE /api/games/<game_id>/attachments/<attachment_id>` – authentifizierter Download bzw. Löschen

Dateien werden über die API mit denselben Cloudflare-Access-Service-Token-Headern wie andere Serveranfragen abgerufen. Dateitypen werden anhand der tatsächlichen Dateisignatur geprüft; keine HTML-/Skript-Uploads. Die API selbst setzt weiterhin eine passende Zugriffsabsicherung am Reverse Proxy / Cloudflare Access voraus. `PWA_ALLOWED_ORIGIN` erlaubt exakt eine Pages-Origin.

## Tests

```bash
pip install -r requirements-dev.txt
PYTHONPATH=. pytest -q
```

Die bestehenden KI-/DB-Tests sowie neue Datei-/Backup-/API-Tests liegen unter `tests/`.

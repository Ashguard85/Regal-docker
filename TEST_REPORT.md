# Testbericht Brettspielregal v9.0.0

## Erfolgreich geprüft

- 73 nicht-Flask-basierte pytest-Tests bestanden (einschließlich der bestehenden Regressionstests und neuer v9-Tests für SQLite-Schema 11, BGG-ID, Lagerort-Massenänderung, Backup-Version 5, Downloadarchiv und WebP-Thumbnail).
- Python-Syntax aller `app/*.py`-Dateien.
- JavaScript-Syntax des geteilten Frontends und beider Builds.
- 152 statische UI-Referenzen gegen vorhandene DOM-IDs geprüft.
- PWA-Manifest, CSS-Parsing, Portainer-YAML.
- Docker/Pages-Parität für alle acht gemeinsam genutzten Frontend-Dateien.
- Service-Worker-Cache-Version v9.0.0.
- ZIP-Integrität und Paketinhalt.

## Nicht geprüft / Einschränkungen

- Acht bestehende Flask-basierte API-/Attachment-Integrationstests konnten mangels installiertem Flask in dieser Build-Umgebung nicht ausgeführt werden.
- Kein vollständiger Laufzeittest mit realem Portainer-Deployment, Cloudflare, Ollama/BGG, externen Bildhosts oder installiertem iPhone-Safari-PWA-Client.
- Externe Anbieter können Downloads durch HTTP 403, CORS oder andere Beschränkungen verhindern.
- Browserarchivierung im lokalen Pages-Modus setzt externe CORS-Freigabe voraus; manueller Upload bleibt verfügbar.

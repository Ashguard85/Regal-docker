# Testbericht – Brettspielregal v10.0.0

## Lokal ausgeführt

- 101 Python-Tests **ohne Flask** bestanden, darunter neue v10-Tests für Schema 13, verknüpfte Erweiterungen, ungültige Beziehungen, Backup-Roundtrip, BGG-Link-IDs und unverifizierte SearXNG-Regel-Kandidaten.
- Node.js JavaScript-Tests für Duplikate, Editionen und zufällige/filtrierte Spielauswahl bestanden.
- Bestehende EAN-Decoder-Tests bestanden.
- JavaScript-Syntax, Python-Compile, gemeinsame Docker-/Pages-Frontend-Dateien, CSS, HTML-ID-Prüfung, YAML und ZIP-Integrität werden beim Release geprüft.

## Enthalten, aber in dieser Build-Umgebung nicht als grüner Browserlauf nachgewiesen

- `tests/pwa_v10.spec.mjs` und `playwright.config.mjs`: automatisierte mobile **Chromium + WebKit**-Regressionen für lokale Erfassung, Editor, Picker und PWA-Offline.
- GitHub Actions `.github/workflows/pwa-regression.yml` führt die Tests in einer passenden Browser-Umgebung aus.
- Ein lokaler Chromium-CDP-Versuch konnte hier aufgrund einer Verbindungsbeschränkung nicht bis zur App-Navigation gelangen. Er wird **nicht** als bestanden gewertet.
- Bestehende Flask-API-Integrationstests benötigen `flask`, das hier nicht installiert ist. Ein echter iPhone-/Kamera-/Portainer-Test muss nach dem Deploy erfolgen.

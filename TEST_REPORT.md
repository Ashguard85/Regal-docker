# Testbericht – Brettspielregal v6.0.0

- `node --check` für `app.js`, `providers.js`, `db.js`, `config.js`, `service-worker.js`: bestanden.
- HTML/JavaScript-ID-Abgleich: keine fehlenden Elemente.
- Python-Tests ohne Flask (KI, Provider, SQLite-Migration, Backup, Anhänge): **13 bestanden**.
- Direkter Test von SQLite-Upload-Metadaten, Dateiablage, JSON-Export/Import, Merge und Replace: bestanden.
- Chromium-UI-Smoke-Test mit simuliertem Server: Liste, Regalansicht, Detaildialog, Bild- und PDF-Anhang, Datei hinzufügen, Cover wechseln, Datei löschen und Bearbeiten; keine JavaScript-Ausnahme.
- Node-Smoke-Test des LocalProvider mit simuliertem IndexedDB-Speicher: Dateien hinzufügen, herunterladen, Export/Import (v3), Legacy-Merge/Replace und ungültige Dateitypen; bestanden.
- Neue Flask-API-Tests für Datei-Upload, Download, Löschen und Backup sind enthalten, konnten in der aktuellen Testumgebung aber **nicht ausgeführt** werden, da Flask hier nicht installiert und ein Paketdownload nicht verfügbar ist. Vor Produktivbetrieb bitte mit `pip install -r requirements-dev.txt && PYTHONPATH=. pytest -q` ausführen.
- Docker und Pages erhalten identische Frontend-Dateien außer der zielabhängigen `config.js`.

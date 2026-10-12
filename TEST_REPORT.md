# Test Report – v8.5.0

## Ausgeführt

- Python `py_compile` für Backendmodule
- JavaScript `node --check` für Frontendmodule
- DOM-ID-Abgleich zwischen `index.html` und `app.js`
- Backend-Kerntests ohne Flask: **36 bestanden**

Die Tests decken u. a. ab:

- Datenbankmigration bis Schema 6
- Backupformat 4 und Altimporte
- Datei-/Anhangsspeicher
- Queue und Worker
- KI-Recherche und Qualitätsregeln
- persistente Recherchekonfiguration
- BoardGameGeek als Referenzquelle
- deutsche kontrollierte Tags und Synonym-Normalisierung
- Lagerort
- temporäre KI-Vorschläge
- Feld-für-Feld-Übernahme/Verwerfen ohne vorheriges Überschreiben
- KI-Opt-out-Pfade in API/Frontend statisch geprüft
- iPhone-Textskalierung (`text-size-adjust`, 16-px-Formfelder) geprüft

## Nicht in dieser Build-Umgebung ausführbar

Die Flask-Integrationstests (`test_app.py`, `test_attachments_v6.py`) benötigen die Runtime-Abhängigkeit Flask. Flask ist in dieser Ausführungsumgebung nicht installiert. Im Docker-Image wird Flask regulär über `requirements.txt` installiert.

Es wurden keine realen Requests an deinen Ollama-, SearXNG- oder Portainer-Host ausgeführt.

# Test Report – v8.7.0

## Ausgeführt

- **51** Kern-/DB-/Worker-/KI-/Recherche-/Tag-/CORS-Helfertests bestanden.
- Neue Tests für BGG-XML-Parsing, BGG-Identifikation, Kandidaten-Scoring, Snippet-Ausschluss und persistente Rechercheberichte.
- Python-Compile-Check für alle App-Module.
- JavaScript-Syntaxprüfung für Shared- und Docker-Frontend.
- DOM-ID-Abgleich zwischen `index.html` und `app.js`.
- CSS-Parsing ohne Fehler.
- Manifest-Parsing.
- Portainer-YAML erfolgreich geparst.
- Docker-/Pages-Parität der gemeinsam genutzten Frontenddateien geprüft.

## In dieser Build-Umgebung nicht ausführbar

8 Flask-basierte Integrationstests (API/Attachments) können hier nicht gestartet werden, weil Flask im bereitgestellten Python-Environment nicht installiert ist. Die Tests bleiben im Paket enthalten.

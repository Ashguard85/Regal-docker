# Testbericht – Brettspielregal v9.1.5

## Ergebnis

- **93 nicht-Flask-basierte Python-Tests bestanden**, darunter sechs neue v9.1.5-Tests für BGG-only-Quellenbegrenzung, Fehler ohne BGG-Zuordnung, direkten HTTPS-Link bei SearXNG-Ausfall, dauerhaftes Speichern der Einstellung, pro Auftrag gespeicherte Rechercheart und die UI-Fallback-Schaltfläche.
- **Node.js-Decoder-Test bestanden** – EAN-13, EAN-8, Drehung, Schräglage und Rauschfilter unverändert.
- Python-Compile, JavaScript-Syntax (inklusive Service Worker), DOM-ID-Prüfung (178 referenzierte IDs), Manifest, CSS und Compose-YAML: bestanden.
- Docker- und Pages-Shared-Frontend stimmen bis auf die absichtlich unterschiedlichen `config.js`-Dateien überein.
- ZIP-Archive: Integrität beim Packaging geprüft.
- Ergänzender Flask-Test für den expliziten Erstimport-Schalter vorhanden, in dieser Build-Umgebung nicht ausführbar.

## Ausführungsgrenzen

Die Flask-basierten API-/Attachment-Integrationstests konnten hier nicht gestartet werden, weil `flask` in dieser Build-Umgebung nicht installiert ist. Vor Ort ist zusätzlich ein Test mit einem gültigen BGG-Key und einem tatsächlichen BGG-API-Treffer sinnvoll. Die übrigen Funktionen wurden anhand der vorhandenen v9.1.4-Codebasis weiterentwickelt.

# Test Report – v8.8.2

## Ergebnis

- **68 nicht-Flask-basierte Tests bestanden.**
- Neuer Attachment-Test prüft, dass das erste Bild explizit als Cover gesetzt wird und die Migration eine ältere leere `cover_attachment_id` repariert.
- Datenbankmigration auf **Schema 10** repariert bestehende implizite Cover-Zuordnungen; Schema 9 enthält weiterhin `evidence_json`.
- Python-Compile für alle App-Module: bestanden.
- JavaScript-Syntax (`app.js`, `providers.js`, `service-worker.js`): bestanden.
- Frontend-Checks prüfen zusätzlich: Detailbilder werden ohne `IntersectionObserver` sofort geladen, der Dialog wird vor der Hydrierung geöffnet und der PWA-Cache wurde auf v8.8.2 angehoben.
- Docker-/Pages-Parität und ZIP-Integrität werden beim Packaging geprüft.

## Umgebungshinweis

Die **8 Flask-basierten API-/Attachment-Integrationstests** können in dieser Build-Umgebung nicht ausgeführt werden, weil das Python-Paket `flask` hier nicht installiert ist. Sie scheitern bereits beim Import mit `ModuleNotFoundError: flask`; die übrigen 68 Tests sind grün. Die Flask-Tests wurden für v8.8.2 zusätzlich um die erwartete `inline`-Auslieferung und die automatische Cover-Zuordnung ergänzt.


## v8.8.2 Zusatzchecks

- Sichtbare eigene Cover werden in der Sammlung sofort geladen, auch wenn Safari den `IntersectionObserver` verzögert.
- Scroll-/Resize-Fallback bleibt aktiv für später sichtbare Karten.
- Queue-Polling rendert die Sammlung nicht mehr alle 8 Sekunden neu.
- Wechsel zurück auf Sammlung stößt einen Render im sichtbaren Zustand an.

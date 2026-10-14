# Test Report – v8.8.3

## Ergebnis

- **69 nicht-Flask-basierte Tests bestanden.**
- Neuer Frontend-Test prüft, dass Server-Cover native Attachment-Bild-URLs verwenden und der authentifizierte Blob-Fallback erhalten bleibt.
- Python-Compile für alle App-Module: bestanden.
- JavaScript-Syntax (`app.js`, `providers.js`, `service-worker.js`, `config.js`): bestanden.
- Docker-Frontend wurde aus dem Shared-Frontend neu gebaut und auf Parität geprüft.
- PWA-Cache wurde auf v8.8.3 angehoben.

## Cover-Fix v8.8.3

Im Docker-/Same-Origin-Modus wird ein ausgewähltes eigenes Bild nicht mehr als Platzhalter mit anschließender JavaScript-Blob-Hydrierung gerendert. Stattdessen zeigt die Sammlung direkt auf den bestehenden sicheren Attachment-Endpunkt. Für GitHub Pages bzw. Serververbindungen mit expliziten Cloudflare-Service-Token-Headern bleibt die bisherige Blob-Lösung als Fallback aktiv.

## Umgebungshinweis

Die **8 Flask-basierten API-/Attachment-Integrationstests** können in dieser Build-Umgebung nicht ausgeführt werden, weil das Python-Paket `flask` hier nicht installiert ist. Sie scheitern bereits beim Import mit `ModuleNotFoundError: flask`. Die übrigen 69 Tests sind grün.

# Testbericht – Pages v9.1.5

- Gleicher Shared-Frontend-Code wie Docker, mit separater Pages-`config.js`.
- Die BGG-Einstellungsoption kommuniziert im Servermodus mit `/api/research-settings`.
- JavaScript-Syntax, Manifest, DOM-Referenzen, CSS und Pages-/Docker-Parität beim Release geprüft.
- Automatische BGG-Recherche wird nicht aus dem Browser heraus gestartet; sie läuft im Docker-Worker.

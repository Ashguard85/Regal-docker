# Testbericht – Brettspielregal v9.1.3

- **84 nicht-Flask-basierte Tests bestanden**, darunter die zwei neuen v9.1.3-Scrolltests.
- Zwei neue Tests sichern Scanner-Integration, Kamera-Abbruch und die Unabhängigkeit von Safaris `BarcodeDetector` ab.
- Node.js-Tests dekodieren EAN-13 und EAN-8, auch mit Drehung, unterschiedlichen Strichbreiten, Hintergrund und ungleichmäßiger Beleuchtung; ungültige Prüfziffern werden zurückgewiesen.
- Zusätzlich: JavaScript-Syntax, Python-Compile, PWA-Cache, DOM-Element-Referenzen und Docker-/Pages-Frontend-Gleichheit geprüft.
- **Nicht durchführbar:** echte iPhone-Kamera-End-to-End-Prüfung und Flask-basierte Integrationstests (Flask fehlt im Build-Container).


## v9.1.3: Regressionstest Bearbeitungsdialog

- Formular-Scrollcontainer und Dialog werden beim Öffnen eines vorhandenen Spiels auf Position 0 gesetzt.
- Fokussierung des Dialogtitels mit `preventScroll` verhindert iOS-Safari-Sprünge in das Titelfeld, auch bei geöffnetem Recherche-/KI-Bereich.
- Neu erfassen und Bearbeiten nutzen weiterhin denselben Dialog; nur der Autofokus beim Bearbeiten entfällt.

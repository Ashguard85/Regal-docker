# Testbericht – Brettspielregal v9.1.4

- **87 nicht-Flask-basierte Python-Tests bestanden**, einschließlich drei neuer Tests für nicht aufeinanderfolgende Scan-Treffer, Foto-Capture und PWA-Versionierung.
- Node.js-Decoder-Tests für synthetische EAN-13/EAN-8-Bilder einschließlich gedrehter und schräger Barcodes sowie Bildrauschen: bestanden.
- JS-Syntax und Python-Compile: bestanden.
- CSS-/Manifest-/Portainer-YAML-Prüfung, alle DOM-ID-Referenzen und Docker-/Pages-Frontend-Parität beim Packaging geprüft.
- **Nicht ausführbar:** Flask-Integrationstests (Flask-Paket fehlt in der Build-Umgebung) und echter Kamera-Test mit Safari/iPhone. Das praktische Erkennungsverhalten bleibt vor Ort zu prüfen.

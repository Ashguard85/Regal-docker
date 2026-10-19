# Test Report – v9.1.1

- **80 nicht-Flask-basierte Tests bestanden** (77 vorhandene und 3 zusätzliche UI-Trennungstests).
- Neue Tests verifizieren den Anzeigedialog ohne mutierende Aktionen; den Bearbeitungsdialog mit Archivieren, Cover-Auswahl, Löschen und KI-Freigabe; außerdem die Weiterleitung der Warteschlange in den Editor.
- Python-, JS-, CSS-, HTML-/DOM-, Manifest- und YAML-Checks sowie Docker-/Pages-Parität und ZIP-Integrität werden beim Release geprüft.
- **Nicht ausgeführt:** 8 Flask-Integrationstests (Flask ist in dieser Umgebung nicht installiert), kein echter iPhone-/Portainer-Laufzeittest.


- **77 nicht-Flask-basierte Tests bestanden** (73 aus v9.0 + vier zusätzliche v9.1-Regressionstests).
- ZIP: Manifest-Prüfsummen, Dateipfade, SQLite-Integrität, vollständiger Restore und Sicherheitsbackup geprüft.
- KI: Standard aus; nicht erlaubte Felder abgewiesen; `primary`-Belege werden freigegeben, Widersprüche nicht.
- UI-Quellcode: Kamera-Start/Stop, manueller EAN-Fallback, Offline-Lesemodus, Restore-/Diagnoseelemente vorhanden.
- Python- und JavaScript-Syntax, CSS, Manifest, YAML, DOM-ID-Verweise, Shared-Frontend-Parität und ZIP-Integrität werden vor Paketierung geprüft.

**Nicht vollständig ausführbar:** Flask-API-Integrationstests (`test_app.py`, `test_attachments_v6.py`) benötigen Flask, das in der Build-Umgebung nicht installiert ist. Ein realer iPhone-/Portainer-End-to-End-Test ist ebenfalls nicht möglich. Die neuen API-Endpunkte wurden daher nur durch Syntax- und Modultests geprüft.

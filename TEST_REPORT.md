# Test Report – v8.7.2

## Ergebnis

- **59 Kern-/DB-/Worker-/KI-/BGG-/Recherchetests bestanden.**
- Neue v8.7.2-Tests: mehrsprachiger Fallback für `Scythe`, Fallback auch bei schwachen deutschen Treffern, BGG-only-Weiterlauf bei SearXNG-Ausfall, detaillierte Engine-Diagnose und sichere HTTP→HTTPS-Normalisierung von Suchtreffern.
- Python-Compile, JavaScript-Syntax, DOM-ID-Prüfung, CSS/Manifest, Docker-/Pages-Parität und ZIP-Integrität werden zusätzlich geprüft.
- **8 Flask-basierte API-/Attachment-Integrationstests sind in dieser Build-Umgebung nicht ausführbar**, weil Flask hier nicht installiert ist. Das ist eine Umgebungsgrenze, kein bestandener Test.

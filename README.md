# Brettspielregal v10.0.0 — Docker Fullstack und iPhone-PWA

Vollständige selbstgehostete Brettspiel-Sammlung mit Flask/SQLite, Anhängen unter `/app/data`, Hintergrund-Import, BGG, Ollama, SearXNG und gemeinsamem Frontend für Docker und GitHub Pages. Dies ist eine **additive Aktualisierung von v9.1.6**.

## Neu in v10

### 1. Grundspiele und Erweiterungen verknüpfen

In **Spiel → Bearbeiten** gibt es **Spieltyp** (Grundspiel, Erweiterung, eigenständige Erweiterung, Promo, Zubehör) und **Gehört zu Grundspiel**. Nach dem Speichern einer BGG-ID kannst du mit **„BGG-Beziehungen vorschlagen“** die strukturierten Verknüpfungen der XML-API2 prüfen. Nur in deiner Sammlung vorhandene, eindeutig zugeordnete BGG-IDs werden als Kandidaten vorgeschlagen. **BGG verknüpft nichts automatisch**; du bestätigst den Vorschlag im Formular und klickst anschließend auf „Speichern“. Im Lesemodus werden zugehörige Erweiterungen mit Lagerort angezeigt. Beim Löschen des Grundspiels werden Verknüpfungen bei Erweiterungen aufgelöst, nicht die Erweiterungen gelöscht.

### 2. Duplikate und Ausgaben erkennen

Das Frontend prüft vor **Speichern**, beim einzelnen Quick-Add und beim Mehrfach-Quick-Import vorhandene Spiele über **EAN → BGG-ID → Titel**. Gleiche BGG-ID bei anderer Sprache/Ausgabe wird ausdrücklich als **mögliche andere Ausgabe** behandelt. Du entscheidest, ob du trotzdem speicherst. **Keine automatische Zusammenführung oder Löschung**. Die Prüfung berücksichtigt die gerade geladene Sammlung und ist keine globale Zwangssperre für direkte API-Nutzer.

### 3. „Was spielen wir heute?“

Auf der Sammlungsseite gibt es einen Button **🎲 Was spielen wir heute?**. Kriterien: Spielerzahl, maximale Spieldauer, Alter und Tag. Danach **Spiel auslosen** oder **passende Spiele anzeigen**. Erweiterungen, Promos und Zubehör werden nicht als eigenständige Spielvorschläge ausgewählt; eigenständige Erweiterungen bleiben enthalten. Kein KI-Aufruf, keine neue Cloud-Verbindung.

### 4. Anleitungssuche mit SearXNG statt OpenAI

Im mitgelieferten Portainer-Stack ist `RULE_SEARCH_PROVIDER: "searxng"` aktiviert. Der Bearbeitungsmodus → **„Offizielle Anleitung suchen“** zeigt eine **anklickbare Kandidatenliste** mit Quellen-Domains und Hinweisen auf mögliche PDF-Dateien. Du prüfst den Link und wählst ihn bewusst aus; anschließend erscheint eine Vorschau, erst danach wird die URL in das Formular eingetragen. **SearXNG-Suchergebnisse sind nicht verifiziert** und werden niemals ungefragt lokal archiviert. Für die Regel-Suche wird kein OpenAI-Key benötigt. Eine direkte Produkt-/Regelseite kann weiterhin manuell als Quelle angegeben werden.

### 5. Sprache und Edition

Neue Felder: **Sprache**, **Ausgabe/Edition**, **Ausgabejahr**, **Originaljahr**. Der bestehende Jahrgang bleibt unverändert; die neuen Felder überschreiben alte Metadaten nicht. Die Daten sind im Docker-/Pages-Modus, im JSON-Backup (Formatversion 5 bleibt kompatibel) und beim Transfer enthalten.

### 6. Browser-/iPhone-PWA-Regressionstests

Unter `tests/pwa_v10.spec.mjs` liegen ausführbare **Playwright-Mobile-Tests für Chromium und WebKit (Safari-Engine)** mit lokalem Server unter `playwright.config.mjs`. Sie prüfen Neuerfassung, Editionsfelder, Spielauswahl, Detail-/Bearbeitungsdialog und Scrollposition, vorhandene BGG-/Barcode-Steuerelemente sowie das Offline-Laden des PWA-App-Shells.

Ausführen (auf einem Entwickler-PC oder GitHub Actions):

```bash
npm install --no-save @playwright/test@^1.58.0
npx playwright install chromium webkit
npx playwright test -c playwright.config.mjs
```

Die GitHub-Actions-Definition liegt unter `.github/workflows/pwa-regression.yml` und führt die Tests bei Pushes/PRs aus. **Chromium-WebKit-Simulatoren ersetzen keinen echten iPhone-Safari-Kamera-Test.**

## Daten und Update

- Schema-Version: **13** (nicht-destruktive neue Spalten und Index)
- Bestehende v9.1.6-Datenbank, Fotos, PDFs, KI-Vorschläge und Importaufträge bleiben erhalten
- Vollständiges ZIP-Backup/Restore aus v9.1 bleibt vorhanden
- JSON-Backup bleibt **Format 5** und enthält die zusätzlichen Felder; alte Backups werden weiterhin akzeptiert
- Keine neuen Pflicht-Secrets; der bestehende `BGG_API_TOKEN` bleibt serverseitig
- PWA-Cache: `brettspielregal-pwa-v10-0-0`
- iPhone-Pages-Lokalmodus nutzt weiterhin IndexedDB, ohne unechte Serversynchronisation

**Wichtig:** Der Portainer-Stack baut aus `https://github.com/Ashguard85/Regal-docker.git#main`. Zuerst den vollständigen Docker-ZIP-Inhalt in dieses Repo committen/pushen und **dann** den Stack mit frischem Image-Build deployen. Nur eine aktualisierte YAML startet sonst wieder den alten Code. Volumes keinesfalls löschen. Vor dem Update ein vollständiges ZIP-Backup erstellen und separat sichern.

## Einschränkungen

BGG-Beziehungen werden nur vorgeschlagen, wenn die relevanten Spiele samt BGG-ID in deiner Sammlung vorhanden sind. SearXNG kann bei bestimmten Verlagen PDF-Links nicht finden; die Treffer sind absichtlich nur Vorschläge. Keine Browser-/iPhone-Laufzeitgarantie ohne Test auf deinem echten Gerät.

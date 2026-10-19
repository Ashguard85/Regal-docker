# Brettspielregal v9.1.4 – Portainer

**Safari EAN-Scanner-Fix (ab v9.1.2):** Die iPhone-PWA liest EAN-13 und EAN-8 jetzt lokal per JavaScript aus Kameraframes; die experimentelle Safari-BarcodeDetector-API ist nicht mehr erforderlich. Für das Update beide Pakete (Docker und gegebenenfalls Pages) aktualisieren. **Keine neue Environment-Variable und keine Datenbankmigration.** Die persistenten `/app/data`-Volumes unverändert weiterverwenden. PWA einmal vollständig schließen und wieder öffnen, damit `brettspielregal-pwa-v9-1-3` aktiv ist.

---

# Brettspielregal v9.1.1 – Portainer

**Update von v9.1.0:** Nur die Benutzeroberfläche wurde neu strukturiert; dieselbe SQLite-Datenbank und dieselben `/app/data`-Volumes weiterverwenden. Keine neuen Environment-Variablen, keine Migration und kein weiterer Dienst nötig. Docker und Pages möglichst gemeinsam auf v9.1.1 aktualisieren; auf dem iPhone die PWA anschließend einmal neu öffnen, damit `brettspielregal-pwa-v9-1-1` geladen wird.

# Brettspielregal v9.1 – Portainer Deployment

## Update von v9.0

1. **Vor dem Update** den bestehenden JSON-Export erstellen und eine Kopie deines `/app/data`-Volumes sichern.
2. Docker-v9.1-Dateien ins vorhandene Git-Repository übertragen und den Stack über Portainer neu deployen. Die Volumes **nicht löschen**.
3. GitHub-Pages-v9.1-Dateien ins Pages-Repository übertragen, falls Pages verwendet wird.
4. Auf dem iPhone die PWA schließen und neu öffnen. Der Cache-Key wurde auf `brettspielregal-pwa-v9-1-1` geändert.

## Neue Einstellungen

Die fünf Funktionen erfordern für den normalen Betrieb **keine neuen Pflichtvariablen**. `FULL_BACKUP_KEEP` begrenzt vollständige manuelle ZIP-Backups standardmäßig auf die fünf neuesten Archive; spezielle `before-restore-*`-Sicherungen werden dadurch nicht gelöscht. Für einen **vollständigen ZIP-Restore** ist ein eigener Admin-Schlüssel erforderlich:

```env
BACKUP_RESTORE_TOKEN=<mindestens-20-zufaellige-Zeichen>
```

Diesen Wert unter **Portainer → Stack → Environment variables** setzen. Nicht als Schlüssel in Git committen und nicht im Frontend speichern. Die App fragt ihn vor dem Restore einmalig ab; HTTPS bzw. ein vertrauenswürdiges LAN verwenden.

Vorhandene Werte `SECRET_KEY`, `SEARXNG_SECRET`, `PWA_ALLOWED_ORIGINS`, `BGG_API_TOKEN` nicht versehentlich löschen oder ändern.

## Vollständiges ZIP-Backup

Unter **Setup → Vollständiges ZIP-Backup und Restore → ZIP erstellen** herunterladen. Das Archiv enthält `database.sqlite` (Spiele, Importwarteschlange, App-/Recherche-Einstellungen), `attachments/` (Original-Cover und PDFs) und `manifest.json` mit SHA-256-Prüfsummen. Generierte WebP-Thumbnails werden nach einem Restore bei Bedarf neu erstellt.

**ZIP-Restore:** ZIP auswählen, Admin-Schlüssel eingeben, `RESTORE` bestätigen. Der Upload wird geprüft und als `/app/data/restore-pending.zip` gespeichert. Die laufende Datenbank bleibt unverändert. **Danach den ganzen Stack (App UND Worker) anhalten und gemeinsam neu starten.** Beim Start verarbeitet genau ein Container die ZIP unter einer Dateisperre, erstellt zuerst `/app/data/backups/before-restore-*.zip`, stellt SQLite und Original-Anhänge wieder her und startet erst dann App bzw. Worker. Nicht nur einen einzelnen Container mit aktivem Worker neu starten.

Auch die bestehenden JSON-v5-Backups und Docker-/Pages-Übertragungen bleiben erhalten. Secrets/Portainer-Umgebungsvariablen sind nicht im ZIP.

## Offline-Regal

Im Server-Modus unter **Setup → Offline-Regal** bewusst eine Momentaufnahme anlegen. Eigene Cover werden lokal in IndexedDB gespeichert. Der lokale Pages-Datenmodus und dessen Datenbank bleiben davon getrennt. Ohne Netzwerk werden nur Lesefunktionen angeboten. Bei wiederhergestellter Verbindung unter Setup **Wieder verbinden** wählen.

## Kamera/EAN

Die automatische Barcode-Erkennung benötigt HTTPS oder localhost, eine Kameraerlaubnis und `BarcodeDetector` im Browser. Bei fehlender Browserunterstützung die EAN im Kameradialog eintippen. Die Kamera wird beim Schließen des Dialogs gestoppt.

## KI-Regeln und Diagnose

**Setup → KI-Feldfreigabe**: Standard aus; nach Aktivierung nur explizit gewählte, serverseitig direkt belegte Felder. Keine Beschreibung, Tags, Regeln oder Widersprüche automatisch.

**Setup → Verbindung / Server** zeigt zusätzlich BGG-Token-Status, SQLite-Schema und -Zustand, Anhänge, freien Speicher, letztes vollständiges ZIP-Backup und ggf. einen vorgemerkten Restore.

## v9.1.3 – Safari EAN-Scanner

Keine zusätzlichen Environment-Variablen. Aktualisiere auch die GitHub-Pages-Dateien und öffne die iPhone-PWA nach dem Deployment neu; der Service Worker lädt die lokale `ean-scanner.js` in den v9.1.3-Cache.


## v9.1.3 – Bearbeiten beginnt oben

Reines Frontend-Update: Bearbeitungsdialog startet stets am Anfang, auch nach vorherigem Scrollen oder bei offenen KI-Vorschlägen. Bestehende Volumes, Datenbank und Portainer-Variablen unverändert lassen.


## v9.1.4 – Scanner bei iPhone/Safari

Im Scanner wird die Anzahl tatsächlich geprüfter Kamerabilder angezeigt. Neu kann über **„Barcode fotografieren“** ein Einzelbild mit der iPhone-Kamera aufgenommen und lokal analysiert werden. Dies hilft besonders, wenn der Live-Stream unscharf ist oder Safaris experimenteller `BarcodeDetector` keine Treffer liefert. Der Kamera-/Foto-Code ist im Service-Worker-Cache v9.1.4 enthalten.

Keine neuen Portainer-Umgebungsvariablen oder SQLite-Migrationen. Nach dem Deployment die PWA vollständig schließen und den neuen Cache laden lassen. Wenn noch kein Code erkannt wird, den **Scannerstatus einschließlich Kamerauflösung** sowie nach Möglichkeit ein Foto des Barcodes teilen.

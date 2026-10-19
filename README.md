# Brettspielregal – Docker Fullstack v9.1.3

## Neu in v9.1.3 – Bearbeiten immer oben öffnen

- Beim Öffnen eines bestehenden Spiels im **Bearbeitungsmodus** startet der Dialog jetzt immer am Anfang. Die zuvor benutzte Scrollposition wird nicht übernommen.
- Auf dem iPhone wird beim Bearbeiten nicht mehr automatisch das Titelfeld fokussiert; dadurch springt Safari bei langen oder geöffneten KI-Bereichen nicht mehr nach unten.
- Die Scrollposition wird am eigentlichen Formular-Scrollcontainer unmittelbar beim Öffnen und erneut im nächsten Animationsframe zurückgesetzt.
- Die Position der dahinterliegenden Sammlung bleibt unverändert. **Keine Datenbankmigration und keine neuen Umgebungsvariablen.**

## Neu in v9.1.2 – Safari EAN-Scanner repariert

- Die Kamera und die Erkennung sind jetzt unabhängig von der experimentellen Safari-`BarcodeDetector`-API.
- **EAN-13 und EAN-8** (UPC-A als EAN-13 mit führender Null) werden aus Kameraframes **direkt auf dem Gerät** gelesen. Es werden keine Bilder hochgeladen und kein externer Scan-Dienst benutzt.
- Der kleine Decoder liegt als eigenständige lokale Datei `ean-scanner.js` bei und wird zusammen mit der PWA offline gecacht. Es werden keine Drittanbieter-CDN-Skripte benötigt.
- Native `BarcodeDetector`-Erkennung bleibt bei anderen Browsern als zusätzliche Möglichkeit. Auf iPhone/iPad wird die unzuverlässige experimentelle Safari-Implementierung bewusst nicht aufgerufen.
- Der Scanner prüft Prüfziffern und verlangt zwei aufeinanderfolgende gleiche Erkennungen, um Fehlablesungen zu minimieren. Zusätzlich werden das vollständige Strichmuster und die Ruhezonen geprüft.
- Die Kamera stoppt beim Schließen, beim Verlassen der App und nach einem Treffer. Falls die Erkennung nicht gelingt, kann die EAN weiterhin manuell eingegeben werden.
- **Keine Datenbankmigration, keine neue Portainer-Variable.** Der PWA-Cache wurde in v9.1.2 erneuert.

**Aufnahme-Tipp:** Den gedruckten Strichcode möglichst waagrecht und groß ins Bild halten, etwas Abstand zur Schachtel lassen und für gleichmäßiges Licht sorgen.

## Neu in v9.1.1 – Spielansicht bewusst schreibgeschützt

- **Spiele ansehen:** Nur Cover, Infos, Tags, Lagerort, Links und vorhandene Bilder/PDFs öffnen. Keine verändernden Aktionen im Anzeigedialog.
- **Bearbeiten:** Alle Aktionen für ein Spiel liegen jetzt hinter **„Bearbeiten“**: Datei hochladen/löschen, anderes Anhangsbild als Cover setzen, externes Cover/PDF lokal archivieren, Neu recherchieren und KI-Vorschläge prüfen/übernehmen/verwerfen.
- Der Bearbeitungsdialog hat oben den ausklappbaren Bereich **„Recherche, Cover & KI verwalten“**. Bei offenen KI-Vorschlägen öffnet sich der Bereich automatisch. Die Queue-Aktion „Vorschläge prüfen“ führt direkt dorthin.
- Einzelne KI-Freigaben ändern die gespeicherten Felder; alle anderen noch nicht gespeicherten Eingaben im Formular bleiben erhalten. Ein Forschungs-Neustart warnt, dass ungespeicherte Änderungen verloren gehen.
- **Kein Datenbank-Update:** SQLite-Schema 11 und Backup-Format 5 bleiben gleich. Keine neuen Portainer-Variablen. PWA-Cache wurde auf `brettspielregal-pwa-v9-1-1` angehoben.

## Neu in v9.1.0

1. **Offline-Regal:** Bewusst erstellte IndexedDB-Momentaufnahme der Server-Sammlung und eigener Cover; beim Verbindungsverlust automatisch schreibgeschützt ansehen. Kein Offline-Schreiben, keine automatische Synchronisation, keine Zugangsdaten im Snapshot.
2. **EAN-Kamerascanner:** BarcodeDetector mit Rückkamera unter HTTPS/localhost und manueller EAN-Eingabe, wenn der Browser die Erkennung nicht unterstützt.
3. **KI-Autofreigabe:** Standard aus, pro sicherem Feld konfigurierbar; nur serverseitig geprüfte `primary`-/`strong`-Belege. Texte/Tags/Widersprüche bleiben zur manuellen Freigabe.
4. **Vollständiges ZIP-Backup + sicher vorgemerkter Restore:** SQLite, Originalbilder/PDFs, Einstellungen und Import-Historie inklusive SHA-256-Manifest; für die Restore-Aktivierung müssen App und Worker gemeinsam neu gestartet werden. `BACKUP_RESTORE_TOKEN` (min. 20 Zeichen) erforderlich; Snapshots werden zuerst vollständig geprüft, dann Sicherheitsbackup vor Aktivierung.
5. **Systemdiagnose:** BGG-Token, Datenbank/Schema, Anhänge, freier Speicher, letzter ZIP-Backup-Zeitpunkt und Restore-Vormerkung zusätzlich zu Ollama, SearXNG, Worker und CORS.

**Migration:** Die SQLite-Schema-Version bleibt 11, das JSON-Backup-Format bleibt v5, der Pages/IndexedDB-Speicher migriert nicht-destruktiv auf Version 4. Service-Worker-Cache: `brettspielregal-pwa-v9-1-0`.

**Einschränkungen:** BarcodeDetector wird nicht von allen iPhone-/Safari-Versionen angeboten (manuelle Eingabe bleibt möglich). Offline-Cover sind nur im Snapshot gespeicherte **eigene** Cover. Externe Cover-URLs werden nicht heimlich geladen oder offline kopiert. Ein Restore überschreibt den Serverbestand erst nach dem gemeinsamen Stack-Neustart; davor ein externes Backup behalten.

Siehe `PORTAINER_SETUP.md` für Deployment und Restore-Schritte.

---

# Brettspielregal – Docker Fullstack v9.0.0

## Neu in v9.0.0 – Alltagstaugliches Brettspielregal

**Gemeinsame Frontend-Codebasis, Docker Fullstack weiterhin eigenständig.** Docker und GitHub Pages haben dieselbe v9.0.0-Version. Das lokale Pages-Frontend verwendet IndexedDB; der Pages-Servermodus und die Docker-Oberfläche teilen sich die API.

### 1. Mobile Schnellerfassung

Der schwebende `+`-Button öffnet eine kompakte Schnellerfassung für **Titel oder EAN** und Lagerort. Im Serverbetrieb kann die KI optional im Hintergrund recherchieren; lokal wird direkt ohne Backend gespeichert. Zwei weitere Aktionen führen zur bestehenden Link- bzw. Fotoerfassung. Der zuletzt verwendete Tab und Lagerort werden als kleine UI-Einstellungen auf dem Gerät gemerkt.

### 2. BoardGameGeek-ID dauerhaft

`bgg_id` ist ein reguläres Spielefeld, sichtbar in Bearbeitung und Detailansicht. Der Worker übernimmt IDs aus sehr sicheren BGG-Identifikationen (Matchscore mindestens 90); ohne API-Token nur bei exakt passender, abgerufener öffentlichen BGG-Spiel-URL. Die ID bleibt bei Updates, Export und Restore erhalten. Der API-Token ist weiterhin optional.

### 3. Externe Cover & PDF-Anleitungen bewusst lokal archivieren

In der Detailansicht stehen bei vorhandenen HTTPS-Links **„Cover lokal archivieren“** und **„PDF lokal archivieren“** bereit. Der Server prüft HTTPS, öffentliche Ziel-IP, Weiterleitungen, Format und 10-MB-Grenze, speichert das Original unter `/app/data/attachments` und erstellt für darstellbare Bilder ein abgeleitetes WebP-Thumbnail unter `/app/data/thumbnails`. Das Original wird mit dem JSON-Backup exportiert; Thumbnails können regeneriert werden und müssen nicht ins Backup. Ein Serverdownload kann durch 403/Anti-Bot verhindert werden; es erfolgt kein Umgehen von Seitensperren. Manuelles Hochladen bleibt dann möglich.

Im **Pages-Lokalmodus** läuft der Download im Browser. Das funktioniert nur, wenn die externe Website CORS erlaubt; andernfalls die Datei zuerst auf dem iPhone speichern und anschließend als Anhang hinzufügen. Dabei wird kein Docker-Backend kontaktiert.

### 4. Stärkere Sammlungssuche

Die bestehenden Such- und Tagfilter bleiben, ergänzt durch: Spielerzahl, Spieldauer-Obergrenze, Mindestalter, Lagerort und Filter für fehlende lokal gespeicherte Cover/PDFs beziehungsweise BGG-ID. Die Filter werden lokal als kleine Einstellungen gemerkt. Die Player-Filter berücksichtigen min/max statt exakte Werte zu vergleichen.

### 5. Lagerorte praktisch verwalten

Bereits benutzte Lagerorte werden automatisch in der Filterauswahl und per Eingabevorschlägen angezeigt. Freitext bleibt möglich, z. B. `Wohnzimmer / 1. Tablar`. Unter Setup → **Lagerorte verwalten** lässt sich ein Lagerort nach Bestätigung für alle betroffenen Spiele umbenennen. Im Servermodus wird davor ein SQLite-Backup angelegt.

### Technische Kompatibilität

- **SQLite Schema 11** ergänzt `games.bgg_id`, ohne alte Datensätze zu löschen.
- **JSON-Backup-Format Version 5** enthält BGG-ID und alle archivierten Originaldateien. Import von Backup-Versionen 1 bis 5 bleibt möglich. v8.x kann v9-Backups möglicherweise nicht verstehen; vor dem Update eine externe Kopie behalten.
- **Pillow** wird für WebP-Thumbnails benötigt, keine weitere Datenbank und kein zusätzlicher Dienst.
- **Keine neuen Pflicht-Environment-Variablen.** Vorhandene Container-/Portainer-Volumes müssen unverändert weiterverwendet werden.
- **Keine automatische Synchronisation** zwischen Pages-Lokalmodus und Server; weiterhin bewusster Backup-Transfer.
- **Bekannte Einschränkung:** Kein vollständiger Browser-/iOS-Laufzeittest im Build-Container und keine echten externen Downloadtests. Seiten können ihre Downloads verhindern.

---

Selbstgehostete Brettspiel-Sammlung als responsive PWA mit Flask/SQLite, Dateianhängen, lokalem Ollama, SearXNG und persistentem Hintergrund-Worker.

## Neu in v8.8.3 – Cover im Regal ohne Blob-Hydrierung

- Im Docker-/Same-Origin-Betrieb werden eigene Cover jetzt direkt über den bestehenden Attachment-Endpunkt als normales `<img>` geladen.
- Das Regal ist damit nicht mehr vom `IntersectionObserver` oder einem nachträglichen Blob-Austausch abhängig.
- Für GitHub Pages bzw. Verbindungen mit Cloudflare-Service-Token bleibt der Blob-Fallback erhalten, weil dort zusätzliche Request-Header nötig sein können.
- Eigene Cover verwenden weiterhin exakt den ausgewählten `cover_attachment_id`; das erste Bild wird seit v8.8.1 automatisch explizit als Cover gespeichert.
- Fehlerhafte direkte Bildaufrufe fallen sichtbar auf einen Cover-Platzhalter zurück.
- Es sind keine neuen Environment-Variablen nötig.

## Neu in v8.8.0

### Feldweise Herkunft statt künstlicher KI-Prozentwerte

Jeder temporäre KI-Vorschlag bekommt jetzt eine nachvollziehbare Belegstufe, die **ohne zusätzlichen Ollama-Durchlauf** aus den bereits geladenen Quellen berechnet wird:

- **🔵 Primärquelle** – eine erkannte offizielle Verlags-/Herstellerseite bestätigt den Wert direkt.
- **🟢 Gut belegt** – mindestens zwei unabhängige Quellen bestätigen denselben Wert.
- **⚪ Eine Quelle** – der Wert ist direkt belegt, aber nur von einer nicht-offiziellen Quelle.
- **🟡 KI-abgeleitet** – z. B. Beschreibung, Kurzregeln und Tags oder ein Wert, der nicht 1:1 strukturiert extrahiert wurde.
- **🟠 Widerspruch** – ausgewählte Quellen nennen für ein eindeutiges Feld unterschiedliche Werte.

Unter **Vorschläge prüfen** zeigt **Belege ansehen** pro Feld Quelle, Quellenklasse und den dort gefundenen Wert. Die Bewertung passiert deterministisch im Backend; der Browser kann die Belegstufe nicht selbst hochstufen.

### Alle gut belegten übernehmen

Der neue Button **„✓ Alle gut belegten übernehmen“** übernimmt ausschließlich Vorschläge, die das Backend als `Primärquelle` oder `Gut belegt` markiert hat. Widersprüche, KI-abgeleitete Texte/Tags und nur schwach belegte Werte bleiben offen und können weiterhin einzeln geprüft werden. Titel, Beschreibungen, Kurzregeln, Tags und Auszeichnungen werden auch bei guter Quellenlage nicht blind per Sammelfreigabe übernommen.

### Performance

Für die Belegstufen gibt es **keinen zweiten KI-Aufruf und keine zusätzlichen Webseitenabrufe**. Die Funktion verwendet nur die ohnehin bereits von v8.7.3 geladenen Quellenwerte. RAM-Bedarf und Modell-Ladezeit ändern sich dadurch praktisch nicht.

## Neu in v8.7.2

- **Robustere SearXNG-Fallbacks:** zuerst deutsch, bei zu wenigen verlässlichen Treffern automatisch mehrsprachig (`language=all`).
- **Einfache Suchanfragen statt überstrenger Operatoren:** kurze Titel wie `Scythe` funktionieren auch mit Engines, die Quotes/Site-Filter schlecht unterstützen.
- **HTTP-Suchergebnisse werden nie unsicher geladen:** Standard-HTTP-Treffer werden nur als HTTPS-Variante geprüft; private/unsichere Ziele bleiben blockiert.
- **BGG kann SearXNG überbrücken:** mit gültigem BGG-Token reicht eine strukturierte BGG-Identifikation als belastbare Quelle, damit Ollama weiterarbeiten kann.
- **Bessere Fehlerdiagnose:** 0 Roh-Treffer, verworfene URLs, nicht antwortende Engines und Abruffehler werden getrennt ausgewiesen.

## Neu in v8.5.3

### Laufende und hängende Hintergrundjobs abbrechen

Laufende Importjobs besitzen direkt in **Import → Warteschlange & Prüfung** einen **Abbrechen**-Button. Jeder Auftrag läuft in einem eigenen Worker-Unterprozess, damit auch ein festhängender SearXNG-/Ollama-Aufruf tatsächlich beendet werden kann.

- `Abbrechen` setzt eine Abbruchanforderung; der Worker-Supervisor beendet den Job-Unterprozess und markiert den Auftrag als `cancelled`.
- Wenn ein Auftrag länger keinen Fortschritt macht oder der Abbruch nicht bestätigt wird, erscheint **Hängenden Auftrag freigeben**.
- Temporäre KI-Vorschläge des abgebrochenen Jobs werden verworfen; das Spiel selbst bleibt erhalten.

## Neu in v8.5.2

Die Hintergrund-Warteschlange kann jetzt direkt im Import-Tab aufgeräumt werden. Fehler/Verlauf lassen sich entfernen; optional können auch offene KI-Prüfungen samt temporären Vorschlägen oder alle nicht laufenden Aufträge gelöscht werden. Spiele selbst werden dabei niemals gelöscht und laufende Worker-Aufträge bleiben geschützt.

## Neu in v8.5.1

### Hotfix: Frontend startet wieder zuverlässig

Ein Syntaxfehler in der neuen KI-Opt-out-Meldung aus v8.5.0 wurde behoben. Zusätzlich lädt der Service Worker die App-Kerndateien jetzt network-first und fällt nur offline auf den Cache zurück. Das verhindert Versionsmischungen nach Updates auf iPhone/PWA.


### KI pro Erfassung abschaltbar

Bei der Schnellerfassung gibt es jetzt **„Mit KI recherchieren“**. Ist der Schalter aus, werden die Spiele sofort gespeichert, aber **kein Queue-/Ollama-Auftrag** erzeugt. Dasselbe gilt beim manuellen Anlegen eines neuen Spiels über **„Nach dem Speichern mit KI recherchieren“**. Bestehende Spiele werden beim normalen Bearbeiten weiterhin nie automatisch neu recherchiert.

### iPhone: keine automatische Textvergrößerung

Safari/iOS bekommt jetzt `-webkit-text-size-adjust: 100%`; Eingabefelder bleiben auf kleinen Displays bei mindestens 16 px. Dadurch wird die Oberfläche beim Fokussieren oder nach Layoutänderungen nicht ungefragt hochskaliert. Pinch-Zoom bleibt aus Gründen der Bedienbarkeit und Barrierefreiheit weiterhin möglich.

### Weiterhin enthalten aus v8.4

### KI recherchiert – du gibst frei

Der Hintergrund-Worker schreibt Rechercheergebnisse **nicht mehr direkt in die freigegebenen Spieldaten**.

1. Titel oder EAN erfassen.
2. Spiel erscheint sofort in der Sammlung.
3. Worker recherchiert im Hintergrund.
4. Qwen erzeugt temporäre Vorschläge.
5. Im Import-Tab auf **Vorschläge prüfen** tippen.
6. Aktuellen Wert und KI-Vorschlag nebeneinander vergleichen.
7. Felder einzeln **Übernehmen** / **Verwerfen** oder **Alle Vorschläge übernehmen**.

Manuelle Werte bleiben unangetastet, bis der Benutzer ausdrücklich einen Vorschlag übernimmt.

### Lagerort

Neues Feld `storage_location`, z. B. `1. Tablar`, `Wohnzimmer links` oder `Keller Regal 2`.

- beim normalen Bearbeiten
- optional für eine komplette Schnellerfassungs-Charge
- sichtbar in Sammlung und Detailansicht
- durchsuchbar
- Bestandteil des JSON-Backups

### Nur deutsche Nutzdaten

Freie KI-Texte werden auf Deutsch verlangt. Die kontrollierten Tags wurden auf deutsche Werte umgestellt, z. B.:

- `Worker Placement` → `Arbeitereinsatz`
- `Tile Placement` → `Plättchenlegen`
- `Set Collection` → `Sets sammeln`
- `Push Your Luck` → `Risikoabwägung`
- `Deck Building` → `Deckbau`

Eigennamen wie Autoren, Verlage und offizielle Titel bleiben natürlich unverändert.

### BoardGameGeek als Referenzquelle

`boardgamegeek.com` ist standardmäßig als **strukturierte Referenzquelle** eingetragen. Hersteller-/Verlagsseiten bleiben für edition-spezifische Angaben wie deutsche EAN, Cover und offizielle Anleitung höher priorisiert. Englische BGG-Texte oder Kategorien werden nicht ungefiltert gespeichert; Qwen muss sie ins Deutsche normalisieren.

Unter **Setup → Automatische Recherche – Quellen & Prompt** gibt es jetzt drei Quellgruppen:

- Primärquellen – Hersteller/Verlage
- Strukturierte Referenzquellen – standardmäßig BoardGameGeek
- Niedrig priorisierte Quellen – Reviews/Händler als Ergänzung

### Backup / Migration

- Datenbankschema: **8**
- Backupformat: **4**
- Backup v1–v4 bleibt importierbar.
- Anhänge sind weiterhin im JSON-Backup enthalten.
- Temporäre KI-Vorschläge/Queue-Zustände werden bewusst nicht als Sammlungsdaten exportiert.

## Dienste

- `app` – Web/API
- `worker` – serieller Hintergrund-Worker
- `searxng` – interne Websuche
- Ollama läuft auf dem Docker-Host

## Ollama

```bash
ollama pull qwen3:14b
ollama pull gemma3:12b
```

- Text/Webrecherche: `qwen3:14b`
- Screenshots: `gemma3:12b`

## Portainer

Siehe `PORTAINER_SETUP.md` und `portainer-stack-v8.8.3.yml`.

Wichtige technische Variablen bleiben in Portainer:

```yaml
AI_PROVIDER: "ollama"
OLLAMA_BASE_URL: "http://host.docker.internal:11434"
OLLAMA_TEXT_MODEL: "qwen3:14b"
OLLAMA_VISION_MODEL: "gemma3:12b"
AUTO_SEARCH_PROVIDER: "searxng"
SEARXNG_BASE_URL: "http://searxng:8080"
BGG_ENABLED: "true"
BGG_API_TOKEN: "${BGG_API_TOKEN:-}"
BGG_TIMEOUT_SECONDS: "15"
BGG_MIN_INTERVAL_SECONDS: "5"
AUTO_FETCH_PAGES: "3"
AUTO_RESEARCH_MAX_CHARS: "24000"
```

Die fachlichen Quellen und Prompts werden dagegen im App-Setup gepflegt und persistent in SQLite gespeichert.

## Neue/erweiterte API-Routen

- `GET /api/system/status`
- `GET /api/import-queue`
- `POST /api/import-queue/cleanup`
- `POST /api/import-queue/quick`
- `POST /api/import-queue/games/<game_id>`
- `POST /api/import-queue/<job_id>/retry`
- `POST /api/import-queue/<job_id>/cancel`
- `POST /api/import-queue/<job_id>/force-release`
- `POST /api/import-queue/<job_id>/suggestions/apply`
- `POST /api/import-queue/<job_id>/suggestions/reject`
- `GET/PUT/POST /api/research-settings`

## Tests

```bash
pip install -r requirements-dev.txt
PYTHONPATH=. pytest -q
```

Frontend zusätzlich mit `node --check` prüfen.


## v8.7 – GitHub Pages + Docker

Mehrere externe Frontend-Origins können mit `PWA_ALLOWED_ORIGINS` (Komma, Semikolon oder neue Zeile) freigegeben werden. Die alte Variable `PWA_ALLOWED_ORIGIN` wird als Fallback weiter unterstützt. Die lokale Docker-Oberfläche ist same-origin und benötigt technisch keinen CORS-Eintrag.

Unter **Setup → Verbindung / Server** zeigt die App einen Systemstatus für Backend, API, Worker, Ollama/KI, SearXNG und CORS.

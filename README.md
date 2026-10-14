# Brettspielregal – Docker Fullstack v8.7.1

Selbstgehostete Brettspiel-Sammlung als responsive PWA mit Flask/SQLite, Dateianhängen, lokalem Ollama, SearXNG und persistentem Hintergrund-Worker.


## Neu in v8.7.1

### Hotfix: robuste Quellen-Fallbacks bei kurzen/mehrdeutigen Titeln

Bei Titeln wie **Scythe** konnte v8.7 abbrechen, obwohl SearXNG brauchbare Treffer gefunden hatte: Die vorselektierten Seiten wurden nur einmal versucht und die öffentliche BoardGameGeek-Spielseite war pauschal ausgeschlossen.

- Wenn die strukturierte BGG-API nicht verfügbar ist (z. B. ohne `BGG_API_TOKEN`), darf die öffentliche BGG-Spielseite jetzt als normale Referenzquelle einspringen.
- Der Worker baut eine grössere Fetch-Warteschlange auf und probiert weitere hochwertige Treffer, bis `AUTO_FETCH_PAGES` Seiten **erfolgreich** abgerufen wurden. Ein HTTP-403 einer guten Quelle beendet die Recherche nicht mehr.
- Zusätzlich wird eine englische `"<Titel>" board game`-Discovery-Suche verwendet; das verbessert kurze internationale Titel.
- Fehlermeldungen unterscheiden nun zwischen **keinen Treffern**, **zu schwachen Treffern** und **gefundenen, aber nicht abrufbaren Seiten** und hängen den BGG-Hinweis an.
- Der Recherchebericht zeigt die tatsächlich erfolgreich verwendeten Quellen; fehlgeschlagene Abrufe erscheinen bei den verworfenen Treffern.

### Webrecherche grundlegend neu aufgebaut

Die allgemeine Websuche ist nicht mehr die Faktengrundlage für Ollama. Der Hintergrundimport arbeitet jetzt in klar getrennten Schritten:

1. Titel/EAN erfassen – das Spiel steht sofort in der Sammlung.
2. BoardGameGeek wird als **strukturierte Identitätsquelle** abgefragt, wenn ein Titel vorhanden ist.
3. SearXNG sucht mit mehreren gezielten Queries nur nach möglichen URLs.
4. Treffer werden **vor dem Abruf** bewertet: Titelähnlichkeit, exakte EAN, Primärquelle, Verlag/Jahr sowie Abzüge für Review/Test oder mögliche Erweiterungen.
5. Nur die besten **2–4 Quellen** werden direkt geladen. Such-Snippets werden nicht an Ollama als Fakten weitergegeben.
6. Jede ausgewählte Quelle wird getrennt deterministisch extrahiert (JSON-LD/Metadaten/Seitentext).
7. Erst das kleine, vorselektierte Recherchebundle geht an Qwen3 14B zur Zusammenführung und deutschen Normalisierung.
8. Die Ergebnisse bleiben weiterhin temporäre Vorschläge und überschreiben deine Sammlung erst nach Freigabe.

Bei einer EAN-Erfassung versucht v8.7 zuerst eine passende Produktseite zu finden. Sobald daraus ein plausibler Titel extrahiert wurde, wird BGG zusätzlich mit diesem Titel als strukturierte Referenz abgefragt. Für die aktuelle BGG-XML-API muss `BGG_API_TOKEN` gesetzt sein; ohne Token läuft die Recherche weiter, nur der strukturierte BGG-Schritt wird übersprungen.

### Transparente Quellenauswahl

In **Vorschläge prüfen** wird jetzt sichtbar:

- welche BGG-Identität erkannt wurde und mit welchem Match-Score,
- welche Quellen tatsächlich an Ollama weitergegeben wurden,
- welche Suchtreffer vorher verworfen wurden und warum.

Der Direktlink-Import bleibt unverändert der präziseste Weg: dort entfällt die allgemeine Suchphase vollständig.

### GitHub Pages + Docker aus v8.6 bleibt enthalten

Mehrere externe Frontend-Origins über `PWA_ALLOWED_ORIGINS`, Systemdiagnose für API/Worker/Ollama/SearXNG/CORS und same-origin Betrieb der lokalen Docker-Seite bleiben unverändert verfügbar.

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

Siehe `PORTAINER_SETUP.md` und `portainer-stack-v8.7.1.yml`.

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

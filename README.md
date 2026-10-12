# Brettspielregal – Docker Fullstack v8.5.0

Selbstgehostete Brettspiel-Sammlung als responsive PWA mit Flask/SQLite, Dateianhängen, lokalem Ollama, SearXNG und persistentem Hintergrund-Worker.

## Neu in v8.5

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

- Datenbankschema: **6**
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

Siehe `PORTAINER_SETUP.md` und `portainer-stack-v8.5.yml`.

Wichtige technische Variablen bleiben in Portainer:

```yaml
AI_PROVIDER: "ollama"
OLLAMA_BASE_URL: "http://host.docker.internal:11434"
OLLAMA_TEXT_MODEL: "qwen3:14b"
OLLAMA_VISION_MODEL: "gemma3:12b"
AUTO_SEARCH_PROVIDER: "searxng"
SEARXNG_BASE_URL: "http://searxng:8080"
```

Die fachlichen Quellen und Prompts werden dagegen im App-Setup gepflegt und persistent in SQLite gespeichert.

## Neue/erweiterte API-Routen

- `GET /api/import-queue`
- `POST /api/import-queue/quick`
- `POST /api/import-queue/games/<game_id>`
- `POST /api/import-queue/<job_id>/retry`
- `POST /api/import-queue/<job_id>/suggestions/apply`
- `POST /api/import-queue/<job_id>/suggestions/reject`
- `GET/PUT/POST /api/research-settings`

## Tests

```bash
pip install -r requirements-dev.txt
PYTHONPATH=. pytest -q
```

Frontend zusätzlich mit `node --check` prüfen.

# Brettspielregal – Docker Fullstack v8.0.0

Brettspiel-Sammlung als responsive PWA mit Flask/SQLite, Dateianhängen, lokalem Ollama und **persistenter Hintergrund-Recherche**. Docker v8 und GitHub Pages v8 gehören zusammen.

## Neu in v8

### Schnellerfassung + Hintergrund-Worker

Im Server-Modus können viele Spiele extrem schnell erfasst werden: **ein Titel oder eine EAN pro Zeile**. Die App legt die Einträge sofort an und stellt sie in eine persistente SQLite-Warteschlange.

Ein separater Docker-Worker verarbeitet die Queue nacheinander:

1. Suche über SearXNG anhand Titel/EAN.
2. Sichere HTTPS-Abrufe geeigneter Treffer; SSRF-Schutz bleibt aktiv.
3. Suchsnippets und erreichbare Seitendaten werden als unvertrauenswürdiges Recherchematerial gesammelt.
4. `qwen3:14b` strukturiert ausschließlich belegte Daten in das Brettspielregal-Schema.
5. Ergebnis wird automatisch am bestehenden Spiel gespeichert.
6. Status wird `done`, `review` oder `failed`.

Die PWA muss dafür nicht geöffnet bleiben.

### Queue-Status in der App

- Wartet
- Wird ergänzt
- Automatisch ergänzt
- Bitte prüfen
- Importfehler + Retry
- Worker online/offline

### Galaxus und andere 403-Seiten

v8 versucht keinen Bot-Schutz zu umgehen. Wenn eine konkrete Händlerseite HTTP 403 liefert, bleiben Suchsnippet und alternative Quellen nutzbar. Der Worker recherchiert weiter über andere Treffer.

## Dienste

- `app` – Web/API
- `worker` – serieller Import-Worker
- `searxng` – interne Websuche ohne veröffentlichten Host-Port

`app` und `worker` müssen dasselbe `/app/data` verwenden.

## Ollama

```bash
ollama pull qwen3:14b
ollama pull gemma3:12b
```

- Text-/Hintergrund-Import: `qwen3:14b`
- Screenshots: `gemma3:12b`

## Neue Umgebungsvariablen

```yaml
AUTO_ENRICH_ENABLED: "true"
AUTO_ENRICH_NEW_GAMES: "true"
AUTO_ENRICH_POLL_SECONDS: "5"
AUTO_SEARCH_PROVIDER: "searxng"
SEARXNG_BASE_URL: "http://searxng:8080"
AUTO_SEARCH_RESULTS: "8"
AUTO_FETCH_PAGES: "4"
AUTO_RESEARCH_MAX_CHARS: "30000"
```

Siehe `PORTAINER_SETUP.md` für den vollständigen Stack.

## Neue API-Routen

- `GET /api/import-queue`
- `POST /api/import-queue/quick`
- `POST /api/import-queue/games/<game_id>`
- `POST /api/import-queue/<job_id>/retry`
- `DELETE /api/import-queue/<job_id>`

## Datenbankmigration

v8 aktualisiert das Schema von Version 3 auf **4** und ergänzt:

- `import_jobs`
- `runtime_state`

Spiele, Anhänge und Backups bleiben kompatibel. Queue-Zustände werden bewusst **nicht** in JSON-Backups exportiert.

## Bestehende v7-Funktionen bleiben erhalten

- Magic Import Link
- Linkimport mit Qwen
- Screenshotimport mit Gemma 3 Vision
- Bilder/PDFs als Anhänge
- eigenes Bild als Cover
- JSON-Backup inklusive Anhänge
- Docker- und GitHub-Pages-Server-Modus

## Tests

```bash
pip install -r requirements-dev.txt
PYTHONPATH=. pytest -q
```

Zusätzlich können Frontend-Dateien mit `node --check` geprüft werden.

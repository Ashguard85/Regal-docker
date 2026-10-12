# Brettspielregal – Docker Fullstack v8.2.0

Brettspiel-Sammlung als responsive PWA mit Flask/SQLite, Dateianhängen, lokalem Ollama und **persistenter Hintergrund-Recherche**. Docker v8.2 und GitHub Pages v8.2 gehören zusammen.


## Neu in v8.2

- Primärquellen und niedrig priorisierte Domains direkt unter **Setup → Automatische Recherche – Quellen & Prompt** pflegen.
- Recherche-Systemprompt und Prompt-Vorlage im Backend editierbar, persistent in SQLite und auf Standard rücksetzbar.
- Primärquellen werden bei SearXNG bevorzugt gesucht und gewichtet.
- Schutz gegen Review-/Seitentitel als Spieltitel, ungültige GTIN/EAN, HTML-Seiten als Cover und nicht-offizielle Regelseiten.
- In der Prüfansicht werden die verwendeten Recherchequellen angezeigt.


### Eigener Import-Tab

Die Sammlung ist wieder vollständig auf Spiele fokussiert. Schnellerfassung, Worker-Status, Warteschlange und Prüfaufträge liegen jetzt im eigenen Tab **Import**. Queue-Badges werden nicht mehr auf den Spielkarten eingeblendet.

### „Bitte prüfen“ wirklich abschließen

Ein Prüfauftrag hat jetzt einen echten Workflow:

1. Im Tab **Import** auf **Prüfen** tippen.
2. Das Spiel öffnet sich inklusive Worker-Hinweisen.
3. Daten kontrollieren oder **Bearbeiten**.
4. Mit **✓ Passt – geprüft** bestätigen.
5. Der Auftrag erhält den Status `verified` und verschwindet aus der offenen Prüfliste.

Zusätzlich kann ein Spiel über **Neu recherchieren** wieder in die Queue gestellt werden.

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

Siehe `PORTAINER_SETUP.md` sowie `portainer-stack-v8.2.yml` für den vollständigen Stack.

## Neue API-Routen

- `GET /api/import-queue`
- `POST /api/import-queue/quick`
- `POST /api/import-queue/games/<game_id>`
- `POST /api/import-queue/<job_id>/retry`
- `POST /api/import-queue/<job_id>/approve`
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

# Portainer Stack – Brettspielregal v8.5.2

Diese Anleitung ist für die bestehende Installation auf `192.168.1.127:8190` vorbereitet.

## Vorher

Auf dem Ollama-Host müssen die Modelle vorhanden sein:

```bash
ollama pull qwen3:14b
ollama pull gemma3:12b
ollama list
```

In Portainer unter **Stack → Environment variables** müssen gesetzt sein:

```text
SECRET_KEY      = dein bisheriger Brettspielregal-Schlüssel
SEARXNG_SECRET  = ein langer zufälliger Schlüssel
```

Den vorhandenen `SECRET_KEY` nicht ändern.

## Web Editor

In **Stacks → Brettspielregal → Web editor** den Stack durch `portainer-stack-v8.5.yml` ersetzen oder folgenden Inhalt einfügen:

```yaml
x-app-build: &app-build
  context: https://github.com/Ashguard85/Regal-docker.git#main

x-app-environment: &app-environment
  APP_TITLE: "Brettspielregal"
  APP_URL: "http://192.168.1.127:8190"
  SECRET_KEY: "${SECRET_KEY}"
  PWA_ALLOWED_ORIGIN: "http://192.168.1.127:8190"
  BACKUP_KEEP: "50"

  AI_IMPORT_ENABLED: "true"
  AI_PROVIDER: "ollama"
  OLLAMA_BASE_URL: "http://host.docker.internal:11434"
  OLLAMA_TEXT_MODEL: "qwen3:14b"
  OLLAMA_VISION_MODEL: "gemma3:12b"
  OLLAMA_TIMEOUT_SECONDS: "600"
  AI_MAX_PAGE_CHARS: "16000"

  RULE_SEARCH_PROVIDER: "none"
  WEB_FALLBACK_PROVIDER: "none"

  AUTO_ENRICH_ENABLED: "true"
  AUTO_ENRICH_NEW_GAMES: "true"
  AUTO_ENRICH_POLL_SECONDS: "5"
  AUTO_SEARCH_PROVIDER: "searxng"
  SEARXNG_BASE_URL: "http://searxng:8080"
  AUTO_SEARCH_RESULTS: "8"
  AUTO_FETCH_PAGES: "4"
  AUTO_RESEARCH_MAX_CHARS: "30000"

services:
  app:
    image: brettspielregal:local
    pull_policy: build
    build: *app-build
    ports:
      - "8190:8080"
    volumes:
      - /home/buebi/docker/brettspielregal/data:/app/data
      - /home/buebi/docker/brettspielregal/backups:/app/data/backups
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment: *app-environment
    labels:
      homepage.group: "Spiele"
      homepage.name: "Brettspielregal"
      homepage.href: "http://192.168.1.127:8190"
      homepage.description: "Meine Brettspielsammlung"
      homepage.showStats: "true"
    depends_on:
      - searxng
    restart: unless-stopped

  worker:
    image: brettspielregal:local
    pull_policy: build
    build: *app-build
    command:
      - /bin/sh
      - -c
      - |
        echo "[worker] Brettspielregal Hintergrund-Worker gestartet"
        exec python -m app.import_worker
    healthcheck:
      disable: true
    volumes:
      - /home/buebi/docker/brettspielregal/data:/app/data
      - /home/buebi/docker/brettspielregal/backups:/app/data/backups
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      <<: *app-environment
      PYTHONUNBUFFERED: "1"
    depends_on:
      - searxng
    restart: unless-stopped

  searxng:
    image: docker.io/searxng/searxng:latest
    environment:
      SEARXNG_SECRET: "${SEARXNG_SECRET}"
    configs:
      - source: searxng_settings
        target: /etc/searxng/settings.yml
    volumes:
      - searxng_cache:/var/cache/searxng
    restart: unless-stopped

configs:
  searxng_settings:
    content: |
      use_default_settings: true

      general:
        debug: false
        instance_name: "Brettspielregal Search"

      search:
        safe_search: 0
        default_lang: "de"
        formats:
          - html
          - json

      server:
        secret_key: "${SEARXNG_SECRET}"
        limiter: false
        image_proxy: true

volumes:
  searxng_cache:
```

Danach **Update the stack**.

## Erwartete Container

- `app` – Web-App/API
- `worker` – Hintergrund-Import
- `searxng` – interne Websuche ohne veröffentlichten Port

Der Worker besitzt bewusst `healthcheck: disable: true`, weil er keinen HTTP-Server auf Port 8080 betreibt. `PYTHONUNBUFFERED=1` und die Startmeldung sorgen für sichtbare Logs in Portainer.

## v8.5 Bedienung

- **Sammlung**: nur Spiele, Suche und Listen-/Regalansicht. Der **Lagerort** ist sichtbar und durchsuchbar.
- **Import**: Schnellerfassung, optional ein Lagerort für die ganze Charge, Workerstatus und KI-Vorschläge.
- Das Spiel erscheint sofort in der Sammlung. Der Worker schreibt Rechercheergebnisse **nicht** direkt in die freigegebenen Felder.
- Bei **Vorschläge prüfen** siehst du je Feld **Aktuell** und **KI-Vorschlag** und kannst einzeln **Übernehmen**, **Verwerfen** oder **Alle Vorschläge übernehmen**.
- **Setup**: Verbindung, Ollama, Quellen, Prompt, Backup und Betriebsmodus.

## Quellen und Prompt konfigurieren

Nach dem Start in Brettspielregal unter **Setup → Automatische Recherche – Quellen & Prompt**.

Dort gibt es:

- **Primärquellen** – Hersteller/Verlage
- **Strukturierte Referenzquellen** – standardmäßig `boardgamegeek.com`
- **Niedrig priorisierte Quellen** – Reviews/Händler
- System-Prompt und Recherche-Prompt

Alle frei formulierten KI-Werte sollen auf Deutsch gespeichert werden. BoardGameGeek darf als englische Referenz dienen, wird aber vor der Übernahme durch Qwen auf deutsche Beschreibungen/Tags normalisiert. Technische Werte wie Ollama-URL, Modelle und Timeouts bleiben in Portainer.

Wenn bereits ein eigener Prompt aus v8.2/v8.3 gespeichert ist, wird er nicht überschrieben. Für den neuen v8.5-Standard im Setup **Auf Standard zurücksetzen** wählen. Siehe auch `OLLAMA_PROMPT_V8.5.md`.

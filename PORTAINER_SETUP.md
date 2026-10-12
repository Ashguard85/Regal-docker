# Portainer Stack – Brettspielregal v8

Diese Datei ist für die bestehende Installation auf `192.168.1.127:8190` vorbereitet.

## Was v8 zusätzlich startet

- `app`: die vorhandene Brettspielregal-Web-App.
- `worker`: verarbeitet die automatische Import-Warteschlange **nacheinander** im Hintergrund.
- `searxng`: interne Meta-Websuche für Titel/EAN. Der Dienst bekommt **keinen veröffentlichten Port** und ist nur im Docker-Netz erreichbar.

`app` und `worker` verwenden dasselbe `/app/data`. Die Warteschlange liegt persistent in derselben SQLite-Datenbank.

## Vorher: Ollama-Modelle laden

Auf dem Ollama-Host:

```bash
ollama pull qwen3:14b
ollama pull gemma3:12b
ollama list
```

## Portainer → Stacks → Web editor

Die bisherige Stack-Datei durch diese Version ersetzen:

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
    restart: unless-stopped

  worker:
    image: brettspielregal:local
    build: *app-build
    command: ["python", "-m", "app.import_worker"]
    volumes:
      - /home/buebi/docker/brettspielregal/data:/app/data
      - /home/buebi/docker/brettspielregal/backups:/app/data/backups
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment: *app-environment
    depends_on:
      - searxng
    restart: unless-stopped

  searxng:
    image: docker.io/searxng/searxng:latest
    environment:
      SEARXNG_SECRET: "${SEARXNG_SECRET}"
      FORCE_OWNERSHIP: "false"
    configs:
      - source: searxng_settings
        target: /etc/searxng/settings.yml
    restart: unless-stopped

configs:
  searxng_settings:
    content: |
      use_default_settings: true
      general:
        instance_name: "Brettspielregal Search"
      search:
        safe_search: 1
        formats:
          - html
          - json
      server:
        limiter: false
        image_proxy: false
```

## Portainer-Umgebungsvariablen

Unter dem Stack mindestens setzen:

- `SECRET_KEY`: bisherigen Wert **beibehalten**.
- `SEARXNG_SECRET`: neuer langer Zufallswert, z. B. 40–64 zufällige Zeichen.

`SEARXNG_SECRET` ist nicht der Ollama-Schlüssel; SearXNG verwendet ihn intern für seine Web-App.

## Schnellerfassung verwenden

1. Brettspielregal öffnen.
2. Auf **Schnell** tippen.
3. Pro Zeile einen Spieltitel oder eine EAN eintragen, z. B.:

```text
Sky Team
4002051698973
Cascadia
Dorfromantik
```

4. **Zur Warteschlange** drücken.
5. Du kannst sofort weitere Spiele erfassen oder die PWA schließen.
6. Der Worker recherchiert jeweils **ein Spiel nach dem anderen**, lässt Qwen die Daten strukturieren und speichert sie direkt beim Spiel.

Status in der Sammlung:

- `Wartet` – noch nicht begonnen.
- `Wird ergänzt` – Websuche/Ollama läuft.
- `Automatisch ergänzt` – erfolgreich gespeichert.
- `Bitte prüfen` – gespeichert, aber Quellen waren unvollständig/widersprüchlich.
- `Importfehler` – fehlgeschlagen; über `↻` erneut starten.

## Welche Daten automatisch ergänzt werden

Je nach Quellenlage:

- Titel
- Beschreibung
- Spieler min./max.
- Spieldauer
- Mindestalter
- Verlag
- Erscheinungsjahr
- Autor / Designer
- EAN / GTIN
- Cover-URL
- Auszeichnung
- Tags
- offizieller Anleitungs-Link, wenn er in den gefundenen Quellen eindeutig vorkommt

Vorhandene Anhänge, Notizen und manuell gepflegte Daten bleiben erhalten.

## Verhalten bei Galaxus 403

Der Worker sucht anhand Titel/EAN über SearXNG. Ein Suchtreffer kann auch dann als Hinweis verwendet werden, wenn Galaxus selbst den direkten Abruf mit HTTP 403 blockiert. Der Worker versucht **nicht**, diesen Schutz zu umgehen; er wertet weitere gefundene Quellen aus.

## AUTO_ENRICH_NEW_GAMES

Für deinen gewünschten Workflow ist standardmäßig aktiviert:

```yaml
AUTO_ENRICH_NEW_GAMES: "true"
```

Damit wird **jedes neu angelegte Spiel** automatisch in die Queue gestellt. Bestehende Spiele werden beim normalen Bearbeiten nicht erneut eingereiht.

Wenn du später nur noch die explizite **Schnellerfassung** verwenden möchtest, kannst du auf `false` umstellen.

## SQLite und Worker

Es darf normalerweise nur **ein Worker** laufen. Der Worker verarbeitet absichtlich seriell, damit Qwen den verfügbaren RAM/VRAM möglichst vollständig nutzen kann und externe Quellen nicht parallel belastet werden.

Die Queue ist persistent. Bleibt ein Job nach einem harten Worker-Abbruch länger als 30 Minuten auf `running`, wird er beim nächsten Worker-Lauf automatisch erneut eingereiht.

## Falls Portainer `configs: ... content:` nicht akzeptiert

Inline-Config-Inhalte benötigen eine ausreichend aktuelle Docker-Compose-Implementierung. Falls Portainer beim Deployen meldet, dass `content` unbekannt sei:

1. Auf dem Docker-Host `/home/buebi/docker/brettspielregal/searxng/settings.yml` anlegen.
2. Inhalt:

```yaml
use_default_settings: true
general:
  instance_name: "Brettspielregal Search"
search:
  safe_search: 1
  formats:
    - html
    - json
server:
  limiter: false
  image_proxy: false
```

3. Beim `searxng`-Service `configs:` entfernen und stattdessen mounten:

```yaml
volumes:
  - /home/buebi/docker/brettspielregal/searxng/settings.yml:/etc/searxng/settings.yml:ro
```

## Kontrolle nach dem Deployment

In Portainer sollten drei Container/Services laufen: `app`, `worker`, `searxng`.

In Brettspielregal erscheint in der Sammlung:

- Button **Schnell**
- Bereich **Automatische Ergänzung**
- Badge **Worker online**

Unter **Setup → KI / Link-Auswertung** stehen zusätzlich:

- `Hintergrund-Ergänzung: aktiv`
- `Automatische Websuche: searxng`

Wenn `Worker offline` erscheint, zuerst die Portainer-Logs des `worker`-Services prüfen.

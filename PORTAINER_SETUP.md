# Portainer Stack – Brettspielregal v8.8.3

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

Optional:

```text
BGG_API_TOKEN   = dein BoardGameGeek Application Token (für strukturierte BGG-Daten)
```

Den vorhandenen `SECRET_KEY` nicht ändern. BoardGameGeek verlangt für die XML-API inzwischen Registrierung und einen Bearer/Application-Token. Wenn `BGG_API_TOKEN` leer bleibt, funktioniert Brettspielregal weiter; nur die strukturierte BGG-Identifikation wird übersprungen und die Recherche nutzt Herstellerseiten/SearXNG.

## Web Editor

In **Stacks → Brettspielregal → Web editor** den Stack durch `portainer-stack-v8.8.3.yml` ersetzen oder folgenden Inhalt einfügen:

```yaml
x-app-build: &app-build
  context: https://github.com/Ashguard85/Regal-docker.git#main

x-app-environment: &app-environment
  APP_TITLE: "Brettspielregal"
  APP_URL: "${APP_URL:-http://192.168.1.127:8190}"
  SECRET_KEY: "${SECRET_KEY}"
  PWA_ALLOWED_ORIGINS: "${PWA_ALLOWED_ORIGINS:-https://ashguard85.github.io,http://192.168.1.127:8190}"
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
  AUTO_ENRICH_JOB_TIMEOUT_SECONDS: "900"
  AUTO_ENRICH_STUCK_MINUTES: "10"
  AUTO_SEARCH_PROVIDER: "searxng"
  SEARXNG_BASE_URL: "http://searxng:8080"
  AUTO_SEARCH_RESULTS: "8"
  BGG_ENABLED: "true"
  BGG_API_TOKEN: "${BGG_API_TOKEN:-}"
  BGG_TIMEOUT_SECONDS: "15"
  BGG_MIN_INTERVAL_SECONDS: "5"
  AUTO_FETCH_PAGES: "3"
  AUTO_RESEARCH_MAX_CHARS: "24000"

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


## v8.8.3 – Cover-/Anhang-Hotfix

Für v8.8.3 sind **keine neuen Environment-Variablen** nötig. Eigene Bilder werden in der Detailansicht sofort geladen, das erste hochgeladene Bild wird explizit als Cover gespeichert und ältere implizite Cover-Zuordnungen werden beim Datenbankstart einmalig repariert.

## v8.8.0 – automatische Quellenklassifizierung

Nach dem erfolgreichen Abruf bewertet der Worker den **echten Seiteninhalt** ein zweites Mal. Dadurch kann eine bisher unbekannte Verlagsdomain automatisch als offizielle Quelle erkannt werden, wenn Domain/Verlagsidentität und Seiteninhalt zusammenpassen.

Beispiel `Scythe`: `feuerland-spiele.de` wird durch die erkannte Feuerland-Verlagsidentität, konkrete Spieldaten und Regel-Downloads als offizielle Verlagsseite hochgestuft; Wikipedia bleibt eine allgemeine Referenzquelle. Reviews/Tests und reine Shops werden nach dem Abruf erneut herabgestuft.

Der Worker darf dafür bis zu einige zusätzliche Kandidaten abrufen, gibt aber weiterhin nur die besten `AUTO_FETCH_PAGES` Quellen an Ollama weiter. Es ist keine neue Portainer-Variable nötig.

## v8.7.2 – robustere Webrecherche

Die Suche läuft jetzt gestuft: zuerst deutsch, bei zu wenigen belastbaren Kandidaten automatisch mehrsprachig (`language=all`). Kurze Titel wie `Scythe` werden zusätzlich mit einfachen, unquoted Suchbegriffen gesucht. Blockierte Produktseiten führen nicht sofort zum Abbruch; der Worker probiert weitere Kandidaten.

Ein gültiger `BGG_API_TOKEN` bleibt empfohlen: gelingt die strukturierte BGG-Identifikation, kann der Worker auch bei einer leeren oder vorübergehend gestörten SearXNG-Suche bis zu Ollama weiterarbeiten. Ohne Token kann eine über SearXNG gefundene öffentliche BGG-Spielseite weiterhin als Web-Referenz dienen.

SearXNG-Diagnosen unterscheiden nun zwischen 0 Roh-Treffern, verworfenen unsicheren URLs, nicht antwortenden Engines, zu schwachen Kandidaten und Seiten-Abruffehlern.

## v8.7 – bessere Webrecherche

- `BGG_ENABLED=true` aktiviert die strukturierte BoardGameGeek-Referenz.
- SearXNG dient nur noch zur URL-Findung. Such-Snippets werden nicht als Fakten an Qwen weitergereicht.
- `AUTO_FETCH_PAGES=3` begrenzt die normalen Webseiten; zusammen mit BGG erhält Ollama maximal vier ausgewählte Quellen.
- `AUTO_RESEARCH_MAX_CHARS=24000` hält das Recherchebundle kompakt.
- Bei BGG-Ausfall arbeitet die Suche mit Hersteller-/Verlagsseiten weiter; der Job scheitert nicht allein deshalb.

## v8.5.3 – hängende Jobs

Bei einem laufenden Auftrag erscheint im Import-Tab **Abbrechen**. Der Worker führt jeden Job in einem eigenen Unterprozess aus und kann dadurch auch einen blockierten Web-/Ollama-Aufruf beenden.

Falls ein Auftrag länger als `AUTO_ENRICH_STUCK_MINUTES` keinen Fortschritt zeigt oder eine Abbruchanforderung nicht sauber abgeschlossen wird, bietet die Oberfläche **Hängenden Auftrag freigeben** an. Das Spiel bleibt erhalten; nur der Queue-Auftrag und seine temporären KI-Vorschläge werden verworfen.

`AUTO_ENRICH_JOB_TIMEOUT_SECONDS` ist ein zusätzliches Sicherheitsnetz für die maximale Gesamtlaufzeit eines einzelnen Jobs. Standard sind 900 Sekunden.


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

Ein bereits gespeicherter eigener Prompt wird nicht überschrieben. v8.8 hängt die neue verbindliche Quellenregel automatisch an alte Prompts an. Für den vollständigen neuen Standard kannst du optional **Auf Standard zurücksetzen** wählen. Siehe `OLLAMA_PROMPT_V8.8.md`.


## GitHub Pages und mehrere erlaubte Origins

Für v8.7 wird die Mehrfachvariable verwendet:

```yaml
PWA_ALLOWED_ORIGINS: "https://ashguard85.github.io,http://192.168.1.127:8190"
```

Bei einer eigenen Pages-Domain trägst du deren **Origin** zusätzlich ein, ohne Pfad, z. B. `https://spiele.example.ch`. Ein GitHub-Pages-Projektpfad wie `/brettspielregal/` gehört nicht in die Origin.

Die lokale Docker-Seite auf `http://192.168.1.127:8190` greift same-origin auf die API zu und braucht CORS technisch nicht; der Eintrag schadet jedoch nicht und erleichtert spätere getrennte lokale Frontends.

Für GitHub Pages muss die Backend-URL eine öffentliche HTTPS-Adresse des Reverse Proxys sein. Ollama und SearXNG bleiben intern und werden nicht öffentlich freigegeben.


## v8.8 – Feldbelege und Schnellfreigabe

Für v8.8 sind **keine neuen Environment-Variablen** nötig. Die Feldbelege werden aus den bereits geladenen Quellen berechnet und in SQLite gespeichert. Bestehende offene Vorschläge aus v8.7.x erhalten nicht rückwirkend belastbare Belege; dafür das Spiel einmal **Neu recherchieren**.


## v8.8.3 – Cover in der Sammlung

Keine neuen Environment-Variablen nötig. Der Fix betrifft ausschließlich das Frontend-Laden eigener Cover in der Sammlungsübersicht und die Vermeidung unnötiger Re-Renders beim Queue-Polling.


## v8.8.3 – Eigene Cover im Regal

Für v8.8.3 sind **keine neuen Environment-Variablen** nötig. Im lokalen Docker-/Same-Origin-Betrieb werden eigene Cover direkt über den bestehenden Attachment-Endpunkt als Bild geladen. Dadurch entfällt in der Sammlungsübersicht die bisherige Blob-/IntersectionObserver-Abhängigkeit.

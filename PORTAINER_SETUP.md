# Portainer Stack – Brettspielregal v7

Für die vorhandene Installation auf `192.168.1.127:8190`:

```yaml
services:
  app:
    build:
      context: https://github.com/Ashguard85/Regal-docker.git#main

    ports:
      - "8190:8080"

    volumes:
      - /home/buebi/docker/brettspielregal/data:/app/data
      - /home/buebi/docker/brettspielregal/backups:/app/data/backups

    labels:
      homepage.group: "Spiele"
      homepage.name: "Spielegal"
      homepage.href: "http://192.168.1.127:8190"
      homepage.description: ""
      homepage.showStats: "true"

    extra_hosts:
      - "host.docker.internal:host-gateway"

    environment:
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

    restart: unless-stopped
```

## Ollama-Host vorbereiten

```bash
ollama pull qwen3:14b
ollama pull gemma3:12b
ollama list
```

Wenn `host.docker.internal:11434` mit dem bisherigen `qwen3:8b` bereits funktioniert hat, ist normalerweise keine weitere Netzwerkänderung nötig.

Falls Ollama vom Container nicht erreichbar ist, auf dem Ollama-Host prüfen, auf welcher Adresse Ollama lauscht. Port 11434 sollte für das Docker-Netz erreichbar, aber nicht öffentlich ins Internet veröffentlicht sein.

## Nach dem Deployment

1. Portainer Stack neu deployen.
2. Browser/PWA komplett neu laden.
3. Brettspielregal → Setup → KI / Link-Auswertung.
4. Es sollten `Textmodell: qwen3:14b` und `Bildmodell: gemma3:12b` erscheinen.
5. „KI-Verbindung testen“ drücken. Beide Modelle müssen als vorhanden gemeldet werden.
6. Ein Spiel öffnen → „Screenshot auslesen“ → JPG/PNG/WebP auswählen.

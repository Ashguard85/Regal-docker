# Portainer – Brettspielregal v10.0.0

1. In **Brettspielregal v9.1.6** ein **vollständiges ZIP-Backup** herunterladen und außerhalb des Servers sichern.
2. **Docker-ZIP v10.0.0** vollständig nach `Ashguard85/Regal-docker` (`main`) übernehmen, committen und pushen. Portainer baut sein Image **aus diesem GitHub-Branch**; nur die YAML zu ersetzen genügt nicht.
3. Den neuen Stack `portainer-stack-v10.0.0.yml` in Portainer verwenden und **App und Worker frisch bauen/redeployen**. Deine Daten- und Backup-Volumes unverändert beibehalten.
4. Bestehende `BGG_API_TOKEN`, `SECRET_KEY`, `SEARXNG_BASE_URL` etc. erhalten. `RULE_SEARCH_PROVIDER` ist im mitgelieferten Stack **searxng** (statt `none`); dafür ist kein OpenAI-Key nötig.
5. Im Browser `/api/frontend-build` prüfen (Version 10.0.0, HTML-Build `10.0.0-editions-relations`). iPhone-PWA vollständig schließen und wieder öffnen.
6. Bestehendes Spiel öffnen, bearbeiten, Sprache/Edition ergänzen. Ein Grundspiel und eine Erweiterung zur Kontrolle verknüpfen; nach BGG-Vorschlägen immer **Speichern**.

Schema-Migration auf **13** erfolgt beim Start automatisch. In GitHub Pages ebenfalls das v10-Pages-ZIP ausrollen, damit die Oberflächen zu deinem Backend passen.

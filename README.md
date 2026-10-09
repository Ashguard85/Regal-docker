# Brettspielregal – Docker Fullstack v5.0.0

Brettspielregal ist eine self-hosted Web-App/PWA zur Pflege der eigenen Brettspielsammlung. Das Docker-Paket ist vollständig eigenständig und enthält Flask-Backend, REST-API, Frontend/PWA, SQLite, Migrationen, Import/Export, Backups und die serverseitige Link-Auswertung.

Release-Kompatibilität: **Docker v5.0.0 ↔ Pages v5.0.0**. Datenbank- und Backup-Format bleiben gegenüber v2 kompatibel; v1-Backups werden weiterhin akzeptiert.

## Neu in v5

- umfassendes visuelles Redesign für iPhone, PWA und Desktop
- neue ruhige Grün-/Sand-Farbwelt mit stärkerer visueller Hierarchie
- neue Sammlungskopfzeile, modernere Suche und hochwertigere Buttons
- Brettspielkarten mit Cover oder automatisch erzeugtem Initialen-Platzhalter
- klarere Metadaten-Chips; Auszeichnungen werden optisch hervorgehoben
- überarbeitete Dialoge, Setup-Bereiche, Bottom Navigation und Statusanzeigen
- optimierte Touch-Flächen, Abstände, Safe Areas und kleinere iPhone-Breiten
- neues Offline-Layout und aktualisierte Theme-Farben
- Service-Worker-Cache `brettspielregal-pwa-v5`
- keine Änderung am Datenmodell, an der API oder an der Ollama-Architektur

### Technischer Stand aus v3 bleibt erhalten

- austauschbarer KI-Provider: `ollama`, `openai` oder `none`
- **Ollama ist im Beispiel-Deployment der Standard**
- Ollama wird ausschließlich vom Flask-Backend angesprochen; Browser/PWA sehen Port 11434 nicht
- strukturierte Ausgaben über Ollamas `/api/chat` mit JSON-Schema
- separater KI-Verbindungstest über `/api/ai/status`
- KI-Anbieter und Modell werden im Setup angezeigt, die interne Ollama-URL nicht
- Websuche vollständig von der KI-Analyse getrennt
- `RULE_SEARCH_PROVIDER=none` und `WEB_FALLBACK_PROVIDER=none` als datensparende Standards
- bestehender OpenAI-Provider bleibt optional verfügbar
- Prompt-Injection-Härtung: Seitentext wird ausdrücklich als unvertraute Daten behandelt
- längerer Gunicorn-Timeout für lokale Modelle

## Architektur

```text
Docker-Frontend ─┐
                 ├── HTTPS/REST ── Flask ── SQLite
Pages Server ────┘                   │
                                     └── Ollama (intern/LAN)

Pages Local ─────────────────────────── IndexedDB
                 (keine KI, kein Backend)
```

GitHub Pages ist niemals Voraussetzung für die Docker-App. Das Pages-Frontend spricht auch im Server-Modus **nicht direkt mit Ollama**, sondern ausschließlich mit der öffentlichen Flask-API.

## Datenmodell

Ein Spiel enthält:

`id`, `title`, `description`, `source_url`, `rules_url`, `rules_text`, `min_players`, `max_players`, `play_time_min`, `min_age`, `publisher`, `year`, `designer`, `ean`, `cover_url`, `award`, `tags`, `notes`, `created_at`, `updated_at`.

SQLite-Schema und IndexedDB-Schema bleiben in v5 auf Version 2; v5 benötigt keine neue Datenmigration.

## Ollama vorbereiten

Ollama stellt seine lokale API standardmäßig auf Port `11434` bereit. Für einen Linux-Docker-Host verwendet das Beispiel `host.docker.internal` plus `host-gateway`.

Ein Modell muss auf dem Ollama-Host bereits vorhanden sein, zum Beispiel:

```bash
ollama pull qwen3:8b
```

Prüfen:

```bash
ollama list
```

Wenn Ollama direkt auf einem Linux-Host läuft, bindet es häufig nur an `127.0.0.1`. Damit ein Docker-Container über das Host-Gateway zugreifen kann, muss Ollama auf einer vom Docker-Host erreichbaren Adresse lauschen, z. B. über eine passende `OLLAMA_HOST`-Konfiguration. **Port 11434 nicht über Cloudflare oder das öffentliche Internet veröffentlichen.**

Alternativ kann `OLLAMA_BASE_URL` auf eine interne LAN-Adresse oder den Namen eines separat betriebenen Ollama-Containers zeigen.

## Portainer / Git Deployment

Siehe `docker-compose.example.yml`. Kernausschnitt:

```yaml
services:
  app:
    build:
      context: https://github.com/USER/brettspielregal.git#main
    ports:
      - "8090:8080"
    volumes:
      - /home/USER/docker/brettspielregal/data:/app/data
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      APP_TITLE: Brettspielregal
      APP_URL: https://api.example.com
      SECRET_KEY: ${SECRET_KEY}
      PWA_ALLOWED_ORIGIN: https://app.example.com
      BACKUP_KEEP: "50"

      AI_IMPORT_ENABLED: "true"
      AI_PROVIDER: ollama
      OLLAMA_BASE_URL: http://host.docker.internal:11434
      OLLAMA_MODEL: qwen3:8b
      OLLAMA_TIMEOUT_SECONDS: "120"
      AI_MAX_PAGE_CHARS: "16000"

      RULE_SEARCH_PROVIDER: none
      WEB_FALLBACK_PROVIDER: none
    restart: unless-stopped
```

Liegt die App im Repository-Unterordner `docker`, verwende beim Git-Build `#main:docker`.

## Environment-Variablen

### Allgemein

- `APP_TITLE`: sichtbarer App-Name
- `APP_URL`: öffentliche Backend-Adresse, z. B. `https://api.example.com`
- `SECRET_KEY`: Flask Secret Key
- `PWA_ALLOWED_ORIGIN`: exakt erlaubte Pages-Origin
- `BACKUP_KEEP`: Anzahl rotierender SQLite-Backups, Standard `50`
- `DATA_DIR`: nur Entwicklung/Test; Docker-Standard `/app/data`

### KI

- `AI_IMPORT_ENABLED`: aktiviert serverseitigen Link-Import
- `AI_PROVIDER`: `ollama`, `openai` oder `none`; Standard `ollama`
- `OLLAMA_BASE_URL`: interne Ollama-Adresse; Standard `http://host.docker.internal:11434`
- `OLLAMA_MODEL`: Modellname; Beispiel/Standard `qwen3:8b`
- `OLLAMA_TIMEOUT_SECONDS`: Modell-Timeout; Standard `120`
- `AI_MAX_PAGE_CHARS`: maximale Menge sichtbaren Seitentexts für KI; Standard `16000`

### optionale Cloud-Websuche / OpenAI

- `RULE_SEARCH_PROVIDER`: `none` oder `openai`; Standard `none`
- `WEB_FALLBACK_PROVIDER`: `none` oder `openai`; Standard `none`
- `OPENAI_API_KEY`: nur nötig, wenn OpenAI tatsächlich verwendet wird
- `OPENAI_MODEL`: OpenAI-Modell für Analyse/Websuche

Die alten v2-Flags `AI_RULE_SEARCH_ENABLED` und `AI_IMPORT_WEB_FALLBACK_ENABLED` werden als Rückwärtskompatibilität noch erkannt. Für neue Installationen die Provider-Variablen verwenden.

## Link-Import mit Ollama

Ablauf:

1. Flask validiert die eingegebene HTTPS-URL gegen SSRF.
2. Flask lädt die öffentliche Produktseite mit Zeit- und Größenlimit.
3. JSON-LD, OpenGraph und sichtbare Produktdaten werden ohne KI extrahiert.
4. Der bereinigte, begrenzte Inhalt wird intern an Ollama gesendet.
5. Ollama liefert ein JSON-Schema mit Titel, Beschreibung, EAN, Designer, Verlag, Spielerzahl, Dauer, Alter, Cover, Auszeichnung usw.
6. Widersprüche werden als Warnungen angezeigt.
7. Das Frontend zeigt eine Vorschau.
8. Erst nach Benutzerbestätigung werden Werte in das Formular übernommen.
9. Erst „Speichern“ persistiert den Datensatz.

Ollama ruft die Produktseite **nicht** selbst ab. Die URL-Sicherheitskontrolle bleibt vollständig im Flask-Backend.

## GitHub Pages und Ollama

### Pages – Server-Modus

Funktioniert mit Ollama:

```text
GitHub Pages PWA
    ↓ HTTPS + Cloudflare Access
Flask Backend
    ↓ internes HTTP/LAN
Ollama
```

Die PWA benötigt keine Ollama-Adresse und kein Ollama-Secret.

### Pages – lokaler Modus

Kein Ollama-Zugriff. Spiele liegen ausschließlich in IndexedDB. Link-Import per KI ist deaktiviert. Dadurch gibt es keine Mixed-Content-, Local-Network- oder CORS-Abhängigkeit zu einem lokalen Ollama-Port auf dem iPhone.

## Anleitungssuche

Ollama analysiert lokal nur den Inhalt, den Flask bereits geladen hat. Eine echte Internetsuche ist davon getrennt.

Mit `RULE_SEARCH_PROVIDER=none`:

- vorhandene Anleitungs-Links auf der Produktseite können erkannt und als **nicht zusätzlich verifiziert** vorgeschlagen werden;
- es findet keine externe Suchmaschinen-/Cloud-Anfrage statt.

Mit `RULE_SEARCH_PROVIDER=openai` kann optional eine offizielle Hersteller-/Verlagsquelle per serverseitiger Websuche verifiziert werden. Das ist bewusst opt-in.

## KI-Verbindung testen

Im Setup zeigt die App Anbieter und Modell. „KI-Verbindung testen“ ruft `/api/ai/status` auf. Bei Ollama prüft das Backend `/api/tags` und ob das konfigurierte Modell vorhanden ist.

Es werden dabei weder `OLLAMA_BASE_URL` noch API-Schlüssel an das Frontend ausgegeben.

## API

- `GET /health`
- `GET /api/config`
- `GET /api/ai/status`
- `GET|POST /api/games`
- `GET|PUT|PATCH|DELETE /api/games/<id>`
- `GET /api/export`
- `POST /api/import/preview`
- `POST /api/import`
- `POST /api/ai/from-url`
- `POST /api/ai/rules-search`

## Sicherheit

### Externe Produktseiten

Nur HTTPS auf Port 443. DNS und Peer-IP werden geprüft. Loopback, private, Link-Local, reservierte, Multicast- und unspezifizierte Netze werden blockiert. Redirects werden erneut geprüft. Abrufe besitzen Zeit- und Größenlimits.

### Ollama

`OLLAMA_BASE_URL` ist ausschließlich eine serverseitige Environment-Variable. Sie stammt nie aus Browser-Eingaben und darf bewusst auf ein internes Netz zeigen. Die interne Ollama-API sollte nicht öffentlich exponiert werden; eine lokale Ollama-API besitzt typischerweise keine eigene Authentifizierung.

### Prompt Injection

Produktseiten sind unvertraute Daten. Das KI-System wird explizit angewiesen, Anweisungen im Seitentext zu ignorieren und ausschließlich Metadaten zu extrahieren. KI-Ergebnisse bleiben Vorschläge und werden vor dem Speichern angezeigt.

## Cloudflare / CORS

`PWA_ALLOWED_ORIGIN` muss exakt auf die Pages-Origin gesetzt werden. Erlaubt werden nur diese Origin sowie die benötigten Methoden und Header einschließlich Cloudflare-Service-Token-Headern.

Cloudflare Access muss `OPTIONS`-Preflights passend zum Pages-Origin erlauben bzw. beantworten. Ollama selbst benötigt keine Cloudflare-Ausnahme, weil Pages es nie direkt anspricht.

## SQLite / Backups / Migration

SQLite liegt unter `/app/data/app.sqlite` und verwendet WAL, `synchronous=FULL` und Foreign Keys. Vor destruktiven JSON-Importen wird ein SQLite-Backup unter `/app/data/backups/` erzeugt und über `BACKUP_KEEP` rotiert.

Backup-Format bleibt:

```json
{
  "format": "brettspielregal-backup",
  "version": 2,
  "data": {"games": [], "settings": {}}
}
```

v1- und v2-Backups werden akzeptiert. Server-/Cloudflare-Zugangsdaten, OpenAI-Keys und Ollama-Konfiguration sind nie Bestandteil eines Backups.

## PWA / Update

Service-Worker-Cache: `brettspielregal-pwa-v5`. IndexedDB bleibt Schema 2. Es gibt keine automatische Daten-Synchronisation zwischen lokalem und Server-Modus.

## Update v3 → v5

1. Optional JSON-Backup erstellen.
2. Bestehenden `/app/data`-Mount unverändert behalten.
3. Bestehende v3-Environment-Variablen unverändert beibehalten.
4. Docker v5 neu deployen.
5. Bei Nutzung des Pages-Clients Pages v5 deployen.
6. Browser/PWA einmal neu öffnen; der Service Worker übernimmt den Cache `brettspielregal-pwa-v5`.

Es ist keine SQLite- oder IndexedDB-Datenmigration für v5 erforderlich.

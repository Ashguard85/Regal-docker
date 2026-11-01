# Brettspielregal – GitHub Pages v9.1.5

Statische PWA mit Server-Provider, lokalem IndexedDB-Modus und lesbarer Offline-Momentaufnahme.

## BGG-Erstimport

Im verbundenen Servermodus kann unter **Setup → Automatische Recherche – Quellen & Prompt** die Option **„Erstimport nur über BGG“** gewählt werden (standardmässig aktiviert). Sie gilt für neue Titel ohne Link. Eine bewusste **„Neu recherchieren“**-Aktion nutzt wieder BGG, SearXNG und Verlagsseiten. EANs benötigen eine Websuche und direkt eingegebene HTTPS-Links werden bevorzugt behandelt.

Alle Recherchen und der BGG-API-Token bleiben im Docker-Backend. Im lokalen Pages-Modus wird keine KI-Recherche ausgeführt.

Der PWA-Service-Worker-Cache wurde auf v9.1.5 angehoben. Für einen vollständig konsistenten Betrieb Docker und Pages zusammen aktualisieren.

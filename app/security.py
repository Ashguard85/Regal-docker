import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

MAX_BYTES = 1_000_000
MAX_REDIRECTS = 3


def _validate_ip_value(value):
    ip = ipaddress.ip_address(value)
    if any((ip.is_private, ip.is_loopback, ip.is_link_local, ip.is_reserved, ip.is_multicast, ip.is_unspecified)):
        raise ValueError("Ziele in lokalen, privaten oder reservierten Netzen sind nicht erlaubt.")
    return ip


def validate_public_https_url(url):
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError("Ungültige URL.") from exc
    if parsed.scheme.lower() != "https":
        raise ValueError("Externe Links müssen HTTPS verwenden.")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Ungültige externe URL.")
    if parsed.port not in (None, 443):
        raise ValueError("Für externe Abrufe ist nur HTTPS auf Port 443 erlaubt.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Hostname konnte nicht aufgelöst werden.") from exc
    for info in infos:
        _validate_ip_value(info[4][0])
    return parsed.geturl()


def fetch_public_text(url):
    session = requests.Session()
    session.trust_env = False
    current = validate_public_https_url(url)
    headers = {"User-Agent": "Brettspielregal/3.0 (+self-hosted metadata importer)", "Accept": "text/html,text/plain;q=0.9"}
    for _ in range(MAX_REDIRECTS + 1):
        response = session.get(current, headers=headers, timeout=(4, 8), allow_redirects=False, stream=True)
        try:
            peer = response.raw._connection.sock.getpeername()[0]
            _validate_ip_value(peer)
        except ValueError:
            response.close()
            raise
        except Exception:
            response.close()
            raise ValueError("Die Zieladresse des externen Servers konnte nicht sicher geprüft werden.")
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("Externer Server lieferte eine ungültige Weiterleitung.")
            current = validate_public_https_url(urljoin(current, location))
            continue
        if response.status_code >= 400:
            code = response.status_code
            response.close()
            raise ValueError(f"Externe Seite antwortete mit HTTP {code}.")
        ctype = (response.headers.get("Content-Type") or "").lower()
        if not ("text/html" in ctype or "text/plain" in ctype):
            response.close()
            raise ValueError("Der Link liefert keine HTML- oder Textseite.")
        chunks = []
        size = 0
        for chunk in response.iter_content(16384):
            if not chunk:
                continue
            size += len(chunk)
            if size > MAX_BYTES:
                response.close()
                raise ValueError("Die externe Seite ist für die sichere Auswertung zu groß.")
            chunks.append(chunk)
        encoding = response.encoding or "utf-8"
        response.close()
        return b"".join(chunks).decode(encoding, errors="replace"), current
    raise ValueError("Zu viele Weiterleitungen beim externen Abruf.")

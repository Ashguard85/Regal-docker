import base64
import json
import os
from urllib.parse import urlparse

import requests

TRUE_VALUES = {"1", "true", "yes", "on"}
SUPPORTED_AI_PROVIDERS = {"none", "ollama", "openai"}
SUPPORTED_SEARCH_PROVIDERS = {"none", "openai"}


class AIProviderError(RuntimeError):
    pass


def _env_bool(name, default=False):
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in TRUE_VALUES


def ai_provider_name():
    value = os.environ.get("AI_PROVIDER", "ollama").strip().lower()
    if value not in SUPPORTED_AI_PROVIDERS:
        raise AIProviderError(f"Unbekannter AI_PROVIDER: {value}")
    return value


def search_provider_name(kind="rules"):
    env_name = "RULE_SEARCH_PROVIDER" if kind == "rules" else "WEB_FALLBACK_PROVIDER"
    value = os.environ.get(env_name, "none").strip().lower()
    # Rückwärtskompatibilität zu v2: alte Flags aktivieren OpenAI nur, wenn explizit gesetzt.
    if value == "none":
        legacy_name = "AI_RULE_SEARCH_ENABLED" if kind == "rules" else "AI_IMPORT_WEB_FALLBACK_ENABLED"
        if _env_bool(legacy_name, False):
            value = "openai"
    if value not in SUPPORTED_SEARCH_PROVIDERS:
        raise AIProviderError(f"Unbekannter {env_name}: {value}")
    return value


def _ollama_base_url():
    raw = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434").strip().rstrip("/")
    try:
        parsed = urlparse(raw)
    except Exception as exc:
        raise AIProviderError("OLLAMA_BASE_URL ist ungültig.") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise AIProviderError("OLLAMA_BASE_URL muss eine HTTP(S)-URL ohne eingebettete Zugangsdaten sein.")
    if parsed.query or parsed.fragment:
        raise AIProviderError("OLLAMA_BASE_URL darf keine Query-Parameter oder Fragmente enthalten.")
    if parsed.path not in {"", "/"}:
        raise AIProviderError("OLLAMA_BASE_URL muss auf den Ollama-Host zeigen, ohne /api oder weiteren Pfad.")
    return raw


def _ollama_text_model():
    # OLLAMA_MODEL bleibt als Rückwärtskompatibilität erhalten.
    model = os.environ.get("OLLAMA_TEXT_MODEL", os.environ.get("OLLAMA_MODEL", "qwen3:14b")).strip()
    if not model:
        raise AIProviderError("OLLAMA_TEXT_MODEL/OLLAMA_MODEL ist nicht gesetzt.")
    return model


def _ollama_vision_model():
    model = os.environ.get("OLLAMA_VISION_MODEL", "gemma3:12b").strip()
    if not model:
        raise AIProviderError("OLLAMA_VISION_MODEL ist nicht gesetzt.")
    return model


def _openai_model():
    return os.environ.get("OPENAI_MODEL", "gpt-5.6-luna").strip() or "gpt-5.6-luna"


def _timeout_seconds(name, default, minimum=5, maximum=600):
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    return min(max(value, minimum), maximum)


def _json_from_text(text):
    text = str(text or "").strip()
    if not text:
        raise AIProviderError("Das KI-Modell hat keine Antwort geliefert.")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Einige lokale Modelle setzen trotz Formatvorgabe Markdown-Fences.
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            try:
                return json.loads("\n".join(lines).strip())
            except json.JSONDecodeError:
                pass
        raise AIProviderError("Das KI-Modell hat kein gültiges JSON zurückgegeben.")


def generate_structured(prompt, schema, system=None):
    provider = ai_provider_name()
    if provider == "none":
        raise AIProviderError("KI-Auswertung ist deaktiviert (AI_PROVIDER=none).")
    if provider == "ollama":
        return _ollama_structured(prompt, schema, system=system, model=_ollama_text_model())
    return _openai_structured(prompt, schema, system=system)


def generate_structured_vision(prompt, schema, images, system=None):
    """Structured extraction from one or more images using local Ollama Vision."""
    provider = ai_provider_name()
    if provider == "none":
        raise AIProviderError("KI-Auswertung ist deaktiviert (AI_PROVIDER=none).")
    if provider != "ollama":
        raise AIProviderError("Der Bild-/Screenshot-Import ist derzeit für AI_PROVIDER=ollama vorgesehen.")
    if not images:
        raise AIProviderError("Für den Bildimport wurde kein Bild übergeben.")
    return _ollama_structured(prompt, schema, system=system, model=_ollama_vision_model(), images=images)


def _ollama_structured(prompt, schema, system=None, model=None, images=None):
    base = _ollama_base_url()
    model = model or _ollama_text_model()
    timeout = _timeout_seconds("OLLAMA_TIMEOUT_SECONDS", 120)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    user_message = {"role": "user", "content": prompt}
    if images:
        encoded=[]
        for image in images:
            if not isinstance(image, (bytes, bytearray)) or not image:
                raise AIProviderError("Ungültige Bilddaten für Ollama.")
            encoded.append(base64.b64encode(bytes(image)).decode("ascii"))
        user_message["images"] = encoded
    messages.append(user_message)
    payload = {
        "model": model,
        "messages": messages,
        "format": schema,
        "stream": False,
        "think": False,
        "options": {"temperature": 0},
    }
    try:
        response = requests.post(f"{base}/api/chat", json=payload, timeout=(5, timeout))
    except requests.RequestException as exc:
        raise AIProviderError("Ollama ist vom Docker-Backend nicht erreichbar.") from exc
    if response.status_code >= 400:
        try:
            detail = str(response.json().get("error") or "").strip()
        except Exception:
            detail = ""
        suffix = f" ({detail[:300]})" if detail else ""
        raise AIProviderError(f"Ollama hat die Anfrage abgelehnt{suffix}.")
    try:
        body = response.json()
    except ValueError as exc:
        raise AIProviderError("Ollama hat eine ungültige Antwort geliefert.") from exc
    content = ((body.get("message") or {}).get("content") or "").strip()
    return _json_from_text(content)


def _openai_structured(prompt, schema, system=None):
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise AIProviderError("Für AI_PROVIDER=openai fehlt OPENAI_API_KEY.")
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    inputs = []
    if system:
        inputs.append({"role": "system", "content": system})
    inputs.append({"role": "user", "content": prompt})
    try:
        response = client.responses.create(
            model=_openai_model(),
            input=inputs,
            text={"format": {"type": "json_schema", "name": "brettspielregal_result", "strict": True, "schema": schema}},
        )
    except Exception as exc:
        raise AIProviderError("OpenAI konnte die Anfrage nicht verarbeiten.") from exc
    return _json_from_text(response.output_text)


def openai_web_search_structured(prompt, schema, schema_name="brettspielregal_web_result"):
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise AIProviderError("Für die aktivierte OpenAI-Websuche fehlt OPENAI_API_KEY.")
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    try:
        response = client.responses.create(
            model=_openai_model(),
            tools=[{"type": "web_search"}],
            input=prompt,
            text={"format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema}},
        )
    except Exception as exc:
        raise AIProviderError("Die serverseitige Websuche konnte nicht ausgeführt werden.") from exc
    return _json_from_text(response.output_text)


def provider_public_config():
    try:
        provider = ai_provider_name()
    except AIProviderError:
        provider = "invalid"
    model = ""
    vision_model = ""
    if provider == "ollama":
        model = os.environ.get("OLLAMA_TEXT_MODEL", os.environ.get("OLLAMA_MODEL", "qwen3:14b")).strip()
        vision_model = os.environ.get("OLLAMA_VISION_MODEL", "gemma3:12b").strip()
    elif provider == "openai":
        model = _openai_model()
    try:
        rules_provider = search_provider_name("rules")
    except AIProviderError:
        rules_provider = "invalid"
    try:
        fallback_provider = search_provider_name("fallback")
    except AIProviderError:
        fallback_provider = "invalid"
    return {
        "ai_provider": provider,
        "ai_model": model,
        "ai_vision_model": vision_model,
        "rules_search_provider": rules_provider,
        "web_fallback_provider": fallback_provider,
    }


def provider_status():
    provider = ai_provider_name()
    if provider == "none":
        return {"status": "disabled", "provider": "none", "model": ""}
    if provider == "ollama":
        base = _ollama_base_url()
        model = _ollama_text_model()
        vision_model = _ollama_vision_model()
        try:
            response = requests.get(f"{base}/api/tags", timeout=(3, 8))
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise AIProviderError("Ollama ist vom Docker-Backend nicht erreichbar.") from exc
        names = {str(m.get("name") or "") for m in (data.get("models") or []) if isinstance(m, dict)}
        def has_model(wanted):
            if wanted in names:
                return True
            # Nur bei taglosen Namen (z. B. "gemma3") darf irgendein Tag derselben Familie gelten.
            if ":" not in wanted:
                return any(name.split(":", 1)[0] == wanted for name in names)
            return False
        available = has_model(model)
        vision_available = has_model(vision_model)
        return {
            "status": "ok" if available else "model_missing",
            "provider": "ollama",
            "model": model,
            "model_available": available,
            "vision_model": vision_model,
            "vision_model_available": vision_available,
            "vision_status": "ok" if vision_available else "model_missing",
        }
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        raise AIProviderError("Für AI_PROVIDER=openai fehlt OPENAI_API_KEY.")
    return {"status": "configured", "provider": "openai", "model": _openai_model()}

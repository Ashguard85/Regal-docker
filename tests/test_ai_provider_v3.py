import importlib
import os


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")


def test_ollama_structured_output(monkeypatch):
    os.environ["AI_PROVIDER"] = "ollama"
    os.environ["OLLAMA_BASE_URL"] = "http://host.docker.internal:11434"
    os.environ["OLLAMA_MODEL"] = "qwen3:8b"
    import app.ai_provider as mod
    importlib.reload(mod)

    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured.update(url=url, body=json, timeout=timeout)
        return FakeResponse(200, {"message": {"content": '{"title":"Sky Team"}'}})

    monkeypatch.setattr(mod.requests, "post", fake_post)
    schema = {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}
    result = mod.generate_structured("Produktdaten", schema)
    assert result == {"title": "Sky Team"}
    assert captured["url"].endswith("/api/chat")
    assert captured["body"]["model"] == "qwen3:8b"
    assert captured["body"]["format"] == schema
    assert captured["body"]["stream"] is False


def test_ollama_status_detects_model(monkeypatch):
    os.environ["AI_PROVIDER"] = "ollama"
    os.environ["OLLAMA_MODEL"] = "qwen3:8b"
    import app.ai_provider as mod
    importlib.reload(mod)
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: FakeResponse(200, {"models": [{"name": "qwen3:8b"}]}))
    result = mod.provider_status()
    assert result["provider"] == "ollama"
    assert result["model_available"] is True


def test_search_is_off_by_default():
    os.environ.pop("RULE_SEARCH_PROVIDER", None)
    os.environ.pop("AI_RULE_SEARCH_ENABLED", None)
    import app.ai_provider as mod
    importlib.reload(mod)
    assert mod.search_provider_name("rules") == "none"


def test_public_config_does_not_expose_ollama_url():
    os.environ["AI_PROVIDER"] = "ollama"
    os.environ["OLLAMA_BASE_URL"] = "http://10.0.0.15:11434"
    os.environ["OLLAMA_MODEL"] = "qwen3:8b"
    import app.ai_provider as mod
    importlib.reload(mod)
    cfg = mod.provider_public_config()
    assert cfg["ai_provider"] == "ollama"
    assert cfg["ai_model"] == "qwen3:8b"
    assert "ollama_base_url" not in cfg
    assert "10.0.0.15" not in str(cfg)


def test_ollama_vision_uses_separate_model_and_images(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    monkeypatch.setenv("OLLAMA_TEXT_MODEL", "qwen3:14b")
    monkeypatch.setenv("OLLAMA_VISION_MODEL", "gemma3:12b")
    import app.ai_provider as mod
    importlib.reload(mod)
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured.update(url=url, body=json, timeout=timeout)
        return FakeResponse(200, {"message": {"content": '{"title":"Andor"}'}})

    monkeypatch.setattr(mod.requests, "post", fake_post)
    schema = {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}
    result = mod.generate_structured_vision("Lies das Bild", schema, [b"fake-image"])
    assert result == {"title": "Andor"}
    assert captured["body"]["model"] == "gemma3:12b"
    assert captured["body"]["messages"][-1]["images"]
    assert captured["body"]["think"] is False


def test_status_checks_text_and_vision_tags_exactly(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_TEXT_MODEL", "qwen3:14b")
    monkeypatch.setenv("OLLAMA_VISION_MODEL", "gemma3:12b")
    import app.ai_provider as mod
    importlib.reload(mod)
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: FakeResponse(200, {"models": [{"name":"qwen3:14b"},{"name":"gemma3:12b"}]}))
    result = mod.provider_status()
    assert result["model_available"] is True
    assert result["vision_model_available"] is True
    assert result["vision_model"] == "gemma3:12b"

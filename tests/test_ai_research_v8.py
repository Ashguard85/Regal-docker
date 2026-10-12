import importlib
import os


def test_import_from_research_merges_current_and_ai(monkeypatch):
    os.environ["AI_PROVIDER"] = "ollama"
    import app.ai_import as mod
    importlib.reload(mod)

    monkeypatch.setattr(mod, "generate_structured", lambda *a, **k: {
        "title": "Sky Team",
        "description": "Kooperatives Spiel.",
        "rules_url": "https://example.com/rules.pdf",
        "rules_text": "",
        "min_players": 2,
        "max_players": 2,
        "play_time_min": 20,
        "min_age": 12,
        "publisher": "Beispiel Verlag",
        "year": 2024,
        "designer": "A. Autor",
        "ean": "4000000000001",
        "cover_url": "https://example.com/cover.jpg",
        "award": "",
        "tags": ["Koop"],
        "warnings": [],
    })
    result = mod.import_from_research(
        "Sky Team",
        {"title": "Sky Team", "notes": "Meine Notiz", "source_url": ""},
        "Quelle belegt Spielerzahl und Verlag",
        ["https://example.com/product"],
    )
    assert result["game"]["publisher"] == "Beispiel Verlag"
    assert result["game"]["source_url"] == "https://example.com/product"
    assert result["game"]["notes"] == "Meine Notiz"
    assert result["web_search_used"] is True

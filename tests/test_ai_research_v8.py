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
        "ean": "4002051698973",
        "cover_url": "https://example.com/cover.jpg",
        "award": "",
        "tags": ["Koop"],
        "warnings": [],
    })
    monkeypatch.setattr(mod, "probe_public_asset", lambda url, allowed_prefixes=(): (url, "image/jpeg" if "cover" in url else "application/pdf"))
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


def test_research_keeps_user_title_and_rejects_bad_gtin_and_review_rules(monkeypatch):
    os.environ["AI_PROVIDER"] = "ollama"
    import app.ai_import as mod
    importlib.reload(mod)
    monkeypatch.setattr(mod, "generate_structured", lambda *a, **k: {
        "title":"Looping Chewie - Spieletest.at", "description":"Spiel", "rules_url":"https://spieletest.at/gesellschaftsspiel/3835/looping-chewie",
        "rules_text":"Fazit. Wir sagen nein.", "min_players":2, "max_players":3, "play_time_min":10, "min_age":4,
        "publisher":"Hasbro", "year":2015, "designer":"Carol Wiseley", "ean":"0000000000000",
        "cover_url":"https://spieletest.at/gesellschaftsspiel/3835/looping-chewie", "award":"", "tags":[], "warnings":[]
    })
    result=mod.import_from_research("Looping Chewie", {"title":"Looping Chewie"}, "Reviewmaterial", ["https://spieletest.at/gesellschaftsspiel/3835/looping-chewie"])
    assert result["game"]["title"] == "Looping Chewie"
    assert result["game"]["ean"] == ""
    assert result["game"]["rules_url"] == ""
    assert result["game"]["rules_text"] == ""
    assert result["game"]["cover_url"] == ""
    assert any("EAN" in w for w in result["warnings"])

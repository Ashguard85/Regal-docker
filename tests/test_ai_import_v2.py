import importlib
import os


def test_jsonld_product_extraction(monkeypatch):
    os.environ["AI_PROVIDER"] = "none"
    import app.ai_import as mod
    importlib.reload(mod)
    html = '''<!doctype html><html><head>
    <meta property="og:title" content="Sky Team – Spiel des Jahres 2024">
    <meta property="og:image" content="https://cdn.example.com/sky.jpg">
    <script type="application/ld+json">{
      "@context":"https://schema.org","@type":"Product","name":"Sky Team",
      "description":"Kooperatives Spiel für zwei Personen.","gtin13":"4002051684044",
      "brand":{"@type":"Brand","name":"Kosmos"},"image":"https://cdn.example.com/sky-product.jpg"
    }</script></head><body>
    <div>Spieler: 2 - 2</div><div>Spieldauer: 20 Minuten</div><div>Alter: ab 10 Jahre</div>
    <div>Autor: Luc Rémond</div><div>Erscheinungsjahr: 2024</div><div>Spiel des Jahres 2024</div>
    <a href="https://www.kosmos.de/anleitung/sky-team.pdf">Spielanleitung PDF</a>
    </body></html>'''
    monkeypatch.setattr(mod, "fetch_public_text", lambda url: (html, "https://shop.example/sky"))
    result = mod.import_from_url("https://shop.example/sky")
    game = result["game"]
    assert game["title"] == "Sky Team"
    assert game["ean"] == "4002051684044"
    assert game["publisher"] == "Kosmos"
    assert game["designer"] == "Luc Rémond"
    assert game["min_players"] == 2 and game["max_players"] == 2
    assert game["play_time_min"] == 20
    assert game["min_age"] == 10
    assert game["year"] == 2024
    assert game["award"].lower() == "spiel des jahres 2024"
    assert game["cover_url"] == "https://cdn.example.com/sky-product.jpg"
    assert game["rules_url"].endswith("sky-team.pdf")
    assert result["ai_used"] is False


def test_conflicting_age_creates_warning(monkeypatch):
    os.environ["AI_PROVIDER"] = "none"
    import app.ai_import as mod
    html = '<html><head><title>Test</title></head><body>Alter: ab 10 Jahre\nBeschreibung: ab 12 Jahren</body></html>'
    monkeypatch.setattr(mod, "fetch_public_text", lambda url: (html, "https://example.com/test"))
    result = mod.import_from_url("https://example.com/test")
    assert any("Altersangaben" in w for w in result["warnings"])


def test_rules_link_from_source_without_cloud_search(monkeypatch):
    os.environ["RULE_SEARCH_PROVIDER"] = "none"
    os.environ.pop("AI_RULE_SEARCH_ENABLED", None)
    import app.ai_import as mod
    html = '<html><head><title>Testspiel</title></head><body><a href="https://publisher.example/rules.pdf">Spielanleitung PDF</a></body></html>'
    monkeypatch.setattr(mod, "fetch_public_text", lambda url: (html, "https://shop.example/test"))
    result = mod.search_official_rules({"title": "Testspiel", "source_url": "https://shop.example/test"})
    assert result["rules_url"] == "https://publisher.example/rules.pdf"
    assert result["web_search_used"] is False
    assert result["verified"] is False

import xml.etree.ElementTree as ET


def test_bgg_search_and_thing_parsing(monkeypatch):
    import app.bgg as bgg

    search_xml = ET.fromstring('''<items total="2"><item type="boardgame" id="123"><name type="primary" value="Sky Team"/><yearpublished value="2023"/></item><item type="boardgame" id="456"><name type="primary" value="Sky Team: Erweiterung"/><yearpublished value="2024"/></item></items>''')
    thing_xml = ET.fromstring('''<items><item type="boardgame" id="123"><thumbnail>https://img.example/t.jpg</thumbnail><image>https://img.example/i.jpg</image><name type="primary" value="Sky Team"/><name type="alternate" value="Pilot Duo"/><description>Cooperative &amp; tactical game.</description><yearpublished value="2023"/><minplayers value="2"/><maxplayers value="2"/><playingtime value="20"/><minage value="12"/><link type="boardgamedesigner" id="9" value="Luc Rémond"/><link type="boardgamepublisher" id="10" value="Scorpion Masqué"/><link type="boardgamemechanic" id="11" value="Communication Limits"/></item></items>''')

    def fake_get(path, params):
        return search_xml if path == "search" else thing_xml

    monkeypatch.setattr(bgg, "_get", fake_get)
    rows = bgg.search("Sky Team")
    assert rows[0]["id"] == 123
    ident = bgg.identify("Sky Team", {"title": "Sky Team"})
    assert ident["score"] >= 90
    assert ident["data"]["min_players"] == 2
    assert ident["data"]["designers"] == ["Luc Rémond"]
    assert ident["data"]["mechanics"] == ["Communication Limits"]


def test_bgg_skips_ean_queries(monkeypatch):
    import app.bgg as bgg
    monkeypatch.setattr(bgg, "search", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not search")))
    assert bgg.identify("4002051684044", {"title": "EAN 4002051684044"}) is None


def test_bgg_requires_token(monkeypatch):
    import app.bgg as bgg
    monkeypatch.setenv("BGG_ENABLED", "true")
    monkeypatch.delenv("BGG_API_TOKEN", raising=False)
    try:
        bgg._get("search", {"query":"Cascadia","type":"boardgame"})
        assert False
    except bgg.BGGError as exc:
        assert "BGG_API_TOKEN" in str(exc)


def test_bgg_sends_bearer_token(monkeypatch):
    import app.bgg as bgg
    monkeypatch.setenv("BGG_ENABLED", "true")
    monkeypatch.setenv("BGG_API_TOKEN", "secret-token")
    monkeypatch.setattr(bgg, "_wait_rate_limit", lambda: None)
    seen = {}
    class Response:
        status_code = 200
        content = b'<items></items>'
    def fake_get(url, **kwargs):
        seen.update(kwargs.get("headers") or {})
        return Response()
    monkeypatch.setattr(bgg.requests, "get", fake_get)
    bgg._get("search", {"query":"Cascadia","type":"boardgame"})
    assert seen["Authorization"] == "Bearer secret-token"

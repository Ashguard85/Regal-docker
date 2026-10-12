import importlib
import os
import tempfile


def load(tmp):
    os.environ["DATA_DIR"] = tmp
    import app.db as db
    importlib.reload(db)
    db.init_db()
    import app.research_config as cfg
    importlib.reload(cfg)
    return db, cfg


def test_research_settings_persist_and_normalize():
    with tempfile.TemporaryDirectory() as tmp:
        db, cfg = load(tmp)
        saved = cfg.save_settings({
            "primary_domains": ["https://www.kosmos.de/foo", "ravensburger.de"],
            "low_trust_domains": ["spieletest.at"],
            "system_prompt": "Systemregel",
            "research_prompt": "{{QUERY}} {{CURRENT_GAME}} {{SOURCES}} {{EVIDENCE}} {{PRIMARY_DOMAINS}}",
        })
        assert saved["primary_domains"] == ["kosmos.de", "ravensburger.de"]
        assert cfg.source_trust("https://shop.kosmos.de/game", saved) == "primary"
        assert cfg.source_trust("https://spieletest.at/x", saved) == "low"
        assert cfg.get_settings()["system_prompt"] == "Systemregel"


def test_prompt_requires_core_placeholders():
    with tempfile.TemporaryDirectory() as tmp:
        _, cfg = load(tmp)
        try:
            cfg.save_settings({"research_prompt": "nur {{QUERY}}", "system_prompt": "x"})
            assert False
        except ValueError as exc:
            assert "Pflicht-Platzhalter" in str(exc)

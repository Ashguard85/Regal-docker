from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_checkbox_is_in_both_delivered_html_and_source_in_correct_order():
    for rel in ("frontend/index.html", "app/static/index.html"):
        html = (ROOT / rel).read_text(encoding="utf-8")
        assert 'meta name="brettspielregal-ui-build" content="9.1.6-bgg-toggle"' in html
        assert 'id="initialBggOnlyInput" type="checkbox" checked' in html
        assert html.index('id="researchSettingsForm"') < html.index('id="initialBggOnlyInput"') < html.index("Primärquellen – eine Domain pro Zeile")
        assert 'data-feature="bgg-first-import"' in html
        assert 'id="uiBuildLabel"' in html
        assert 'src="./app.js?v=9.1.6"' in html


def test_frontend_mixed_build_fallback_and_explicit_cache_refresh():
    app = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
    sw = (ROOT / "frontend/service-worker.js").read_text(encoding="utf-8")
    backend = (ROOT / "app/app.py").read_text(encoding="utf-8")
    css = (ROOT / "frontend/app.css").read_text(encoding="utf-8")
    assert 'function ensureInitialBggToggle()' in app
    assert 'ensureInitialBggToggle();\n  bindEvents();' in app
    assert 'if($("initialBggOnlyInput"))return;' in app
    assert 'if($("uiBuildLabel"))' in app
    assert 'updateViaCache:"none"' in app
    assert 'brettspielregal-pwa-v9-1-6' in sw
    assert 'fetch(event.request, {cache:"no-store"})' in sw
    assert 'response.headers["Cache-Control"] = "no-store, max-age=0"' in backend
    assert '@app.route("/api/frontend-build", methods=["GET"])' in backend
    assert 'html_contains_bgg_toggle' in backend
    assert '#researchSettingsForm > .research-mode-toggle' in css


def test_docker_static_is_built_from_shared_source():
    # config.js differs intentionally for Docker/Pages.
    for path in (ROOT / "frontend").rglob("*"):
        if path.is_file() and path.name != "config.js":
            assert path.read_bytes() == (ROOT / "app/static" / path.relative_to(ROOT / "frontend")).read_bytes(), str(path)

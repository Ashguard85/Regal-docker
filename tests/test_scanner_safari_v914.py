from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_scanner_confirms_nonconsecutive_frames_and_shows_progress():
    app = (ROOT / 'frontend/app.js').read_text()
    assert 'now-lastSeenAt<=6000' in app
    assert 'matches>=2||local.hits>=3' in app
    assert 'else if(checks%8===0)' in app
    assert 'Bildverarbeitung fehlgeschlagen' in app
    assert 'video.videoWidth' in app
    assert 'scannerSession++' in app


def test_iphone_still_capture_has_no_external_upload_and_can_restart():
    app = (ROOT / 'frontend/app.js').read_text()
    html = (ROOT / 'frontend/index.html').read_text()
    decoder = (ROOT / 'frontend/ean-scanner.js').read_text()
    assert 'id="barcodePhotoButton"' in html
    assert 'id="barcodePhotoInput"' in html
    assert 'capture="environment"' in html
    assert 'id="barcodeRestartButton"' in html
    assert 'async function scanBarcodePhoto(file)' in app
    assert 'decodeEanImageDataDetailed(ctx.getImageData' in app
    assert 'stopScanner();$("barcodePhotoInput").click()' in app
    assert 'fetch(' not in decoder
    assert 'XMLHttpRequest' not in decoder


def test_cache_contains_scanner_and_released_version():
    sw = (ROOT / 'frontend/service-worker.js').read_text()
    assert 'brettspielregal-pwa-v9-1-4' in sw
    assert './ean-scanner.js' in sw

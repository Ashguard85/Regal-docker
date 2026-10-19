"""Safety and integration checks for the Safari-independent browser decoder."""
from pathlib import Path
import shutil
import subprocess
import pytest

BASE = Path(__file__).resolve().parents[1]


def test_scanner_not_gated_behind_experimental_safari_api():
    app = (BASE / 'frontend/app.js').read_text(encoding='utf-8')
    html = (BASE / 'frontend/index.html').read_text(encoding='utf-8')
    sw = (BASE / 'frontend/service-worker.js').read_text(encoding='utf-8')
    assert 'import {decodeEanImageData,validEan} from "./ean-scanner.js"' in app
    assert 'if(!("BarcodeDetector" in window))' not in app
    assert 'const isIOS=' in app
    assert 'if(!isIOS&&"BarcodeDetector" in window)' in app
    assert 'scannerSession++' in app
    assert 'repeats>=2' in app
    assert './ean-scanner.js' in sw
    assert 'Browser mit BarcodeDetector' not in html
    decoder = (BASE / 'frontend/ean-scanner.js').read_text(encoding='utf-8')
    assert 'fetch(' not in decoder
    assert 'validEan' in decoder


def test_ean_decoder_accepts_valid_examples_and_camera_frame_patterns():
    if not shutil.which('node'):
        pytest.skip('Node.js not available for decoder regression tests')
    result = subprocess.run(
        ['node', str(BASE / 'tests/test_ean_decoder_v912.mjs')],
        cwd=BASE, text=True, capture_output=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert 'EAN local decoder tests passed' in result.stdout

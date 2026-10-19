from pathlib import Path


def test_server_covers_use_native_image_urls_and_blob_fallback_remains():
    base = Path(__file__).resolve().parents[1]
    js = (base / "frontend" / "app.js").read_text(encoding="utf-8")
    providers = (base / "frontend" / "providers.js").read_text(encoding="utf-8")
    assert 'provider?.attachmentImageUrl?.(game.id,selected.id,classes.includes("game-cover"))' in js
    assert 'data-native-cover' in js
    assert 'installNativeCoverFallback(list)' in js
    assert 'attachmentImageUrl(gameId,attachmentId,thumbnail=false)' in providers
    assert 'if(this.creds?.clientId||this.creds?.clientSecret)return "";' in providers
    # Fallback for authenticated cross-origin Pages mode remains available.
    assert 'data-attachment-id=' in js
    assert 'getAttachmentBlob(gameId,attachmentId)' in providers


def test_collection_does_not_rerender_on_every_queue_poll():
    js = (Path(__file__).resolve().parents[1] / "frontend" / "app.js").read_text(encoding="utf-8")
    assert 'if(view==="collection")requestAnimationFrame(()=>renderGames());' in js
    assert 'renderQueue();renderGames();' not in js

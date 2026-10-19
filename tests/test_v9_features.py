import importlib
import io
import json
import os
import tempfile
from unittest.mock import patch

from PIL import Image


def setup_db(folder):
    os.environ['DATA_DIR'] = folder
    from app import db, attachments
    importlib.reload(db)
    importlib.reload(attachments)
    db.init_db()
    return db, attachments


def test_v9_migration_bgg_and_backup_roundtrip():
    with tempfile.TemporaryDirectory() as folder:
        db, _ = setup_db(folder)
        assert db.SCHEMA_VERSION == 11
        game = db.normalize_game({'id': 'g1', 'title': 'Scythe', 'bgg_id': 169786, 'storage_location': 'Wohnzimmer / Tablar 1'})
        db.save_game(game)
        assert db.get_game('g1')['bgg_id'] == 169786
        data = db.backup_payload()
        assert data['version'] == 5
        assert data['data']['games'][0]['bgg_id'] == 169786
        db.import_backup(data, 'replace')
        assert db.get_game('g1')['bgg_id'] == 169786


def test_location_batch_rename_is_persistent_and_backed_up():
    with tempfile.TemporaryDirectory() as folder:
        db, _ = setup_db(folder)
        for id_, loc in [('a','Regal / 1'), ('b','Regal / 1'), ('c','Regal / 2')]:
            db.save_game(db.normalize_game({'id': id_, 'title': id_, 'storage_location': loc}))
        result = db.rename_location('Regal / 1', 'Wohnzimmer / Tablar 1')
        assert result['changed'] == 2
        assert db.get_game('a')['storage_location'] == 'Wohnzimmer / Tablar 1'
        assert db.get_game('c')['storage_location'] == 'Regal / 2'
        assert list(db.BACKUP_DIR.glob('*.sqlite'))


def test_secure_archive_preserves_original_and_makes_thumbnail():
    with tempfile.TemporaryDirectory() as folder:
        db, attachments = setup_db(folder)
        db.save_game(db.normalize_game({'id':'g1','title':'Azul','cover_url':'https://example.org/cover.png','rules_url':'https://example.org/rules.pdf'}))
        im = Image.new('RGB',(900,1200),(25,120,60))
        buf=io.BytesIO();im.save(buf,'PNG');png=buf.getvalue()
        pdf=b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n'
        with patch('app.security.fetch_public_asset', side_effect=[(png,'https://example.org/cover.png'),(pdf,'https://example.org/rules.pdf')]):
            cover=attachments.store_public_asset('g1','https://example.org/cover.png','cover')
            rules=attachments.store_public_asset('g1','https://example.org/rules.pdf','rules')
        assert db.get_game('g1')['cover_attachment_id'] == cover['id']
        assert attachments.read_file(cover['id']) == png
        assert attachments.thumbnail_path(cover['id']).is_file()
        with Image.open(attachments.thumbnail_path(cover['id'])) as thumb:
            assert thumb.format == 'WEBP'
            assert thumb.size[0] <= 480 and thumb.size[1] <= 600
        assert attachments.read_file(rules['id']) == pdf
        export=db.backup_payload()
        assert len(export['data']['attachments']) == 2
        assert export['data']['games'][0]['bgg_id'] is None


def test_frontend_contains_same_filter_and_quick_capture_apis():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    js=(root/'frontend/app.js').read_text()
    providers=(root/'frontend/providers.js').read_text()
    assert 'function advancedMatch(g)' in js
    assert 'async function submitQuickAdd(event)' in js
    assert 'async function archiveAsset(kind)' in js
    assert 'renameLocation(oldName,newName)' in providers
    assert 'archiveAsset(gameId,kind,url)' in providers
    assert 'bgg_id:num(raw.bgg_id)' in providers

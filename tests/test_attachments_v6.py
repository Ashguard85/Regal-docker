import base64
import importlib
import io
import os
import tempfile

PNG = b'\x89PNG\r\n\x1a\n' + b'example image bytes'
PDF = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n'


def load_app(tmp):
    os.environ['DATA_DIR'] = tmp
    os.environ['AI_IMPORT_ENABLED'] = 'false'
    os.environ['AI_PROVIDER'] = 'none'
    import app.db as db
    import app.attachments as files
    import app.app as appmod
    importlib.reload(db)
    importlib.reload(files)
    importlib.reload(appmod)
    return appmod.create_app({'TESTING': True}), db


def upload(c, game_id, data, filename):
    return c.post(f'/api/games/{game_id}/attachments', data={'file': (io.BytesIO(data), filename)}, content_type='multipart/form-data')


def test_upload_gallery_cover_pdf_download_delete():
    with tempfile.TemporaryDirectory() as tmp:
        app, db = load_app(tmp)
        c = app.test_client()
        game = c.post('/api/games', json={'title': 'Azul'}).json
        gid = game['id']
        image = upload(c, gid, PNG, 'mein cover.png')
        pdf = upload(c, gid, PDF, 'Spielregeln.pdf')
        assert image.status_code == 201 and image.json['kind'] == 'image'
        assert pdf.status_code == 201 and pdf.json['kind'] == 'rules'
        listed = c.get('/api/games').json[0]
        assert len(listed['attachments']) == 2
        img_id = image.json['id']
        assert listed['cover_attachment_id'] == img_id
        image_response = c.get(f'/api/games/{gid}/attachments/{img_id}')
        assert image_response.data == PNG
        assert image_response.headers['Cache-Control'] == 'private, no-store'
        assert image_response.headers.get('Content-Disposition', '').startswith('inline')
        assert c.put(f'/api/games/{gid}', json={'title': 'Azul', 'cover_attachment_id': img_id}).status_code == 200
        # Updating a game must NOT cascade-delete its attachments.
        assert len(c.get(f'/api/games/{gid}').json['attachments']) == 2
        assert c.delete(f'/api/games/{gid}/attachments/{img_id}').status_code == 200
        assert c.get(f'/api/games/{gid}').json['cover_attachment_id'] == ''
        assert c.get(f'/api/games/{gid}/attachments/{img_id}').status_code == 404
        assert c.delete(f'/api/games/{gid}').status_code == 200
        assert not list((db.DATA_DIR/'attachments').glob('*'))


def test_backup_roundtrip_and_legacy_import():
    with tempfile.TemporaryDirectory() as tmp:
        app, db = load_app(tmp)
        c = app.test_client()
        gid = c.post('/api/games', json={'title': 'Sky Team'}).json['id']
        assert upload(c, gid, PNG, 'cover.png').status_code == 201
        assert upload(c, gid, PDF, 'regeln.pdf').status_code == 201
        backup = c.get('/api/export').json
        assert backup['version'] == 4
        assert len(backup['data']['attachments']) == 2
        assert PNG in [base64.b64decode(a['content_base64']) for a in backup['data']['attachments']]
        assert c.post('/api/import/preview', json={'backup': backup}).status_code == 200
        assert c.post('/api/import', json={'backup': backup, 'strategy': 'replace'}).status_code == 200
        assert len(c.get(f'/api/games/{gid}').json['attachments']) == 2
        assert c.post('/api/import', json={'backup': backup, 'strategy': 'merge'}).status_code == 200
        assert len(c.get(f'/api/games/{gid}').json['attachments']) == 2
        legacy = {**backup, 'version': 2, 'data': {'games': backup['data']['games'], 'settings': {}}}
        assert c.post('/api/import', json={'backup': legacy, 'strategy': 'merge'}).status_code == 200
        assert len(c.get(f'/api/games/{gid}').json['attachments']) == 2
        assert c.post('/api/import', json={'backup': legacy, 'strategy': 'replace'}).status_code == 200
        assert c.get(f'/api/games/{gid}').json['attachments'] == []


def test_upload_rejects_invalid_files_and_path_traversal():
    with tempfile.TemporaryDirectory() as tmp:
        app, db = load_app(tmp)
        c = app.test_client()
        gid = c.post('/api/games', json={'title': 'Test'}).json['id']
        assert upload(c, gid, b'<script>alert(1)</script>', 'bad.png').status_code == 400
        assert upload(c, gid, b'', 'empty.pdf').status_code == 400
        assert upload(c, gid, PNG, '../../cover.png').status_code == 201
        assert c.get(f'/api/games/{gid}').json['attachments'][0]['filename'] == 'cover.png'
        assert upload(c, gid, b'\xff\xd8\xff' + b'x'*(10*1024*1024), 'large.jpg').status_code == 400
        backup = c.get('/api/export').json
        backup['data']['attachments'][0]['content_base64'] = base64.b64encode(b'not an image').decode()
        assert c.post('/api/import/preview', json={'backup': backup}).status_code == 400

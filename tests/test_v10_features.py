import importlib
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
import pytest


def setup_db(path):
    os.environ['DATA_DIR']=path
    from app import db
    importlib.reload(db)
    db.init_db()
    return db


def test_v10_schema_edition_and_parent_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        db=setup_db(tmp)
        assert db.SCHEMA_VERSION == 13
        base=db.normalize_game({'id':'scythe','title':'Scythe','bgg_id':169786,'game_type':'base', 'original_year':2016, 'edition_language':'Deutsch','edition_year':2017})
        db.save_game(base)
        child=db.normalize_game({'id':'invaders','title':'Invasoren aus der Ferne','game_type':'expansion','base_game_id':'scythe', 'edition_language':'Deutsch','edition_name':'Feuerland','edition_year':2017})
        db.save_game(child)
        assert db.get_game('invaders')['base_game_id']=='scythe'
        assert db.get_game('scythe')['edition_language']=='Deutsch'
        assert db.get_game('scythe')['original_year']==2016
        backup=db.backup_payload()
        assert backup['data']['games'][0]['edition_language'] or backup['data']['games'][1]['edition_language']
        db.import_backup(backup,'replace')
        assert db.get_game('invaders')['base_game_id']=='scythe'


def test_v10_invalid_and_cyclic_relationships_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        db=setup_db(tmp)
        db.save_game(db.normalize_game({'id':'a','title':'A'}))
        with pytest.raises(ValueError,match='eigene'):
            db.save_game(db.normalize_game({'id':'a','title':'A','game_type':'expansion','base_game_id':'a'}))
        with pytest.raises(ValueError,match='existiert'):
            db.save_game(db.normalize_game({'id':'b','title':'B','game_type':'expansion','base_game_id':'missing'}))
        db.save_game(db.normalize_game({'id':'b','title':'B','game_type':'expansion','base_game_id':'a'}))
        with pytest.raises(ValueError,match='Erweiterung'):
            db.save_game(db.normalize_game({'id':'c','title':'C','game_type':'expansion','base_game_id':'b'}))
        db.delete_game('a')
        assert db.get_game('b')['base_game_id']==''


def test_v10_bgg_relation_ids_from_xml(monkeypatch):
    import app.bgg as bgg
    xml=ET.fromstring('''<items><item id="222" type="boardgameexpansion"><name type="primary" value="Scythe: Invaders from Afar"/><link type="boardgameexpansion" id="169786" value="Scythe" inbound="true"/></item></items>''')
    monkeypatch.setattr(bgg,'_get',lambda *args,**kwargs:xml)
    details=bgg.thing(222)
    assert details['expansion_of_ids']==[169786]
    assert details['expansion_of']==['Scythe']
    assert details['expansion_ids']==[]


def test_v10_searxng_rules_are_only_unverified_suggestions(monkeypatch):
    import app.rules_v10 as rules
    monkeypatch.setattr(rules,'searxng_search',lambda *args,**kwargs:[
        {'url':'https://kosmos.de/download/anleitung.pdf','title':'Azul Anleitung PDF','content':'Regeln'},
        {'url':'https://kosmos.de.evil.example/anything.pdf','title':'Azul Anleitung PDF','content':'Regeln'},
        {'url':'https://shop.example/review','title':'Testbericht','content':'Rezension'}])
    monkeypatch.setattr(rules,'get_settings',lambda:{'primary_domains':['kosmos.de']})
    res=rules.rules_candidates({'title':'Azul','publisher':'Kosmos'})
    assert len(res['candidates'])==2
    assert res['candidates'][0]['publisher_domain'] is True
    assert res['candidates'][1]['publisher_domain'] is False
    assert all(x['verified'] is False for x in res['candidates'])


def test_v10_frontend_controls_present():
    root=Path(__file__).resolve().parents[1]
    html=(root/'frontend/index.html').read_text()
    js=(root/'frontend/app.js').read_text()
    for name in ('gameTypeInput','baseGameInput','editionLanguageInput','editionNameInput','editionYearInput','originalYearInput','bggRelationButton','gamePickerOpen','gamePickerDialog','pickerChoose'):
        assert f'id="{name}"' in html
    assert 'duplicateCandidates(data,games' in js
    assert 'provider.rulesCandidates(game)' in js
    assert 'function pickerOpen()' in js
    assert 'openGameDetail' in js

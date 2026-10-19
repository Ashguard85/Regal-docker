"""Regression checks for iOS-Safari edit dialog initially scrolled to bottom."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_existing_game_opens_at_top_without_input_autofocus():
    js = (ROOT / 'frontend/app.js').read_text(encoding='utf-8')
    html = (ROOT / 'frontend/index.html').read_text(encoding='utf-8')
    assert 'id="gameDialogTitle" tabindex="-1"' in html
    helper = js.split('function resetGameDialogToTop(){',1)[1].split('function openGame(game=null){',1)[0]
    assert 'form.scrollTop=0' in helper
    assert 'dialog.scrollTop=0' in helper
    edit = js.split('function openGame(game=null){',1)[1].split('function sizeText(bytes){',1)[0]
    assert 'dialog.showModal();' in edit
    assert 'if(game){' in edit
    assert '$(' + '"gameDialogTitle"' + ').focus({preventScroll:true})' in edit
    assert 'requestAnimationFrame(()=>resetGameDialogToTop())' in edit
    assert 'setTimeout(()=>$("titleInput").focus(),50)' in edit
    assert 'window.scrollTo(' not in edit


def test_scroll_reset_helper_targets_form_and_dialog_only():
    js = (ROOT / 'frontend/app.js').read_text(encoding='utf-8')
    helper = 'function resetGameDialogToTop(){' + js.split('function resetGameDialogToTop(){',1)[1].split('function openGame(game=null){',1)[0]
    scenario = '''
const form={scrollTop:735}, dialog={open:true,scrollTop:241};
const $=id=>id==='gameDialog'?dialog:id==='gameForm'?form:undefined;
resetGameDialogToTop();
if(form.scrollTop!==0||dialog.scrollTop!==0)throw new Error('edit was not reset');
form.scrollTop=535;dialog.open=false;resetGameDialogToTop();
if(form.scrollTop!==535)throw new Error('closed dialog was modified');
'''
    result = subprocess.run(['node', '-e', helper+'\n'+scenario],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr

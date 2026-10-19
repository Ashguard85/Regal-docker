"""Regression coverage: game detail is read-only; mutating controls belong to edit mode."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_game_details_have_only_read_actions():
    html = (ROOT / 'frontend/index.html').read_text()
    detail = html.split('<dialog id="gameDetailDialog"', 1)[1].split('</dialog>', 1)[0]
    editor = html.split('<dialog id="gameDialog"', 1)[1].split('</dialog>', 1)[0]
    assert 'id="detailEditButton"' in detail
    assert 'id="detailBody"' in detail
    assert 'type="file"' not in detail
    for action in ('archiveCoverButton', 'archiveRulesButton', 'detailReEnrichButton',
                   'detailApproveButton', 'editReviewPanel', 'editActionStatus'):
        assert f'id="{action}"' not in detail, action
        assert f'id="{action}"' in editor, action


def test_detail_template_does_not_expose_mutation_actions():
    script = (ROOT / 'frontend/app.js').read_text()
    detail = script.split('function openGameDetail(gameId){', 1)[1].split('async function downloadStoredAttachment(', 1)[0]
    assert 'data-open-attachment' in detail
    assert 'data-cover-attachment' not in detail
    assert 'data-delete-attachment' not in detail
    assert 'data-download-attachment' not in detail
    assert 'data-apply-suggestion' not in detail
    assert 'data-reject-suggestion' not in detail
    assert 'openGame(game)' in detail


def test_review_and_attachment_management_are_in_edit_mode():
    script = (ROOT / 'frontend/app.js').read_text()
    editor = script.split('function renderEditReview(game){', 1)[1].split('function openGameDetail(gameId){', 1)[0]
    assert 'data-apply-suggestion' in editor
    assert 'data-apply-safe-suggestions' in editor
    assert 'data-reject-suggestion' in editor
    assert 'enqueueEnrichment(' in editor
    assert 'renderEditReview(updated)' in editor
    attachments = script.split('function renderEditAttachments(game=null){', 1)[1].split('function addPendingFiles(', 1)[0]
    assert 'data-cover-existing' in attachments
    assert 'data-delete-existing' in attachments
    assert 'data-open-existing' in attachments
    assert 'data-download-existing' in attachments
    assert 'openGame(game);' in script.split('function renderQueue(){', 1)[1].split('function openQueueCleanup(', 1)[0]

"""Atomic independent edits retain artifact revision and recording guarantees."""
import pytest
from jsonschema import validate, ValidationError
from backend.tests.services.reporter.test_artifact_tools import make_ctx, decode, ArtifactRecordingProbe
from backend.services.reporter.runner.tools.artifact_tools import ARTIFACT_TOOL_SPECS, create_artifact, edit_artifact, submit_artifact

def setup_text(text='Alpha beta gamma', recorder=None):
    ctx = make_ctx(recorder)
    create_artifact(ctx, path='article.md', content=text)
    return ctx

def apply(ctx, edits, revision=1, **extra):
    return decode(edit_artifact(ctx, path='article.md', expected_revision=revision, edits=edits, **extra))

def test_batch_records_one_revision_and_matches_original_without_cascading():
    recorder = ArtifactRecordingProbe()
    ctx = setup_text('Alpha beta gamma', recorder)
    r = apply(ctx, [{'old_text': 'gamma', 'new_text': 'delta'}, {'old_text': 'Alpha', 'new_text': 'gamma'}])
    assert r['ok'] and r['changed'] and (r['replacement_count'] == 2)
    assert r['artifact']['content'] == 'gamma beta delta' and r['artifact']['revision'] == 2
    assert len(recorder.mutations) == 2
    assert ctx.artifacts.artifacts['article.md'].snapshots[0].content == 'Alpha beta gamma'
    retry = apply(ctx, [{'old_text': 'gamma', 'new_text': 'delta'}])
    assert retry['error']['code'] == 'revision_conflict'
    assert ctx.artifacts.read('article.md').revision == 2

@pytest.mark.parametrize('edits,code', [([], 'invalid_edit'), ([{'old_text': '', 'new_text': 'x'}], 'invalid_edit'), ([{'old_text': 'Alpha', 'new_text': None}], 'invalid_edit'), ([{'old_text': 'Alpha', 'new_text': 'x', 'extra': 1}], 'invalid_edit'), ([{'old_text': 'Alpha', 'new_text': 'x'}, {'old_text': 'missing', 'new_text': 'y'}], 'match_not_found'), ([{'old_text': 'Alpha', 'new_text': 'x'}, {'old_text': 'Alpha beta', 'new_text': 'y'}], 'overlapping_edits'), ([{'old_text': 'Alpha', 'new_text': 'x'}, {'old_text': 'Alpha', 'new_text': 'y'}], 'overlapping_edits')])
def test_invalid_batch_never_applies_a_valid_prefix(edits, code):
    recorder = ArtifactRecordingProbe()
    ctx = setup_text(recorder=recorder)
    before = ctx.artifacts.model_dump()
    r = apply(ctx, edits)
    assert not r['ok'] and r['error']['code'] == code
    assert ctx.artifacts.model_dump() == before and len(recorder.mutations) == 1

@pytest.mark.parametrize('text,old', [('same same', 'same'), ('aaa', 'aa')])
def test_ambiguous_including_overlapping_occurrences_rejected(text, old):
    ctx = setup_text(text)
    r = apply(ctx, [{'old_text': old, 'new_text': 'x'}])
    assert r['error']['code'] == 'match_not_unique'
    assert ctx.artifacts.read('article.md').content == text

def test_noop_batch_does_not_add_revision_or_record():
    recorder = ArtifactRecordingProbe()
    ctx = setup_text(recorder=recorder)
    r = apply(ctx, [{'old_text': 'Alpha', 'new_text': 'Alpha'}, {'old_text': 'gamma', 'new_text': 'gamma'}])
    assert r['ok'] and (not r['changed']) and (r['artifact']['revision'] == 1) and (len(recorder.mutations) == 1)

def test_adjacent_unicode_and_deletion():
    ctx = setup_text('αβ!')
    r = apply(ctx, [{'old_text': 'α', 'new_text': ''}, {'old_text': 'β', 'new_text': '漢字'}])
    assert r['ok'] and r['artifact']['content'] == '漢字!'

def test_finalized_and_stale_artifact_stay_unchanged():
    ctx = setup_text()
    assert decode(submit_artifact(ctx, path='article.md', expected_revision=1))['ok']
    before = ctx.artifacts.model_dump()
    r = apply(ctx, [{'old_text': 'Alpha', 'new_text': 'Beta'}])
    assert r['error']['code'] == 'artifact_finalized'
    assert ctx.artifacts.model_dump() == before

def test_recording_failure_rolls_back_whole_batch():
    recorder = ArtifactRecordingProbe()
    ctx = setup_text(recorder=recorder)
    before = ctx.artifacts.model_dump()
    recorder.fail = True
    with pytest.raises(Exception, match='artifact|database'):
        apply(ctx, [{'old_text': 'Alpha', 'new_text': 'X'}, {'old_text': 'gamma', 'new_text': 'Y'}])
    assert ctx.artifacts.model_dump() == before and len(recorder.mutations) == 1

def test_schema_and_runtime_reject_mixed_edit_forms():
    params = next((t['function']['parameters'] for t in ARTIFACT_TOOL_SPECS if t['function']['name'] == 'edit_artifact'))
    base = {'path': 'article.md', 'expected_revision': 1}
    single = {'old_text': 'Alpha', 'new_text': 'X'}
    batch = {'edits': [single]}
    validate(base | single, params)
    validate(base | batch, params)
    for invalid in (base, base | single | batch):
        with pytest.raises(ValidationError):
            validate(invalid, params)
    ctx = setup_text()
    r = apply(ctx, [single], old_text='Alpha', new_text='X')
    assert r['error']['code'] == 'invalid_edit'
    assert ctx.artifacts.read('article.md').revision == 1

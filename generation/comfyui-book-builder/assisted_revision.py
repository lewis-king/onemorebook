"""Revisit one approved illustration while preserving the book's other work."""
import copy

from . import assisted_store as store
from .story import digest

RETURN_FIELDS = ('current_stage', 'status', 'job', 'error')
APPROVAL_FIELDS = ('status', 'selected', 'decision_id', 'feedback', 'prompt_base')


def begin(state, stage_id):
    from . import assisted_engine as engine
    if state.get('page_revision'):
        raise store.Conflict('Finish revising this page or keep its original before revising another.')
    if state['status'] not in ('awaiting_review', 'error', 'ready', 'complete'):
        raise store.Conflict('Wait for the current generation to finish before revising an earlier page.')
    target = store.stage(state, stage_id)
    if target['kind'] != 'scene' or target['status'] != 'approved':
        raise ValueError('Only an approved page or cover can be reopened. Story and references stay fixed.')
    if any(stage_id in s.get('references', []) for s in state['stages']):
        raise ValueError('This image is used as a reference by another stage and cannot be reopened independently.')
    engine.approved(state, stage_id)  # Verify the original approval and bytes before changing state.
    revision = {'stage_id': stage_id,
                'return_to': {k: copy.deepcopy(state.get(k)) for k in RETURN_FIELDS},
                'original': {k: copy.deepcopy(target[k]) for k in APPROVAL_FIELDS if k in target}}
    state['page_revision'] = revision
    state.update(current_stage=stage_id, status='awaiting_review', job=None, error=None)
    store.decision(state, engine.selected(state, stage_id), 'reopen', '')
    target['status'] = 'awaiting_review'
    state['revision'] += 1
    store.save(state)
    return state


def finish(state):
    """Called after the replacement receives an explicit human approval."""
    revision = state.pop('page_revision')
    state.update(revision['return_to'])
    if state['status'] == 'complete':
        # An immutable new export keeps the previously finished book accessible.
        state['export_revision'] = digest([
            [s['id'], s['selected'], s['decision_id']] for s in state['stages']])[:16]
        state.update(status='exporting', job=None, error=None)


def keep_original(state):
    revision = state.get('page_revision')
    if not revision:
        raise store.Conflict('No earlier page is being revised.')
    if state['status'] not in ('awaiting_review', 'error', 'ready'):
        raise store.Conflict('Wait for the generation to finish before keeping the original.')
    target = store.stage(state)
    original = next(c for c in target['candidates'] if c['id'] == revision['original']['selected'])
    store.candidate_path(state, original)
    store.decision(state, original, 'keep_original', '')
    for key in APPROVAL_FIELDS:
        target.pop(key, None)
    target.update(copy.deepcopy(revision['original']))
    state.update(revision['return_to'])
    del state['page_revision']
    state['revision'] += 1
    store.save(state)
    return state

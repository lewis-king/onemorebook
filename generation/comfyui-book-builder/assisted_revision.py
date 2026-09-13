"""Revisit one approved illustration while preserving the book's other work.

Pages and covers return to where the reader left off when the replacement is
approved. References (style, characters, moments, props, places and states) are
different: everything that was rendered from them is built on their exact
bytes, so approving a replacement reference marks every dependent stage for
regeneration and the pipeline resumes from the next stage.
"""
import copy

from . import assisted_store as store
from .story import digest

RETURN_FIELDS = ('current_stage', 'status', 'job', 'error')
APPROVAL_FIELDS = ('status', 'selected', 'decision_id', 'feedback', 'prompt_base')
REVISABLE_KINDS = ('scene', 'style', 'character', 'character_state', 'moment', 'prop', 'prop_state', 'location')


def _dependents(state, stage_id):
    """Stages that (transitively) use this stage's exact approved bytes."""
    reverse = {}
    for stage in state['stages']:
        edges = list(stage.get('references') or [])
        if stage.get('source_scene'):
            edges.append(stage['source_scene'])
        for dep in edges:
            reverse.setdefault(dep, []).append(stage['id'])
    found = set()
    queue = list(reverse.get(stage_id, []))
    while queue:
        current = queue.pop()
        if current == stage_id or current in found:
            continue
        found.add(current)
        queue.extend(reverse.get(current, []))
    return found


def _new_export(state):
    state['export_revision'] = digest([
        [s['id'], s['selected'], s['decision_id']] for s in state['stages']])[:16]
    state.pop('publication', None)


def begin(state, stage_id):
    from . import assisted_engine as engine
    if state.get('page_revision'):
        raise store.Conflict('Finish revising this page or keep its original before revising another.')
    if state['status'] not in ('awaiting_review', 'error', 'ready', 'complete'):
        raise store.Conflict('Wait for the current generation to finish before revising an earlier page.')
    target = store.stage(state, stage_id)
    if target['kind'] in ('story', 'plan'):
        raise ValueError('The story and plan stay fixed; revise a page, cover or reference instead.')
    if target['kind'] not in REVISABLE_KINDS or target['status'] != 'approved':
        raise ValueError('Only an approved page, cover or reference can be reopened.')
    if target['kind'] == 'scene' and (any(stage_id in (s.get('references') or []) for s in state['stages'])
                                      or _dependents(state, stage_id)):
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
    target = store.stage(state, revision['stage_id'])
    if target['kind'] == 'scene':
        state.update(revision['return_to'])
        if state['status'] == 'complete':
            # An immutable new export keeps the previously finished book accessible.
            _new_export(state)
            state.update(status='exporting', job=None, error=None)
        return
    # A replaced reference invalidates everything rendered from its old bytes.
    downstream = _dependents(state, revision['stage_id'])
    for stage in state['stages']:
        if stage['id'] in downstream and stage['status'] == 'approved':
            stage['status'] = 'pending'
    index = next(i for i, s in enumerate(state['stages']) if s['id'] == revision['stage_id'])
    if state.get('book_url'):
        _new_export(state)
    state.update(current_stage=state['stages'][index + 1]['id'],
                 status='ready', job=None, error=None)


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

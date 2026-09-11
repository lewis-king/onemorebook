"""Durable full-scene prompts, separate from approved plans and image edits."""
import copy
import hashlib
import json
import uuid

from . import assisted_store as store
from .storage import write_json

VERSION = 1


def signature(state, current, reference_hashes):
    story = store.stage(state, 'story')
    selected = next(c for c in story['candidates'] if c['id'] == story['selected'])
    value = {'story_sha256': selected['sha256'],
             'scene': {k: current.get(k) for k in ('id', 'brief', 'text', 'cast_refs', 'cast_ids', 'references')},
             'design_notes': {sid: store.stage(state, sid)['brief'] for sid in current['references']},
             'reference_sha256': reference_hashes}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def verify(state, stage_id, base):
    if not isinstance(base, dict) or not isinstance(base.get('id'), str):
        raise ValueError('Invalid saved scene prompt.')
    if len(base['id']) != 32 or any(c not in '0123456789abcdef' for c in base['id']):
        raise ValueError('Invalid scene prompt revision ID.')
    path = store.stage_dir(state['id'], stage_id) / 'prompt-bases' / (base['id'] + '.json')
    if json.loads(path.read_text()) != base:
        raise ValueError('Saved scene prompt changed after its revision was recorded.')
    return copy.deepcopy(base)


def snapshot(state, current):
    base = current.get('prompt_base')
    return verify(state, current['id'], base) if base else None


def install(state, stage_id, prompt, context_sha256, *, reason, source, attempt=None):
    """Save a revision without approving an image or rewriting the original plan."""
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 6000:
        raise ValueError('A scene prompt must contain 1–6,000 characters.')
    with store.LOCK:
        latest = store.read(state['id'])
        current = store.stage(latest, stage_id)
        if (current['kind'] != 'scene' or current['status'] == 'approved'
                or latest['current_stage'] != stage_id or latest['status'] == 'complete'):
            raise store.Conflict('Only the current unapproved scene can receive a prompt revision.')
        if attempt is None:
            store.expect_revision(latest, state['revision'])
            if latest['status'] not in ('ready', 'awaiting_review', 'error'):
                raise store.Conflict('Wait for this attempt to finish before changing its base prompt.')
        elif (latest.get('job') or {}).get('attempt') != attempt:
            raise store.Conflict('This prompt revision belongs to an older attempt.')
        old = snapshot(latest, current)
        if old and old['prompt'] == prompt and old['context_sha256'] == context_sha256:
            return old
        base = {'id': uuid.uuid4().hex, 'version': VERSION, 'created_at': store.now(),
                'prompt': prompt, 'context_sha256': context_sha256,
                'reason': reason, 'source': source, 'source_attempt': attempt}
        write_json(store.stage_dir(state['id'], stage_id) / 'prompt-bases' / (base['id'] + '.json'), base)
        current['prompt_base'] = base
        latest['revision'] += 1
        store.save(latest)
        return copy.deepcopy(base)

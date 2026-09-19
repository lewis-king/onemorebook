"""Durable human-review sessions. Candidates and decisions are never overwritten."""
import datetime
import hashlib
import json
from pathlib import Path
import re
import threading
import uuid

from .storage import books_root, write_exclusive, write_json
from .preview import atomic_view

LOCK = threading.RLock()
SESSION_RE = re.compile(r'book-(?:assisted-)?\d{14}-[a-f0-9]{10}')


class Conflict(ValueError):
    pass


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def root(session_id):
    if not isinstance(session_id, str) or not SESSION_RE.fullmatch(session_id):
        raise ValueError('Invalid book session.')
    path = books_root() / session_id
    if not path.exists() and not session_id.startswith('book-assisted-'):
        legacy = books_root() / session_id.replace('book-', 'book-assisted-', 1)
        if (legacy / 'creator.json').is_file():
            return legacy
    return path


def creator_url(session_id):
    return '/book-builder/create/' + session_id.replace('book-assisted-', 'book-', 1)


def read(session_id):
    return json.loads((root(session_id) / 'creator.json').read_text())


def save(state):
    state['updated_at'] = now()
    atomic_view(root(state['id']) / 'creator.json',
                (json.dumps(state, indent=2, ensure_ascii=False) + '\n').encode())


def stage(state, stage_id=None):
    stage_id = stage_id or state['current_stage']
    return next(s for s in state['stages'] if s['id'] == stage_id)


def stage_dir(session_id, stage_id):
    # Only known stage IDs may address files; the transformation is not a sanitizer.
    stage(read(session_id), stage_id)
    return root(session_id) / 'creator' / 'stages' / stage_id.replace('/', '__')


def config(values):
    from .planning import DEFAULT_WRITER_MODEL
    from .story_craft import preferences, ART, DEFAULT_AGE
    from .story_craft_auto import ART_DIRECTION
    from .assisted_story import AUTO_MIN, AUTO_MAX, AUTO_TARGET
    from . import assisted_moment
    craft = preferences(values)
    automatic = craft['story_craft_version'] == 'picturebook-2'
    result = {'story_idea': str(values.get('story_idea', '')).strip(),
              'art_style': str(values.get('art_style') or '').strip() or (ART_DIRECTION if automatic else ART[craft['art_preset']][1]),
              'age_range': str(values.get('age_range', DEFAULT_AGE)),
              'page_count': int(values.get('page_count', 0 if automatic else 14)),
              'max_characters': int(values.get('max_characters', 3)),
              'seed': int(values.get('seed', int(datetime.datetime.now().timestamp() * 1000))),
              'ollama_url': 'http://127.0.0.1:11434', 'ollama_model': DEFAULT_WRITER_MODEL,
              'review_model': 'gemma4:31b', 'prose_format': 'plain-v2', 'version': 'assisted-1',
              **craft}
    mode = str(values.get('mode', 'scratch'))
    if mode not in ('scratch', 'moment'):
        raise ValueError("Choose 'scratch' or 'moment'.")
    approval = str(values.get('approval_mode', 'assisted'))
    if approval not in ('assisted', 'yolo'):
        raise ValueError("Choose 'assisted' or 'yolo' review.")
    # YOLO is the explicit, recorded acceptance that the AI judge may approve
    # candidates for this book; every such decision is stamped source 'yolo'.
    result['approval_mode'] = approval
    if mode == 'moment':
        result['mode'] = 'moment'
        result['moment'] = assisted_moment.validate_submission(values)
        # A moment book follows the day exactly: one page per photograph, no
        # invented pages and none left out.
        result['page_count'] = len(result['moment']['photos'])
    elif values.get('moment'):
        raise ValueError('Photographs only belong in a from-a-moment book.')
    inspiration = str(values.get('art_inspiration', '')).strip()
    if len(inspiration) > 300:
        raise ValueError('Keep the art inspiration under 300 characters.')
    if inspiration:
        result['art_inspiration'] = inspiration
    if result['page_count'] == 0 and automatic:
        result.update(page_count_min=AUTO_MIN, page_count_max=AUTO_MAX, page_count_target=AUTO_TARGET)
    elif result.get('mode') != 'moment' and not 2 <= result['page_count'] <= 24:
        raise ValueError('Choose 2–24 pages, or leave length automatic.')
    if not 1 <= result['max_characters'] <= 6:
        raise ValueError('Choose 1–6 characters.')
    if not 0 <= result['seed'] < 2**53:
        raise ValueError('Seed must be a nonnegative safe integer.')
    if len(result['story_idea']) > 10000 or len(result['art_style']) > 2000 or len(result['age_range']) > 40:
        raise ValueError('Book settings are too long.')
    return result


def new_stage(stage_id, kind, title):
    return {'id': stage_id, 'kind': kind, 'title': title, 'status': 'pending',
            'candidates': [], 'selected': None, 'feedback': ''}


def create(values):
    with LOCK:
        sid = 'book-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S') + '-' + uuid.uuid4().hex[:10]
        conf = config(values)
        state = {'version': 1, 'id': sid, 'created_at': now(), 'revision': 0,
                 'config': conf, 'status': 'ready', 'current_stage': 'story',
                 'stages': [new_stage('story', 'story', 'Story'), new_stage('plan', 'plan', 'Characters, props and places')],
                 'job': None, 'error': None}
        root(sid).mkdir(parents=True, exist_ok=False)
        if conf.get('mode') == 'moment':
            # Photographs are single-use: each staged upload lands inside this
            # book with its hash pinned, then the staged file is consumed.
            from . import assisted_moment
            state['config']['moment'] = assisted_moment.intake_photos(sid, conf['moment'])
        save(state)
        return state


def listing():
    result = []
    for path in books_root().glob('book-*/creator.json'):
        try:
            state = json.loads(path.read_text())
            if state.get('verification_only') or not SESSION_RE.fullmatch(state.get('id', '')):
                continue
            result.append({**{k: state.get(k) for k in ('id', 'created_at', 'updated_at', 'status', 'current_stage', 'title')},
                           'creator_url': creator_url(state['id'])})
        except (OSError, ValueError):
            continue
    return sorted(result, key=lambda s: s['created_at'], reverse=True)


def expect_revision(state, revision):
    if type(revision) is not int or revision != state['revision']:
        raise Conflict('This book changed in another tab. Refresh before deciding.')


def next_attempt(state, feedback='', *, mode='fresh', source_candidate=None, prompt_override=''):
    current = stage(state)
    if current['status'] == 'approved' or state['status'] == 'complete':
        raise Conflict('This stage is already approved.')
    attempt = max([c['attempt'] for c in current['candidates']] + [0]) + 1
    # Failed/interrupted submissions also own their attempt number.
    intents = list(stage_dir(state['id'], current['id']).glob('attempt-*/intent.json'))
    if intents:
        attempt = max(attempt, max(int(p.parent.name.split('-')[-1]) for p in intents) + 1)
    directory = stage_dir(state['id'], current['id']) / f'attempt-{attempt:04d}'
    intent = {'session_id': state['id'], 'stage_id': current['id'], 'attempt': attempt,
              'feedback': feedback.strip(), 'created_at': now(), 'mode': mode,
              'source_candidate': source_candidate, 'prompt_override': prompt_override}
    if current['kind'] == 'scene' and mode == 'fresh':
        from . import assisted_prompt_base
        intent['scene_prompt_version'] = assisted_prompt_base.VERSION
        intent['prompt_base'] = assisted_prompt_base.snapshot(state, current)
    write_json(directory / 'intent.json', intent)
    current['feedback'] = feedback.strip()
    current['status'] = 'generating'
    state.update(status='queued', error=None, job={**intent, 'prompt_id': None})
    state['revision'] += 1
    save(state)
    return intent


def candidate_path(state, candidate):
    path = (root(state['id']) / candidate['path']).resolve()
    if not path.is_relative_to(root(state['id']).resolve()) or not path.is_file():
        raise ValueError('Candidate file is missing or outside this book.')
    if hashlib.sha256(path.read_bytes()).hexdigest() != candidate['sha256']:
        raise ValueError('Candidate changed after generation. It cannot be approved.')
    return path


def record_candidate(session_id, stage_id, attempt, path, metadata=None):
    with LOCK:
        state = read(session_id); current = stage(state, stage_id)
        relative = Path(path).resolve().relative_to(root(session_id).resolve()).as_posix()
        candidate = {'id': f'{stage_id}:{attempt}', 'attempt': attempt, 'path': relative,
                     'sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                     'created_at': now(), 'metadata': metadata or {}}
        previous = next((c for c in current['candidates'] if c['attempt'] == attempt), None)
        if previous:
            if previous['sha256'] != candidate['sha256']:
                raise Conflict('This attempt already has a different saved result.')
            return state
        current['candidates'].append(candidate)
        current['selected'] = candidate['id']
        current['status'] = 'awaiting_review'
        state.update(status='awaiting_review', error=None)
        if stage_id=='story' and isinstance(candidate['metadata'].get('content'),dict):
            title=candidate['metadata']['content'].get('story',{}).get('metadata',{}).get('title')
            if isinstance(title,str):state['title']=title
        state['revision'] += 1
        save(state)
        return state


def decision(state, candidate, action, feedback, source='human'):
    if source not in ('human', 'yolo'):
        raise ValueError('Unknown decision source.')
    record = {'id': uuid.uuid4().hex, 'at': now(), 'session_id': state['id'],
              'stage_id': state['current_stage'], 'candidate_id': candidate['id'],
              'candidate_sha256': candidate['sha256'], 'action': action,
              'feedback': feedback, 'source': source, 'revision': state['revision']}
    write_json(root(state['id']) / 'creator' / 'decisions' / (record['id'] + '.json'), record)
    return record

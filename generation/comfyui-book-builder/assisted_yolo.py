"""YOLO review mode: a local vision-language judge decides candidates for books
whose creator explicitly opted in (config.approval_mode == 'yolo').

The judge mirrors what a human reviewer checks, per stage kind, and every
verdict is recorded as a decision with source 'yolo' next to the human ones.
It fails closed: uncertainty, transport errors and exhausted retries all park
the stage for a human instead of approving or looping. Hard contract
validation in engine.advance still runs on every approval — a judge pass can
never approve a draft that breaks the story contract.
"""
import json
import time

from . import assisted_store as store
from . import quality
from .story import asset_seed, object_schema

JUDGE_VERSION = 'yolo-2'
MAX_AUTO_RETRIES = 3        # judge-requested regenerations per stage
MAX_STYLE_TAKE_POOL = 8     # two rounds of the four-take style loop, then park

# Benchmarked on the real adjudication cases (.local/judge-bench): gemma4:31b
# judges single-image stages without false rejects but misranks the four-image
# style comparison; qwen3.5-27b ranks the takes correctly. So the style stage
# gets the ranker, everything else keeps the steadier single-image judge.
DEFAULT_STYLE_REVIEW_MODEL = 'hf.co/unsloth/Qwen3.5-27B-GGUF:Q6_K'

TEXT = {'type': 'string', 'minLength': 1}

SCENE_CHECKS = ('scene_matches', 'photo_fidelity', 'characters_on_model',
                'style_matches', 'anatomy_sound', 'no_unwanted_text', 'age_safe')
REFERENCE_CHECKS = ('design_matches', 'style_matches', 'clean_reference', 'no_unwanted_text')
STORY_CHECKS = ('age_appropriate', 'coherent_arc', 'read_aloud', 'matches_request', 'engaging')
PLAN_CHECKS = ('covers_story', 'reusable_references', 'continuity_sound', 'matches_request')


def enabled(state):
    return state['config'].get('approval_mode') == 'yolo'


def _candidate_bytes(state, candidate):
    return store.candidate_path(state, candidate).read_bytes()


def _approved_bytes(state, stage_id):
    from . import assisted_engine as engine
    return engine.approved(state, stage_id).read_bytes()


def _context(state):
    config = state['config']
    lines = [f"The book is for ages {config.get('age_range', '4-7')}."]
    if config.get('story_idea'):
        lines.append('The creator asked for: ' + config['story_idea'])
    moment = config.get('moment')
    if moment:
        lines.append("This book commemorates a real day, described as: " + moment.get('description', ''))
        lines.append('Photograph captions, in the order of the day: '
                     + ' | '.join(f"{p['id']}: {p['caption']}" for p in moment.get('photos', [])))
    if config.get('art_inspiration'):
        lines.append("Art inspiration from the reader's world (always interpreted cutely and "
                     'age-appropriately): ' + config['art_inspiration'])
    return '\n'.join(lines)


def _passed(report, checks):
    """Strict pass for our own check sets (quality.passed only knows the legacy gates)."""
    return (set(report.get('checks', {})) == set(checks)
            and all(report['checks'][c] is True for c in checks)
            and report.get('uncertain') is False
            and not report.get('issues')
            and bool(report.get('evidence')))


def _verdict_from_report(report, checks, candidate_id=None):
    if report.get('uncertain'):
        # Fail closed: an unsure judge never retries blindly nor approves.
        return _uncertain_verdict('The AI judge was unsure about this attempt — please review it yourself.')
    passed = _passed(report, checks)
    feedback = ('; '.join(report.get('issues') or []) or report.get('evidence', '')).strip()
    return {'action': 'approve' if passed else 'retry', 'feedback': feedback,
            'candidate_id': candidate_id, 'report': report}


def _uncertain_verdict(note):
    return {'action': 'park', 'feedback': note, 'candidate_id': None,
            'report': {'uncertain': True, 'evidence': note, 'issues': [], 'checks': {}}}


def judge_text(state, stage, candidate):
    content = candidate['metadata'].get('content')
    error = candidate['metadata'].get('validation_error')
    if error:
        # No model call needed: feed the exact contract failure back to the writer.
        return {'action': 'retry', 'candidate_id': candidate['id'],
                'feedback': 'The draft failed the story contract: ' + error,
                'report': {'validation_shortcut': True, 'evidence': error, 'issues': [error],
                           'checks': {}, 'uncertain': False}}
    checks = STORY_CHECKS if stage['kind'] == 'story' else PLAN_CHECKS
    schema = quality.review_schema(checks)
    if stage['kind'] == 'story':
        task = ('Review this children\'s picture-book story draft. Check: age_appropriate (gentle, '
                'safe, warm for the age band), coherent_arc (clear beginning, middle and satisfying '
                'end), read_aloud (rhythmic, concrete, enjoyable to read aloud), matches_request (it '
                'delivers what the creator asked for, and for a real-day book it honours every '
                'photograph caption in order), engaging (a child would want it read again).')
    else:
        task = ('Review this illustration plan for the approved story. Check: covers_story (every '
                'page and the cover has a scene that matches its text), reusable_references (only '
                'truly recurring characters, props and places become references; one-off moments do '
                'not), continuity_sound (states and visible_pages keep designs consistent), '
                'matches_request (it respects the creator\'s brief).')
    prompt = (task + '\n' + _context(state) + '\nDraft JSON:\n'
              + json.dumps(content, ensure_ascii=False)
              + '\nJudge strictly but fairly; list concrete issues only when something should change.')
    report = _call(state, stage, candidate, prompt, schema, (), 32768)
    return _verdict_from_report(report, checks, candidate['id'])


def judge_style(state, stage):
    from . import assisted_engine as engine
    current = state['config'].get('art_inspiration', '') or ''
    matching = [c for c in stage['candidates']
                if (c['metadata'].get('style_inspiration') or '') == current]
    pool = matching[-engine.MAX_STYLE_TAKES:]
    if not pool:
        return _uncertain_verdict('No style takes to judge yet.')
    schema = object_schema({'best_image': {'type': 'integer', 'minimum': 1, 'maximum': len(pool)},
                            'acceptable': {'type': 'boolean'}, 'uncertain': {'type': 'boolean'},
                            'evidence': TEXT, 'issues': {'type': 'array', 'items': TEXT}})
    prompt = ('You are choosing the art style for a whole children\'s picture book. '
              + _context(state)
              + '\nStyle direction: ' + stage['brief']
              + '\n' + '\n'.join(f'IMAGE{i+1} is style take {c["attempt"]}.' for i, c in enumerate(pool))
              + '\nEvery take must itself be a digital artwork: a photograph of a physical print, '
                'card, object, room or pet is a failed take, however pretty the picture inside it. '
                'Pick the single best take (best_image) for young children: appealing, warm, '
                'technically clean, true to the direction, with no text, collage or watermark. '
                'The take MUST be completely unoccupied: check every corner and edge — any person, '
                'animal or creature in a take makes that take unacceptable, no matter how lovely — '
                'this picture anchors technique only, and stray characters would leak into every '
                'page. acceptable is true only if best_image is unoccupied AND good enough to '
                'anchor the whole book. When no take is acceptable, say exactly what is missing '
                'in issues.')
    report = _call(state, stage, pool[0], prompt, schema,
                   [_candidate_bytes(state, c) for c in pool], 32768,
                   model=config_style_model(state))
    chosen = pool[report['best_image'] - 1]
    if report.get('uncertain'):
        return _uncertain_verdict('The AI judge was unsure about the style takes — please choose one.')
    if report.get('acceptable') and report.get('best_image'):
        report.setdefault('checks', {})
        return {'action': 'approve', 'candidate_id': chosen['id'],
                'feedback': f"Chose take {chosen['attempt']} of {len(pool)}. " + report.get('evidence', ''),
                'report': report}
    if len(matching) >= MAX_STYLE_TAKE_POOL:
        return {'action': 'park', 'candidate_id': None,
                'feedback': 'The AI judge found no acceptable style take after '
                            f'{len(matching)} attempts: ' + '; '.join(report.get('issues') or ['no take passed']),
                'report': report}
    return {'action': 'retry', 'candidate_id': chosen['id'],
            'feedback': '; '.join(report.get('issues') or ['None of the style takes passed.']),
            'report': report}


def judge_reference(state, stage, candidate):
    images = [_candidate_bytes(state, candidate)]
    labels = []
    for name in stage.get('references', [])[:2]:
        images.append(_approved_bytes(state, name))
        labels.append(f'IMAGE{len(images)} is the approved reference "{store.stage(state, name)["title"]}".')
    schema = quality.review_schema(REFERENCE_CHECKS)
    prompt = ('Review IMAGE1 as a reusable reference image for a children\'s picture book. '
              + ' '.join(labels)
              + '\nIt should depict: ' + stage['brief']
              + '\n' + _context(state)
              + '\nCheck: design_matches (the subject matches its described appearance), '
                'style_matches (same paint/line technique, palette and lighting treatment as the '
                'approved style — never require the same subject or scenery), clean_reference ('
                'the subject is complete and clearly usable as a design reference; a character or '
                'prop sits on a plain backdrop with nothing extraneous baked in), no_unwanted_text '
                '(no letters, words or watermarks). Reject only real, visible problems and give '
                'concrete corrections in issues.')
    report = _call(state, stage, candidate, prompt, schema, images, 16384)
    return _verdict_from_report(report, REFERENCE_CHECKS, candidate['id'])


def judge_scene(state, stage, candidate):
    images = [_candidate_bytes(state, candidate)]
    parts = ['IMAGE1 is the candidate illustration under review.']
    photo = stage.get('source_photo')
    if photo:
        images.append((store.root(state['id']) / photo['path']).read_bytes())
        parts.append(f'IMAGE{len(images)} is the real photograph this page recreates '
                     f'(caption: {photo["caption"]}).')
    for name in stage.get('cast_refs', [])[:2]:
        images.append(_approved_bytes(state, name))
        parts.append(f'IMAGE{len(images)} is an approved character reference.')
    fidelity = ('photo_fidelity (the illustration recreates the photograph: same people, poses, key '
                'objects and setting; the storybook style change is expected and is NOT a mismatch; '
                'added flourishes fail only when they contradict the photo), '
                if photo else
                'photo_fidelity (no photograph for this page — mark true), ')
    cast = ('characters_on_model (the people match the approved character references in clothing, '
            'colours and features), ' if stage.get('cast_refs') else
            'characters_on_model (no character references supplied — mark true), ')
    title_note = (' The page text below is empty because this is the cover: the requested book title '
                  'IS expected as lettering, and only other text fails no_unwanted_text.'
                  if stage.get('page') == 0 else '')
    schema = quality.review_schema(SCENE_CHECKS)
    prompt = ('Review a children\'s picture-book illustration. ' + ' '.join(parts)
              + '\nIllustration brief: ' + stage['brief']
              + ('\nPage text: "' + stage['text'] + '"' if stage.get('text') else '')
              + '\n' + _context(state)
              + '\nCheck: scene_matches (the action and composition deliver the brief'
              + (' and page text' if stage.get('text') else '') + '), '
              + fidelity + cast
              + 'style_matches (storybook illustration, not a photograph), anatomy_sound (no extra '
                'limbs, fused hands or distorted faces), no_unwanted_text (no rendered words or '
                'letters), age_safe (nothing scary or inappropriate for young children).'
              + title_note
              + '\nJudge what is actually visible; do not invent hidden details. List concrete '
                'issues only when something should change, phrased as corrections for the artist.')
    report = _call(state, stage, candidate, prompt, schema, images, 32768)
    return _verdict_from_report(report, SCENE_CHECKS, candidate['id'])


def config_style_model(state):
    return state['config'].get('style_review_model') or DEFAULT_STYLE_REVIEW_MODEL


def _call(state, stage, candidate, prompt, schema, images, num_ctx, model=None):
    from .storage import write_json
    from . import assisted_engine as engine
    config = state['config']
    model = model or config.get('review_model', quality.DEFAULT_REVIEW_MODEL)
    seed = asset_seed(config['seed'], 'judge:' + stage['id'] + ':' + str(candidate['attempt']))
    started = time.monotonic()
    report = quality.json_model(config['ollama_url'], model,
                                prompt, schema, images=images, seed=seed, num_ctx=num_ctx)
    directory = engine.directory(state['id'], stage['id'], candidate['attempt'])
    # Never overwrite a saved report: a re-judge after a restart gets the next name.
    report_path = directory / 'judge-report.json'
    n = 1
    while report_path.exists():
        n += 1
        report_path = directory / f'judge-report-{n}.json'
    write_json(report_path,
               {'judge_version': JUDGE_VERSION, 'model': model,
                'stage_id': stage['id'], 'attempt': candidate['attempt'], 'prompt': prompt,
                'image_count': len(images), 'seconds': round(time.monotonic() - started, 2),
                'report': report})
    return report


def judge_session(sid):
    """Review the selected candidate of the current stage. Runs off the event loop."""
    state = store.read(sid)
    stage = store.stage(state)
    candidate = next(c for c in stage['candidates'] if c['id'] == stage['selected'])
    if stage['kind'] in ('story', 'plan'):
        return judge_text(state, stage, candidate)
    if stage['kind'] == 'style':
        return judge_style(state, stage)
    if stage['kind'] == 'scene':
        return judge_scene(state, stage, candidate)
    return judge_reference(state, stage, candidate)


def apply_verdict(state, verdict):
    """Apply a judge verdict to the state. Returns True when the pipeline should drive on."""
    from . import assisted_engine as engine
    stage = store.stage(state)
    candidate = next((c for c in stage['candidates'] if c['id'] == verdict.get('candidate_id')), None)
    if candidate is None:
        candidate = next(c for c in stage['candidates'] if c['id'] == stage['selected'])
    if verdict['action'] == 'approve':
        record = store.decision(state, candidate, 'approve', verdict['feedback'], source='yolo')
        engine.advance(state, candidate, record)
        return state['status'] not in ('awaiting_review', 'complete')
    if verdict['action'] == 'retry' and stage.get('auto_retries', 0) < MAX_AUTO_RETRIES:
        store.decision(state, candidate, 'reject', verdict['feedback'], source='yolo')
        stage['auto_retries'] = stage.get('auto_retries', 0) + 1
        store.next_attempt(state, verdict['feedback'])
        return True
    store.decision(state, candidate, 'reject', verdict['feedback'] or 'Parked for human review.',
                   source='yolo')
    stage['feedback'] = verdict['feedback'] or 'The AI judge could not approve this — please review it yourself.'
    # A parked stage stays with the human until they act; automation must not
    # re-judge the same candidate on every restart or page reload.
    stage['auto_parked'] = True
    state['revision'] += 1
    store.save(state)
    return False

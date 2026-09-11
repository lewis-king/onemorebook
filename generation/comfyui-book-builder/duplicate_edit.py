"""One bounded duplicate-removal edit, chosen and checked for scene continuity."""
import hashlib
import json
from .story import object_schema as obj

VERSION = 2
TEXT = {'type': 'string', 'minLength': 1}
BOOL = {'type': 'boolean'}
ITEMS = {'type': 'array', 'items': TEXT, 'minItems': 1}
COPY = obj({'location': TEXT, 'gaze_and_interaction': TEXT,
            'effect_of_removing_this_copy': TEXT})
PLAN_SCHEMA = obj({
    'decision': {'enum': ['remove_duplicate', 'redraw', 'uncertain']},
    'character_id': TEXT, 'keep': COPY, 'remove': COPY,
    'reason': TEXT, 'preserve': ITEMS, 'fill': TEXT,
    'remaining_defects_after_removal': {'type': 'array', 'items': TEXT},
    'checks': obj({key: BOOL for key in (
        'only_one_extra_copy', 'copies_separately_identifiable',
        'kept_copy_fulfils_story_role', 'other_characters_keep_meaningful_gaze',
        'contacts_and_held_props_preserved', 'single_removal_sufficient')}),
})


def eligible(report, expected_ids):
    """Screen for one extra figure; the image planner must confirm duplication."""
    r = report.get('review', {})
    cast = {c['id']: c for c in r.get('characters', [])}
    if report.get('accepted') or r.get('uncertain') or set(cast) != set(expected_ids):
        return False
    if any(c.get('count') not in (1, 2) or c.get('identity_matches') is not True
           or c.get('appearance_matches') is not True or c.get('scale_matches') is not True
           for c in cast.values()):
        return False
    # Reviewers sometimes assign both copies to one id, sometimes call one extra.
    extra = max(sum(c['count']-1 for c in cast.values()), r.get('unexpected_character_count', 0))
    checks = r.get('checks', {})
    if extra != 1 or any(checks.get(k) is not True for k in (
            'style_matches', 'anatomy_sound', 'no_unwanted_text', 'reference_background_ok')):
        return False
    return not any(c.get('accepted') is False for key in (
        'object_scale_checks', 'visual_reference_checks') for c in report.get(key, []) or [])


def plan_edit(project, spec, source, report, generate=None):
    from .quality import expected_scene, json_model
    from .flux_prompt import scene_source
    generate = generate or json_model
    ids, scene, prose = expected_scene(project, spec)
    if not eligible(report, ids):
        return {'decision': 'redraw', 'reason': 'Not an isolated extra-character candidate.'}
    cast = [{k: c[k] for k in ('id', 'name', 'appearance')} for c in project['book']['characters'] if c['id'] in ids]
    context = scene_source(project, spec)
    context.pop('illustration_brief', None)
    prompt = (
        'Inspect this illustration to plan ONE removal of an accidentally duplicated character. '
        'Evaluate BOTH copies before deciding which to keep. For each, describe its position, '
        'actual head/body orientation, gaze, contact with props and interaction with the other characters. '
        'Imagine each copy removed: would a retained character stare or gesture toward empty space, '
        'lose a conversation partner, lose support or a held object, or contradict the story action? '
        'Keep the copy that best preserves the existing meaningful interaction and composition. '
        'Do not prefer the taller, larger, rightmost or more attractive copy by default. '
        'Gaze direction is evidence, not mind-reading: facing generally toward another figure does not '
        'prove a conversation. Trace the kept head/beak direction toward ALL surviving figures and the '
        'shared focal object, including smaller figures below it. A gaze still directed toward that '
        'surviving group or object is meaningful. Do not invent an exclusive relationship between copies. '
        'The prose controls named actor roles. An illustration-only pose flourish need not be enforced. '
        'Choose redraw if removal alone would require changing other characters, poses, scale or props; '
        'Inventory the story props as well: extra contents or an extra held object remain a separate defect '
        'even after removing a character. List concrete remaining defects after removal. Only choose '
        'remove_duplicate when that list is empty and the surviving scene fulfils the published prose. '
        'choose uncertain if the surviving interaction cannot be judged. '
        'Removing a figure naturally reveals background: filling that gap is the allowed edit, '
        'not a reason to rebalance or redraw the composition. Keep the other figures in place. '
        'A group may look toward a shared object; direct eye contact is not required. '
        'Use short spatial descriptions that uniquely identify each copy, including species/clothing. '
        'Preserve entries must describe the specific existing interactions and scenery to retain. '
        'Fill describes the scenery revealed by removal. Do not invent a new subject there.\n'
        + json.dumps({'cast': cast, 'page_prose': prose, 'scene': context,
                      'blind_scene_observation': report.get('inventory', {}).get('description', '')}, ensure_ascii=False))
    result = generate(project['config']['ollama_url'], project['render_settings']['review_model'],
                      prompt, PLAN_SCHEMA, images=[source], seed=spec['seed'] % (2**31),
                      think=False, num_predict=4000)
    import jsonschema
    jsonschema.validate(result, PLAN_SCHEMA)
    if (result['character_id'] not in ids or not all(result['checks'].values())
            or result['remaining_defects_after_removal']
            or result['keep']['location'].strip().casefold() == result['remove']['location'].strip().casefold()):
        result = {**result, 'decision': 'uncertain'}
    return result


def edit_prompt(plan, character):
    if plan['decision'] != 'remove_duplicate':
        raise ValueError('A confirmed continuity-preserving removal plan is required.')
    if character['id'] != plan['character_id']:
        raise ValueError('Removal target does not match the canonical character.')
    import re
    appearance = re.sub(r'\bHeight\s*:\s*[\d.]+\s*cm\.?', '', character['appearance'], flags=re.I).strip()
    subject = character['name']+' ('+appearance.rstrip('.')+')'
    return ('Edit Image 1. Remove the extra '+subject+'. Its location is: '+plan['remove']['location'].rstrip('.')+'. '
            'Keep the other copy of '+character['name']+' at '+plan['keep']['location'].rstrip('.')
            +' in its existing position, pose and size. '
            +' '.join(p.rstrip('.')+'.' for p in plan['preserve'])+' '
            'Fill the removed figure’s area with '+plan['fill'].rstrip('.')+'. '
            'Preserve all other characters, their faces, gaze directions, clothing and contact with objects. '
            'Keep the framing, lighting, painted style and all unaffected scenery unchanged.')


def prepare_edit(project, spec, source_attempt, attempt, report, generate=None):
    """Cache the decision against the exact pixels; never repeat a failed edit."""
    from .storage import review_directory, write_json
    directory = review_directory(project, spec)
    for p in directory.glob('attempt-*-strategy.json'):
        value = json.loads(p.read_text())
        number = int(p.name.split('-')[1])
        if (number < attempt and value.get('signature') == spec['signature']
                and value.get('strategy') == 'duplicate_removal'):
            return None
    source = directory/f'attempt-{source_attempt:02d}.png'
    if not source.exists():
        return None
    pixels = source.read_bytes()
    sha = hashlib.sha256(pixels).hexdigest()
    if report.get('signature') != spec['signature'] or report.get('png_sha256') != sha:
        return None
    path = directory/f'attempt-{attempt:02d}-duplicate-plan.json'
    identity = {'version': VERSION, 'signature': spec['signature'],
                'source_attempt': source_attempt, 'source_sha256': sha}
    if path.exists():
        record = json.loads(path.read_text())
        if any(record.get(k) != v for k, v in identity.items()):
            raise ValueError('Duplicate-removal source changed; preserve the old plan and use a new rendition.')
    else:
        plan = plan_edit(project, spec, pixels, report, generate)
        record = {**identity, 'plan': plan}
        if plan['decision'] == 'remove_duplicate':
            character = next(c for c in project['book']['characters'] if c['id'] == plan['character_id'])
            record['prompt'] = edit_prompt(plan, character)
        write_json(path, record)
    return record if record['plan']['decision'] == 'remove_duplicate' else None


PRESERVATION_CHECKS = ('correct_duplicate_removed', 'kept_character_unchanged',
    'other_characters_unchanged', 'gaze_and_interactions_preserved',
    'props_contacts_and_story_preserved', 'composition_and_style_preserved', 'background_repaired')
PRESERVATION_SCHEMA = obj({'checks': obj({k: BOOL for k in PRESERVATION_CHECKS}),
    'uncertain': BOOL, 'evidence': TEXT, 'issues': {'type': 'array', 'items': TEXT}})


def review_edit(project, source, edited, plan, generate=None):
    from .quality import json_model
    generate = generate or json_model
    prompt = (
        'Compare Image 1 (before) with Image 2 (after). Verify this single duplicate-removal edit. '
        'Count and identify actual visible figures before judging preservation. The specified copy must '
        'be removed and the chosen survivor must retain its identity, position, pose and approximate size. '
        'Check the other characters still look/gesture toward the same surviving partner or object, '
        'not toward the empty space of a removed partner. Preserve held objects, contacts, support and '
        'relative arrangement. Reject meaningful changes of gaze, action, scale, character design, '
        'story props or composition. Ignore tiny paint-texture differences. Report uncertainty honestly.\n'
        + json.dumps(plan, ensure_ascii=False))
    result = generate(project['config']['ollama_url'], project['render_settings']['review_model'],
                      prompt, PRESERVATION_SCHEMA, images=[source, edited], think=False, num_predict=4000)
    import jsonschema
    jsonschema.validate(result, PRESERVATION_SCHEMA)
    return {**result, 'accepted': not result['uncertain'] and all(result['checks'].values()) and not result['issues']}


def apply_edit_review(project, spec, attempt, png, report, generate=None):
    from .storage import review_directory
    directory = review_directory(project, spec)
    path = directory/f'attempt-{attempt:02d}-strategy.json'
    if not path.exists():
        return report
    strategy = json.loads(path.read_text())
    if strategy.get('strategy') != 'duplicate_removal':
        return report
    record = json.loads((directory/f'attempt-{attempt:02d}-duplicate-plan.json').read_text())
    source = (directory/f"attempt-{record['source_attempt']:02d}.png").read_bytes()
    if (record['signature'] != spec['signature'] or strategy.get('signature') != spec['signature']
            or hashlib.sha256(source).hexdigest() != record['source_sha256']):
        raise ValueError('Duplicate-removal preservation check has a changed source.')
    result = review_edit(project, source, png, record['plan'], generate)
    report['duplicate_edit_review'] = result
    if not result['accepted']:
        report['accepted'] = False
        report['review']['checks']['scene_matches'] = False
        report['review']['issues'].extend(result['issues'] or ['Removal edit did not preserve the existing scene interaction.'])
    return report

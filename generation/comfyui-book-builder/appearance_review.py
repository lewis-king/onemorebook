"""Evidence-based second look at a disputed, visible canonical appearance detail."""
import copy
import hashlib
import io
import json

from .story import object_schema


def eligible(report, expected_ids):
    return (report.get('uncertain') is False
            and report.get('unexpected_character_count') == 0
            and sorted(c['id'] for c in report['characters']) == sorted(expected_ids)
            and all(c['count'] == 1 and c['identity_matches'] is True for c in report['characters'])
            and any(c['appearance_matches'] is False for c in report['characters']))


def verified(audit, character_id, issue_count, retry_count):
    return (audit.get('character_id') == character_id
            and all(audit.get(k) is True for k in
                    ('same_character', 'required_appearance_present', 'disputed_features_visible'))
            and audit.get('uncertain') is False and audit.get('discrepancies') == []
            and all(str(audit.get(k, '')).strip() for k in ('candidate_observation', 'reference_observation'))
            and sorted(x['index'] for x in audit.get('issues', [])) == list(range(issue_count))
            and sorted(x['index'] for x in audit.get('retries', [])) == list(range(retry_count)))


def apply_verified(report, character, audit):
    """Only the appearance flag and explicitly disproven appearance objections change."""
    if not verified(audit, character['id'], len(report['issues']), len(report.get('retry_instructions', []))):
        return False
    cleared = {x['index'] for x in audit['issues']
               if x['this_character_appearance'] and x['contradicted_by_visible_evidence'] and x['evidence'].strip()}
    retries = {x['index'] for x in audit['retries']
               if x['this_character_appearance'] and x['contradicted_by_visible_evidence'] and x['evidence'].strip()}
    character['appearance_matches'] = True
    character['evidence'] += '\nFocused current-reference comparison: ' + audit['candidate_observation']
    report['issues'] = [v for i, v in enumerate(report['issues']) if i not in cleared]
    report['retry_instructions'] = [v for i, v in enumerate(report.get('retry_instructions', [])) if i not in retries]
    return True


def needs_scene_confirmation(report, records):
    return (any(r['changed'] for r in records) and not report['issues']
            and report['checks'].get('scene_matches') is False
            and all(v is True for k, v in report['checks'].items() if k != 'scene_matches')
            and report.get('uncertain') is False and report.get('unexpected_character_count') == 0
            and all(c['count'] == 1 and c['identity_matches'] and c['appearance_matches'] for c in report['characters']))


def confirmed_scene(audit):
    return (audit.get('story_event_visible') is True and audit.get('uncertain') is False
            and audit.get('essential_issues') == [] and audit.get('prior_issues') == []
            and bool(audit.get('observed_event', '').strip())
            and bool(audit.get('required_story_event', '').strip()))


def state_owned_characters(project, scene, spec):
    """Dynamic costume surfaces have dedicated before/after/attachment audits."""
    from .state_ledger import active_changes, inactive_additions
    ids = {c['character_id'] for c in [*active_changes(project, scene), *inactive_additions(project, scene)]}
    changes = {c['id']:c for c in project.get('art_plan', {}).get('ledger', {}).get('changes', [])}
    ids.update(changes[p['source_change_id']]['character_id'] for p in spec.get('props', [])
               if p['source_change_id'] in changes)
    return ids


def recheck(project, spec, png, report, detections, generate):
    from PIL import Image
    from .quality import expected_scene
    from .state_ledger import character_reference, scene_character_description
    from .storage import asset_path
    ids, _, _ = expected_scene(project, spec)
    if spec['kind'] != 'scene' or not eligible(report, ids):
        return []
    scene = project['book']['cover'] if spec['name'] == 'cover.png' else next(
        p for p in project['book']['pages'] if spec['name'] == f"pages/page-{p['page_number']:03d}.png")
    state_owned = state_owned_characters(project, scene, spec)
    records = []
    assessment = object_schema({'index': {'type': 'integer', 'minimum': 0},
        'this_character_appearance': {'type': 'boolean'},
        'contradicted_by_visible_evidence': {'type': 'boolean'}, 'evidence': {'type': 'string'}})
    for character in report['characters']:
        if character['appearance_matches'] is not False:
            continue
        cid = character['id']
        if cid in state_owned:
            records.append({'character_id':cid, 'before':copy.deepcopy(character), 'changed':False,
                            'audit':None, 'skipped':'Dynamic costume is owned by the dedicated state/attachment audits.'})
            continue
        detection = detections.get(cid)
        # A multi-actor image needs an independently assigned unique crop.
        if len(ids) > 1 and not detection:
            continue
        image = Image.open(io.BytesIO(png)).convert('RGB')
        bbox = [0, 0, image.width, image.height]
        if detection:
            x0, y0, x1, y1 = detection['bbox']
            pad = max(12, round(max(x1-x0, y1-y0) * .12))
            bbox = [max(0, int(x0)-pad), max(0, int(y0)-pad),
                    min(image.width, int(x1)+pad), min(image.height, int(y1)+pad)]
            image = image.crop(bbox)
        image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        encoded = io.BytesIO(); image.save(encoded, format='PNG'); candidate = encoded.getvalue()
        reference_name = character_reference(project, scene, cid)
        reference = asset_path(project, reference_name).read_bytes()
        canonical = next(c for c in project['book']['characters'] if c['id'] == cid)
        schema = object_schema({
            'character_id': {'type': 'string'}, 'candidate_observation': {'type': 'string'},
            'reference_observation': {'type': 'string'}, 'same_character': {'type': 'boolean'},
            'required_appearance_present': {'type': 'boolean'}, 'disputed_features_visible': {'type': 'boolean'},
            'discrepancies': {'type': 'array', 'items': {'type': 'string'}}, 'uncertain': {'type': 'boolean'},
            'issues': {'type': 'array', 'items': assessment, 'minItems': len(report['issues']), 'maxItems': len(report['issues'])},
            'retries': {'type': 'array', 'items': assessment, 'minItems': len(report.get('retry_instructions', [])),
                        'maxItems': len(report.get('retry_instructions', []))}})
        prompt = ('Compare the ONE named character in Image 1 (crop from the candidate scene) with Image 2 '
            '(the approved CURRENT character reference). First describe actual visible appearance in each image. '
            'A previous broad review made a disputed appearance claim; check it independently against these pixels. '
            'Do not assume either acceptance or rejection is correct. Only overturn a claim when the disputed '
            'feature is directly visible and matches the current reference and canonical design. Occlusion is '
            'not positive proof; set disputed_features_visible=false when the relevant region cannot be inspected. '
            'Check clothing, footwear, colours, species features and current story-state details. Do not broaden '
            'the design, substitute a similar garment, restore removed clothing, or overlook an actual mismatch. '
            'Ordinary painted shading and the appearance of straps in a turned foot are not missing footwear. '
            'Distinguish carried props from clothing by their actual attachment. For a removed scarf, '
            'inspect the visible neck and shoulders separately from fabric held by the hands across '
            'the belly or chest. A bare neck above hand-held fabric is not a worn scarf. A loop of '
            'fabric actually attached around the neck is worn, even if an end is also held. '
            'Keep emotion, pose, action, anatomy, counts and size outside this APPEARANCE-only reassessment. '
            'Classify every listed issue and correction exactly once by its supplied index. '
            'this_character_appearance is false for other characters and for expressions/actions/size/anatomy. '
            'contradicted_by_visible_evidence is true only when this character appearance claim is visibly false; '
            'give the specific observed evidence, not a generic reassurance.\n'
            + json.dumps({'character_id': cid, 'current_description': scene_character_description(project, scene, canonical, current=True),
                         'disputed_claim': character['evidence'],
                         'issues': list(enumerate(report['issues'])),
                         'retries': list(enumerate(report.get('retry_instructions', [])))}, ensure_ascii=False))
        before = copy.deepcopy(character)
        issues_before = list(report['issues'])
        retries_before = list(report.get('retry_instructions', []))
        audit = generate(project['config']['ollama_url'], project['render_settings']['review_model'],
                         prompt, schema, [candidate, reference])
        issue_count, retry_count = len(report['issues']), len(report.get('retry_instructions', []))
        changed = apply_verified(report, character, audit)
        records.append({'character_id': cid, 'before': before, 'audit': audit, 'changed': changed,
                        'issues_before': issues_before, 'retries_before': retries_before,
                        'source_sha256': hashlib.sha256(png).hexdigest(), 'crop_bbox': bbox,
                        'candidate_crop_sha256': hashlib.sha256(candidate).hexdigest(),
                        'reference': reference_name, 'reference_sha256': hashlib.sha256(reference).hexdigest(),
                        'issue_count': issue_count, 'retry_count': retry_count})
    return records

"""Choose an explicitly unapproved draft image, using the local queued reviewer."""
import hashlib
import json
from pathlib import Path
import re

VERSION = 3


def review_backend(project):
    """Use the same policy that produced the native per-attempt reviews."""
    if project.get('render_settings', {}).get('scene_quality_policy') == 'concise_v1':
        from . import quality_preview
        return quality_preview
    from . import quality
    return quality


def selection_inputs(project, spec):
    from .storage import asset_path, review_directory
    QA_VERSION = review_backend(project).QA_VERSION
    directory = review_directory(project, spec)
    candidates = []
    for path in sorted(directory.glob('attempt-*.png')):
        match = re.fullmatch(r'attempt-(\d+)\.png', path.name)
        if not match:
            continue
        metadata_path = path.with_name(path.stem+'-render.json')
        if not metadata_path.exists():
            continue
        metadata = json.loads(metadata_path.read_text())
        if metadata.get('signature') != spec['signature']:
            continue
        report_path = path.with_name(path.stem+'-review.json')
        report = json.loads(report_path.read_text()) if report_path.exists() else {}
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        matches = report.get('signature') == spec['signature'] and report.get('png_sha256') == sha
        candidates.append({'attempt': int(match.group(1)), 'path': str(path), 'sha256': sha,
                           'known_issues': report.get('review', {}).get('issues', []) if matches else []})
    references = []
    for name in dict.fromkeys(spec.get('references', [])):
        path = asset_path(project, name)
        if path.is_file():
            references.append({'name': name, 'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    guide = directory/'size-guide.png'
    if guide.is_file():
        references.append({'name': 'shared proportional cast guide', 'path': str(guide),
                           'sha256': hashlib.sha256(guide.read_bytes()).hexdigest()})
    return {'version': VERSION, 'review_policy': QA_VERSION, 'signature': spec['signature'], 'brief': spec.get('prompt', ''), 'story': project['story'],
            'production': project['production'], 'user_constraints': project['config'].get('story_idea', ''),
            'model': project['render_settings']['review_model'],
            'candidates': candidates, 'references': references}


def validate_comparison(result, attempts):
    ranking = result['ranking']
    observed = [o['attempt'] for o in result['observations']]
    if sorted(ranking) != sorted(attempts) or sorted(observed) != sorted(attempts):
        raise ValueError('Draft selection must compare and rank every supplied attempt exactly once.')
    if not result['reason'].strip():
        raise ValueError('Draft selection needs an explanation.')
    return ranking[0]


def select_review_candidate(project, spec, reviewer=None):
    from .quality import json_model, expected_scene
    backend = review_backend(project)
    review_art, QA_VERSION = backend.review_art, backend.QA_VERSION
    from .storage import review_directory, valid_asset, write_json
    from .story import digest, object_schema
    from .preview import atomic_view
    if valid_asset(project, spec):
        return None
    inputs = selection_inputs(project, spec)
    candidates = inputs['candidates']
    if not candidates:
        return None
    directory = review_directory(project, spec)
    key = digest(inputs)[:20]
    saved = directory/'draft-selections'/f'{key}.json'
    attempts = [c['attempt'] for c in candidates]
    if saved.exists():
        record = json.loads(saved.read_text())
        if record['inputs'] != inputs:
            raise ValueError('Draft selection inputs changed; preserve the previous selection.')
    else:
        # A multi-image ranking confused candidates and repeated stale failures
        # in calibration. Inspect ONE candidate at a time under the current QA
        # rules, then rank those recorded observations without guessing pixels.
        audits = []
        for candidate in candidates:
            audit_key = digest({**inputs, 'candidate': candidate})[:20]
            audit_path = directory/'draft-assessments'/f'{audit_key}.json'
            if audit_path.exists():
                audit = json.loads(audit_path.read_text())['audit']
            else:
                native_path = Path(candidate['path']).with_name(Path(candidate['path']).stem+'-review.json')
                native = json.loads(native_path.read_text()) if native_path.exists() else {}
                if (native.get('qa_version') == QA_VERSION and native.get('signature') == spec['signature']
                        and native.get('png_sha256') == candidate['sha256']):
                    audit = native
                else:
                    from .review_session import phase
                    with phase(project, directory/'draft-assessment-calls'/audit_key):
                        audit = review_art(project, spec, Path(candidate['path']).read_bytes(),
                                           generate=reviewer or json_model, attempt=candidate['attempt'])
                write_json(audit_path, {'inputs': inputs, 'candidate': candidate, 'audit': audit})
            audits.append({'attempt': candidate['attempt'], 'accepted_under_current_review': audit['accepted'],
                           'review': audit['review'], 'geometry': audit.get('geometry', {})})
        schema = object_schema({
            'observations': {'type': 'array', 'minItems': len(attempts), 'maxItems': len(attempts),
                'items': object_schema({'attempt': {'type': 'integer', 'enum': attempts},
                    **{k: {'type': 'string', 'minLength': 1} for k in ('cast_identity', 'story_action', 'appearance_and_scale', 'anatomy_and_style')},
                    'remaining_problems': {'type': 'array', 'items': {'type': 'string'}}})},
            'ranking': {'type': 'array', 'minItems': len(attempts), 'maxItems': len(attempts), 'uniqueItems': True,
                        'items': {'type': 'integer', 'enum': attempts}},
            'reason': {'type': 'string', 'minLength': 1}, 'uncertain': {'type': 'boolean'},
        })
        visible_ids, scene, prose = expected_scene(project, spec)
        from .scale import height_targets
        prompt = (
            "Choose the closest usable DRAFT illustration among failed attempts of one children's book asset. "
            "You are selecting a review copy for the author, NOT approving publication. Every candidate may have defects. "
            "Respect the asset's purpose: baseline portraits exclude temporary story props; style references contain no characters; cover/pages depict the specified story moment. "
            "Every candidate has been separately inspected against the canonical references and exact story moment. "
            "Rank the supplied CURRENT per-candidate observations. You are not seeing images in this final ranking call: "
            "do not invent visual observations, scale mismatches or failures beyond this evidence. "
            "Individual portraits are independently framed: their size within separate files is not the intended relative character height. "
            "Use canonical height_cm values and the shared proportional guide when supplied. "
            "Summarize each candidate's recorded evidence; then rank all attempts best to worst. "
            "Prioritize correct cast/count/identity and the actual story action, then costume/size continuity, then anatomy, clarity, style and unwanted lettering. "
            "A beautiful image of the wrong event or merged/missing character is worse than a slightly imperfect image telling the right story. "
            "Treat incidental illustration-direction details as flexible: carrying a stick does not require an added one-finger balancing flourish; "
            "a natural grip can tell the same story. Exact grip, pose or contact matters when it conveys the prose event, its causal mechanism or an explicit user requirement. "
            "Do not favor the last attempt. Old failure reports are deliberately excluded; they may use superseded rules. "
            "Mention the selected image's remaining defects and uncertainty honestly. Do not redefine any character or invent an event to excuse a mismatch.\n"
            + '\nAsset: '+spec['name']
            + '\nAsset purpose and story moment: '+json.dumps({'kind': spec['kind'], 'visible_character_ids': visible_ids, 'scene': scene, 'prose': prose})
            + '\nExact production brief (includes any planned temporary state): '+spec.get('prompt', '')
            + '\nCanonical cast: '+json.dumps(project['production']['characters'])
            + '\nCode-computed whole-body height ratios: '+json.dumps(height_targets(project['production']['characters']))
            + '\nExplicit user constraints: '+inputs['user_constraints']
            + '\nCurrent independently recorded candidate assessments: '+json.dumps(audits))
        result = (reviewer or json_model)(project['config']['ollama_url'], inputs['model'], prompt, schema,
                                         seed=spec['seed'], num_ctx=32768)
        # An old failed candidate can pass corrected QA. Keep it ahead of known
        # failures in this DRAFT ranking; publication still needs native approval.
        now_passed = {a['attempt'] for a in audits if a['accepted_under_current_review']}
        raw_ranking = list(result['ranking'])
        result['ranking'] = sorted(result['ranking'], key=lambda n: n not in now_passed)
        if result['ranking'] != raw_ranking:
            result['reason'] = (f"Attempt {result['ranking'][0]} passes the current independent checks; "
                                "it takes priority over candidates with recorded defects. "
                                "This remains a draft selection pending native publication review.")
        chosen = validate_comparison(result, attempts)
        record = {'status': 'unapproved_draft_selection', 'inputs': inputs,
                  'selected_attempt': chosen, 'comparison': result, 'model_ranking': raw_ranking,
                  'candidate_assessments': audits, 'prompt': prompt}
        write_json(saved, record)
    if record['selected_attempt'] != validate_comparison(record['comparison'], attempts):
        raise ValueError('Saved draft selection differs from its ranking.')
    atomic_view(directory/'draft-selection.json', (json.dumps(record, ensure_ascii=False, indent=2)+'\n').encode())
    return record


def try_select_review_candidate(project, spec):
    import logging
    try:
        return select_review_candidate(project, spec)
    except Exception:
        # A user cancellation must stop the workflow, not start another page.
        import comfy.model_management as mm
        mm.throw_exception_if_processing_interrupted()
        logging.exception('Book v2: comparison unavailable for %s; review draft retains the latest candidate and all alternatives.', spec['name'])
        return None


def selected_draft_candidate(project, spec):
    """Read a selection only while its exact images, references and story match."""
    from .storage import review_directory
    path = review_directory(project, spec)/'draft-selection.json'
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text())
        inputs = selection_inputs(project, spec)
        if record.get('status') != 'unapproved_draft_selection' or record['inputs'] != inputs:
            return None
        chosen = validate_comparison(record['comparison'], [c['attempt'] for c in inputs['candidates']])
        if record['selected_attempt'] != chosen:
            return None
        candidate = next(c for c in inputs['candidates'] if c['attempt'] == chosen)
        observation = next(o for o in record['comparison']['observations'] if o['attempt'] == chosen)
        return {**candidate, 'reason': record['comparison']['reason'],
                'uncertain': record['comparison']['uncertain'], 'remaining_problems': observation['remaining_problems']}
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        return None

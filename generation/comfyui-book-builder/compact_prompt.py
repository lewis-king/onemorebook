"""Compile a cached, locally checked rendering prompt; public story stays immutable."""
import json
import re

VERSION = 4


def compile_prompt(project, spec, source, reference_count, generate=None):
    from .quality import json_model
    from .scale import guide_cast, cast_height
    from .storage import checked_root, write_json
    from .story import digest, object_schema as obj
    import jsonschema
    generate = generate or json_model
    cast = guide_cast(project, spec)
    if not cast and project.get('render_settings',{}).get('qwen_scene_recipe'):
        from .quality import expected_scene
        ids=expected_scene(project,spec)[0]
        cast=[next(c for c in project['book']['characters'] if c['id']==cid) for cid in ids]
    if not cast or (len(cast)>1 and spec.get('reference_layout') != 'cast_guide'):
        raise ValueError('Compact prompt requires the shared cast guide in Image 1.')
    ids = [c['id'] for c in cast]
    model = project['render_settings']['review_model']
    context = {'source_prompt': source, 'reference_count': reference_count,
               'cast_left_to_right': [{'id': c['id'], 'name': c['name'], 'height_cm': cast_height(c)} for c in cast]}
    key = digest([VERSION, context, model])
    root = checked_root(project) / 'prompt-compilation' / key[:20]
    approved = root / 'approved.json'
    if approved.exists():
        saved = json.loads(approved.read_text())
        if saved.get('source_hash') != key or digest(saved.get('prompt')) != saved.get('prompt_hash'):
            raise ValueError('Saved compact prompt provenance mismatch.')
        return saved['prompt']
    text = {'type': 'string', 'minLength': 1}
    schema = obj({'setting': text, 'actors': obj({cid: obj({'identity': text, 'action': text,
                  'contact_geometry': {'type':'string','maxLength':350}}) for cid in ids}),
                  'objects_and_relationships': text, 'object_counts': text, 'style': text,
                  'other_reference_roles': {'type': 'string'},
                  'uncertain': {'type': 'boolean'}, 'issues': {'type': 'array', 'items': text}})
    checks = ('identities_and_current_clothes', 'same_actor_actions', 'props_and_states',
              'contact_containment_and_scale', 'reference_roles', 'style_and_setting', 'no_added_story_content')
    audit_schema = obj({'checks': obj({k: {'type': 'boolean'} for k in checks}),
                        'uncertain': {'type': 'boolean'}, 'issues': {'type': 'array', 'items': text}, 'evidence': text})
    request = (
        'Reformat this approved illustration brief into concise visual prose for a reference-conditioned image model. '
        'Do not invent or rewrite the story. Each actor gets ONE identity and ONE action: identity names its species, '
        'visible distinguishing body traits and CURRENT clothes; action describes that SAME body performing its '
        'assigned pose and interaction, including its target. This binds identity and action together instead of '
        'describing a standing cast and a second acting cast. Names remain supplied by the caller. Use the names '
        'and distinguishing species/clothing when referring to another participant. One moment only. '
        'For contact_geometry, turn the assigned interaction into visible physical geometry: manipulated '
        'object orientation, exact receiving object/surface, and continuous material path when applicable. '
        'For example, pouring requires the vessel opening tilted toward its named receiving surface, with '
        'the liquid stream landing on that surface. This is clarification of the existing verb, not permission '
        'to invent props or change the event. A watcher needs an empty contact_geometry. '
        'object_counts must state the number of each central manipulated/shared object grounded in the '
        'source, preserving vague/plural quantities when no exact count is established. A single object '
        'mentioned in several clauses is still ONE physical object. State shared ownership explicitly. '
        'Avoid restating a manipulated object as a separate still-life item: subsequent mentions mean '
        'the SAME object in the actor action, not another copy. '
        'Keep all required props, states, contact, containment, placement, appearance and scale constraints. '
        'Current changes override baseline clothes. A detached item stays detached and is described as an object, '
        'not a worn accessory. Preserve conditional visibility; do not make optional objects mandatory. '
        'Do not invent a support/table or additional props to simplify the action. Preserve each additional '
        'Image N role exactly; other_reference_roles is empty when there is only Image 1. '
        'Use plain natural sentences, not embedded JSON, repeated instructions or reference-card poses. '
        'Aim for 250–450 words; correctness takes priority over brevity. The caller adds count, cast-guide '
        'mapping, physical heights and no-lettering instructions. If a required detail cannot be reconciled, '
        'report uncertainty rather than silently losing it.\n' + json.dumps(context, ensure_ascii=False))
    for attempt in (1, 2):
        write_json(root / f'request-{attempt}.json', {'prompt': request, 'schema': schema, 'model': model})
        path = root / f'draft-{attempt}.json'
        draft = json.loads(path.read_text()) if path.exists() else generate(
            project['config']['ollama_url'], model, request, schema, seed=0)
        jsonschema.validate(draft, schema)
        write_json(path, draft)
        parts = [f"Paint one children's picture-book scene with exactly {len(cast)} individual characters. "
                 'Re-pose the individuals in Image 1: each becomes one body in this scene. Use their canonical '
                 'identities, current clothes and relative physical sizes. Replace the reference lineup and '
                 'portrait backgrounds with the scene.\n' + draft['setting']]
        for index, c in enumerate(cast, 1):
            actor = draft['actors'][c['id']]
            parts.append(f"{c['name']}, individual {index} from the left in Image 1: {actor['identity']} "
                         f"This same individual {actor['action']} {actor['contact_geometry']}")
        parts += [draft['object_counts'], draft['objects_and_relationships'],
                  'Preserve standing physical heights through changes of pose and camera angle: ' +
                  '; '.join(f"{c['name']} {cast_height(c):g} cm" for c in cast) + '.',
                  draft['other_reference_roles'], draft['style'],
                  'Each individual appears once with separate natural anatomy. One full illustration without lettering or portrait panels.']
        prompt = '\n\n'.join(p for p in parts if p)
        mentioned = {int(n) for n in re.findall(r'\bImage\s+(\d+)\b', prompt, re.I)}
        structural_issues = []
        if mentioned != set(range(1, reference_count + 1)):
            structural_issues.append('Missing, out-of-range or renumbered image-reference roles.')
        audit_path = root / f'review-{attempt}.json'
        if structural_issues or draft['uncertain'] or draft['issues']:
            audit = {'checks': {k: False for k in checks}, 'uncertain': draft['uncertain'],
                     'issues': structural_issues + draft['issues'], 'evidence': 'Structural compilation check failed.'}
        else:
            audit = json.loads(audit_path.read_text()) if audit_path.exists() else generate(
                project['config']['ollama_url'], model,
                'Check semantic preservation of this reformatted image prompt against its source. Reject '
                'omitted or swapped actors/actions, current clothing errors, added props/supports, lost '
                'contact/containment, changed prop designs/scales, or changed image-reference roles. '
                'Read synonyms normally. Removing repetition and implementation boilerplate is allowed. '
                'Every story-relevant constraint must survive; conditional visibility must stay conditional. '
                'Do not demand exact wording or add requirements absent from the source.\n' +
                json.dumps({'source': context, 'candidate': prompt}, ensure_ascii=False), audit_schema, seed=0)
        jsonschema.validate(audit, audit_schema)
        write_json(audit_path, audit)
        if not audit['uncertain'] and not audit['issues'] and all(audit['checks'].values()):
            write_json(approved, {'source_hash': key, 'prompt_hash': digest(prompt), 'prompt': prompt,
                                  'model': model, 'review': audit})
            return prompt
        request += '\nCorrect the previous draft without altering source meaning:\n' + json.dumps({'draft': draft, 'review': audit})
    # The original brief remains usable. Never treat failed compilation as an
    # image approval or force the failed rewrite into the sampler.
    write_json(root / 'fallback.json', {'source_hash': key, 'reason': 'No compact draft passed semantic validation.'})
    return source

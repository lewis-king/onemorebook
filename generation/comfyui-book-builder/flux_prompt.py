"""Compile a cached, locally checked rendering prompt; public story stays immutable."""
import json
import re

VERSION = 15


def scene_source(project, spec):
    """Supply authoritative scene data once; never feed accumulated retry prose back as truth."""
    from .quality import expected_scene
    from .scene_contract import scene_render_details, scene_context
    from .visual_library import entries
    from .story import scene_style_text
    from .state_ledger import scene_character_description
    ids = expected_scene(project, spec)[0]
    scene = (project['book']['cover'] if spec['name'] == 'cover.png' else next(
        p for p in project['book']['pages'] if spec['name'] == f"pages/page-{p['page_number']:03d}.png"))
    objects, checks = scene_render_details(project, scene)
    # Reference routing can resolve a synonym that the lexical contract binder
    # cannot ("rock crack" versus "Rock Crevice"). Include the routed design.
    library = entries(project, spec) if spec.get('visual_references') else []
    designs = {o['id']: {k:o[k] for k in ('id','name','appearance')} for o in objects}
    for e in library:
        designs[e['id']] = {k:e[k] for k in ('id','name','appearance')}
    return {'moment': scene_context(project, spec['name']),
            'page_prose': scene.get('text', ''), 'illustration_brief': scene['scene_prompt'],
            'cast': [{'id':c['id'], 'name':c['name'], 'appearance':scene_character_description(project,scene,c)}
                     for c in project['book']['characters'] if c['id'] in ids],
            'canonical_designs': list(designs.values()),
            'rules_to_evaluate_at_this_moment': [{'requirement':c['requirement'], 'visibility':c['visibility']}
                                                for c in checks],
            'style': scene_style_text(project)}


def compile_prompt(project, spec, source, reference_count, generate=None, reference_roles=None, feedback=''):
    from .quality import json_model
    from .scale import guide_cast, cast_height
    from .storage import checked_root, write_json
    from .story import digest, object_schema as obj
    import jsonschema
    generate = generate or json_model
    cast = guide_cast(project, spec)
    structured = project.get('render_settings',{}).get('compact_prompt_policy',0) >= 7
    positive = project.get('render_settings',{}).get('compact_prompt_policy',0) >= 11
    if not cast:
        from .quality import expected_scene
        ids=expected_scene(project,spec)[0]
        cast=[next(c for c in project['book']['characters'] if c['id']==cid) for cid in ids]
    if (not cast and not structured) or (len(cast)>1 and spec.get('reference_layout') != 'cast_guide'):
        raise ValueError('Compact prompt requires the shared cast guide in Image 1.')
    ids = [c['id'] for c in cast]
    from .quality import expected_scene
    from .state_ledger import active_changes
    scene = (project['book']['cover'] if spec['name']=='cover.png' else next(
        p for p in project['book']['pages'] if spec['name']==f"pages/page-{p['page_number']:03d}.png"))
    current_states={c['id']:[{'state':change['after_state'],'surface':change['surface']}
                           for change in active_changes(project,scene,c['id'])] for c in cast}
    model = project['render_settings']['review_model']
    if reference_roles is not None:
        expected = set(range(2, reference_count + 1))
        if set(reference_roles) != expected or not all(reference_roles.values()):
            raise ValueError('Caller must provide exactly the additional numbered reference roles.')
    context = {'source_prompt': scene_source(project,spec) if structured else source,
               'retry_observations': feedback if structured else '', 'reference_count': reference_count,
               'fixed_reference_roles': reference_roles,
               'fixed_current_states': current_states,
               'cast_left_to_right': [{'id': c['id'], 'name': c['name'], 'height_cm': cast_height(c)} for c in cast]}
    from .scene_staging import SPECIAL_VIEW as special_view, continuous_view, normalize
    prose = context['source_prompt'].get('page_prose', '') if structured else ''
    require_continuous_view = positive and continuous_view(project, prose)
    context['continuous_scene_view'] = require_continuous_view
    original_brief = None
    if require_continuous_view and structured:
        # Translate only an illustration-only camera directive. Keep every
        # actor/action/prop clause; the public brief remains byte-for-byte intact.
        brief = context['source_prompt'].get('illustration_brief', '')
        ordinary_view = normalize(project, prose, brief)
        if ordinary_view != brief:
            original_brief = brief
            context['source_prompt']['illustration_brief'] = ordinary_view
        context['retry_observations'] = normalize(project, prose, context['retry_observations'])
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
                  'contact_geometry': {'type':'string','maxLength':350},
                  **({'current_surface': {'type':'string','maxLength':350}} if positive else {})}) for cid in ids}),
                  'objects_and_relationships': text, 'object_counts': text, 'style': text,
                  **({'other_reference_roles': {'type': 'string'}} if reference_roles is None else {}),
                  'uncertain': {'type': 'boolean'}, 'issues': {'type': 'array', 'items': text}})
    checks = ('identities_and_current_clothes', 'same_actor_actions', 'props_and_states',
              'contact_containment_and_scale', 'reference_roles', 'style_and_setting', 'no_added_story_content')
    audit_schema = obj({'checks': obj({k: {'type': 'boolean'} for k in checks}),
                        'uncertain': {'type': 'boolean'}, 'issues': {'type': 'array', 'items': text}, 'evidence': text})
    hierarchy = (
        'Resolve ONE visible instant on the specified page. Page prose controls events and named actors; '
        'canonical designs control the recurring objects and location. The illustration brief supplies staging '
        'only where compatible with those. Never change an upright object into a ground opening, for example. '
        'Evaluate conditional timeline rules at this page: describe ONLY the current state, never future/earlier '
        'alternatives or page ranges. Reference designs define appearance, not a demand to display hidden objects. '
        'Established contents persist until removed in the story: a visibly open cavity/container must show '
        'its contents. Omit them only when that interior is genuinely cropped or occluded. An empty canonical '
        'prop reference defines its shape, not an empty state for the current scene. '
        'Retry observations can clarify a defect but cannot add cast, props or change the story. '
        'Use one continuous scene view appropriate to the story environment. When only the illustration '
        'brief asks for a cutaway, split-view or diagram, depict the same action or its immediate visible '
        'result in the established environment. Preserve underwater settings when the story is underwater. '
        'Keep the characters in their established environment. '
        'Use one body per actor. Describe the principal action once; '
        'combine watchers into the same moment. Keep identity phrases short: species plus distinguishing clothes. '
        'References carry the fine visual detail. If prose and canonical design truly cannot coexist, report uncertainty. '
        if structured else '')
    request = hierarchy + (
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
        'Image N role exactly. When fixed_reference_roles is supplied, the caller attaches those roles verbatim; '
        'do not repeat their mapping in the scene prose. Otherwise other_reference_roles lists the extra images '
        'and is empty only when there is just Image 1. '
        'Use plain natural sentences, not embedded JSON, repeated instructions or reference-card poses. '
        'Aim for 180–300 words; correctness takes priority over brevity. The caller adds count, cast-guide '
        'mapping, physical heights and no-lettering instructions. If a required detail cannot be reconciled, '
        'report uncertainty rather than silently losing it. The caller also attaches fixed_current_states '
        'beside each actor; do not contradict them.\n' + json.dumps(context, ensure_ascii=False))
    if structured:
        request = (hierarchy +
            'Return concise visual prose in the schema. For each actor, identity is species plus distinguishing '
            'CURRENT clothes/body traits; action describes that same body performing its prose-grounded role. '
            'contact_geometry clarifies a necessary action contact or material path; leave it empty for watchers. '
            'Name and appearance must identify the same actor, including when another actor refers to them. '
            'A detached garment is an object, not a worn accessory. '
            'object_counts describes central objects once, retaining vague quantities when unspecified. '
            'objects_and_relationships adds necessary placement, containment, attachment and current state, '
            'without repeating actor actions or adding a second copy of an object. Keep conditional visibility '
            'conditional. Preserve required contact and scale; never invent a support or prop to simplify a pose. '
            'The caller supplies image-role mapping, cast count, heights and current states; do not repeat them. '
            'setting and style can each be one short sentence. Aim for 100–180 words across your fields. '
            'Correctness takes priority over brevity. Report irreconcilable requirements as uncertainty.\n' +
            json.dumps(context,ensure_ascii=False))
    if positive:
        request += ('\nDescribe the desired visible result in affirmative natural language. Replace negative '
                    'phrases with grounded visible surfaces or states. current_surface states the visible '
                    'result of fixed_current_states on its specified surface, using the approved current '
                    'appearance; keep it empty only when that actor has no current state changes. For example, '
                    'a removed scarf exposes the established neck surface; do not invent its colour or anatomy. '
                    'Keep the detached scarf at its required prop location. Express comparisons and metaphors '
                    'as the actual subject state: cheeks puffed like balloons means puffed cheeks, not balloons. '
                    'Avoid quality-tag lists, quoted dialogue, text-rendering requests, and camera jargon '
                    'irrelevant to the chosen illustration style. Keep style, palette and lighting coherent.')
    for attempt in (1, 2):
        reasoning = {'think': True, 'num_predict': 8192} if positive and attempt > 1 else {}
        write_json(root / f'request-{attempt}.json', {'prompt': request, 'schema': schema, 'model': model,
                   'original_illustration_brief': original_brief, **reasoning})
        path = root / f'draft-{attempt}.json'
        draft = json.loads(path.read_text()) if path.exists() else generate(
            project['config']['ollama_url'], model, request, schema, seed=0, **reasoning)
        jsonschema.validate(draft, schema)
        write_json(path, draft)
        parts = [f"Create one picture-book scene with exactly {len(cast)} characters from Image 1, "
                 'each appearing once. Preserve their identities and re-pose them for the scene, '
                 'replacing the portrait background.\n' + draft['setting']]
        if not cast:
            parts=['Create one unpopulated picture-book scene. Image 1 supplies style and palette.\n'+draft['setting']]
        if positive and cast:
            parts=[f"One picture-book illustration with exactly {len(cast)} characters, each appearing once. "
                   + draft['style']]
        for index, c in enumerate(cast, 1):
            actor = draft['actors'][c['id']]
            identity = re.sub(r'^'+re.escape(c['name'])+r'\b[, :]*', '', actor['identity'], flags=re.I).strip()
            state='; '.join(f"{s['state']} on {s['surface']}" for s in current_states[c['id']])
            state=(f'Current appearance: {state}. ' if state else '')
            if positive:
                state = ('Current appearance: '+actor['current_surface'].strip()+'. '
                         if actor['current_surface'].strip() else '')
            parts.append(f"{c['name']} ({identity}; figure {index} from left in Image 1): "
                         + (f"{actor['action']} {actor['contact_geometry']} {state}" if positive else
                            f"{state}{actor['action']} {actor['contact_geometry']}"))
        if positive and cast:
            parts.append(draft['setting'])
        parts += [draft['object_counts'], draft['objects_and_relationships'],
                  ('Preserve standing physical heights through changes of pose and camera angle: ' +
                  '; '.join(f"{c['name']} {cast_height(c):g} cm" for c in cast) + '.') if cast else '',
                  (draft['other_reference_roles'] if reference_roles is None else
                   ' '.join(f'Image {n}: {role}' for n, role in sorted(reference_roles.items()))),
                  '' if positive and cast else draft['style'],
                  ('Preserve the referenced designs in fresh expressive poses within this continuous scene. '
                   'Unmarked artwork surfaces.' if positive else 'Natural separate bodies; no lettering or portrait panels.')]
        prompt = '\n\n'.join(p for p in parts if p)
        mentioned = {int(n) for n in re.findall(r'\bImage\s+(\d+)\b', prompt, re.I)}
        structural_issues = []
        if require_continuous_view and re.search(special_view, prompt, re.I):
            structural_issues.append('Use a continuous external view of the objects in their established '
                                     'environment. Illustration-only sectional staging must be expressed '
                                     'as the same action or its visible immediate result.')
        if positive:
            for cid in ids:
                if current_states[cid] and not draft['actors'][cid]['current_surface'].strip():
                    structural_issues.append(f'Missing visible current-state result for {cid}.')
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
                'Do not demand exact wording or add requirements absent from the source.\n' + hierarchy +
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
    if structured:
        from .scene_staging import ScenePromptError
        raise ScenePromptError('Scene prompt could not reconcile prose, current state and canonical designs; '
                         'saved compilation reports for diagnosis before spending image retries.')
    return source

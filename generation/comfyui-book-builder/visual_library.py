"""Private canonical pictures for recurring props and locations, never app fields."""
import json
from pathlib import Path

from .story import digest, object_schema as obj

VERSION = 3
TEXT = {'type': 'string', 'minLength': 1}
IDENTIFIER = {'type': 'string', 'pattern': '^[a-z][a-z0-9_]{0,31}$'}


def story_scenes(project):
    return [('cover.png', project['book']['cover'])] + [
        (f"pages/page-{p['page_number']:03d}.png", p) for p in project['book']['pages']]


def request(project):
    scenes = dict(story_scenes(project))
    object_ids = [o['id'] for o in project.get('scene_contract', {}).get('objects', [])]
    character_ids = [c['id'] for c in project['book']['characters']]
    names = {'type': 'array', 'uniqueItems': True, 'items': {'type': 'string', 'enum': list(scenes)}}
    schema = obj({'entries': {'type': 'array', 'maxItems': 16, 'items': obj({
        'id': IDENTIFIER, 'kind': {'type': 'string', 'enum': ['prop', 'location']},
        'name': TEXT, 'appearance': TEXT,
        'source_object_id': {'type': 'string', 'enum': ['', *object_ids]},
        'source_character_id': {'type': 'string', 'enum': ['', *character_ids]},
        'source_item': {'type': 'string'},
        'scenes': names, 'required_scenes': names,
        'evidence': TEXT,
    })}, 'uncertain': {'type': 'boolean'}, 'issues': {'type': 'array', 'items': TEXT}})
    prompt = ("Plan a PRIVATE reusable visual-reference library for this complete picture book. "
        "The public prose and illustration briefs are immutable. Identify salient props/landmarks "
        "and recurring locations whose design must stay the same on at least TWO distinct story pages. "
        "Include recurring objects even when a later page names only a PART (a crown still belongs to "
        "the previously established crowned statue), uses a pronoun, or changes the object's state. "
        "Use the existing prop catalogue's IDs and designs where available; source_object_id names "
        "that entry. A location has source_object_id empty. Do not include living cast as objects. "
        "Ignore one-off tools and incidental flowers, clouds or decoration. A distinct repeated "
        "building, room, garden or landscape may need one location reference. Do not collapse "
        "different places, or demand the identical camera view on every visit.\n"
        "appearance describes permanent material, colours, silhouette, construction and a few "
        "salient distinguishing features. Resolve a vague statue into ONE coherent figure/crown/base "
        "design consistent with the source; preserve that design through different views. Never add "
        "new plot events. Omit transient contents, ownership, honey/paint, damage, position, lighting "
        "and current attachments: the story-state ledger supplies those separately. Location design "
        "describes fixed architecture/surfaces/layout, with NO cast or movable plot props baked in.\n"
        "scenes lists only frames where this reference is relevant and its subject may be visible; "
        "required_scenes is the subset whose chosen story event requires that subject on screen. "
        "A close-up can crop a location away, so its reference is normally optional. An absent/popped "
        "object must NOT be routed into that frame. Background continuity does not invent a second "
        "moment, extra actor or story prop. Ongoing containment must preserve both container and "
        "contents when the container is visible.\n"
        "For a prop originally belonging to a character's costume (e.g. their removed scarf), set "
        "source_character_id and source_item so its canonical portrait anchors that SAME garment. "
        "Do not invent a second garment design or freeze its worn pose; it can naturally unfold. "
        "Otherwise both source fields are empty. Keep entries concise. No issues/uncertainty when "
        "clear. An empty library is valid for a story with no recurring visual subjects.\n" + json.dumps({
            'story': project['story'], 'characters': project['book']['characters'],
            'scenes': scenes, 'prop_catalogue': project.get('scene_contract', {}).get('objects', []),
            'persistent_facts': project.get('scene_contract', {}).get('persistent_facts', []),
            'costume_ledger': project.get('art_plan', {}).get('ledger', {})}, ensure_ascii=False))
    return prompt, schema


def validate(project, value):
    import jsonschema
    jsonschema.validate(value, request(project)[1])
    ids, source_ids = set(), set()
    for entry in value['entries']:
        if entry['id'] in ids:
            raise ValueError('Duplicate visual reference ID.')
        ids.add(entry['id'])
        if not set(entry['required_scenes']) <= set(entry['scenes']):
            raise ValueError('Required reference frames must be routed frames.')
        if len([s for s in entry['scenes'] if s.startswith('pages/')]) < 2:
            raise ValueError('A reusable reference requires two story pages, not merely a cover.')
        if entry['source_object_id']:
            if entry['source_object_id'] in source_ids:
                raise ValueError('One source prop cannot acquire multiple canonical designs.')
            source_ids.add(entry['source_object_id'])
        if bool(entry['source_character_id']) != bool(entry['source_item']):
            raise ValueError('Garment reference requires both a source character and item.')
        if entry['kind'] == 'location' and (entry['source_object_id'] or entry['source_character_id']):
            raise ValueError('Location reference cannot borrow an object or character identity.')
    for name, _ in story_scenes(project):
        routed = [e for e in value['entries'] if name in e['scenes']]
        if sum(e['kind'] == 'prop' for e in routed) > 6 or sum(e['kind'] == 'location' for e in routed) > 1:
            raise ValueError('A frame supports six prop references and one coherent location.')


def checked_model_call(root, tag, generate, url, model, prompt, schema, *, seed=0):
    """Persist and retry malformed local model replies without accepting them."""
    import jsonschema
    from .storage import write_json
    key = digest([prompt, schema, model, seed])
    directory = root / (tag + '-responses') / key[:16]
    feedback = ''
    for retry in range(3):
        prefix = directory / f'attempt-{retry+1:02d}'
        result_path = prefix.with_suffix('.json')
        error_path = prefix.with_name(prefix.name + '-error.json')
        request_path = prefix.with_name(prefix.name + '-request.json')
        request = {'model': model, 'prompt': prompt + feedback, 'schema': schema, 'seed': seed + retry}
        if request_path.exists():
            if json.loads(request_path.read_text()) != request:
                raise ValueError('Saved visual planning request changed; preserve its response history.')
        else:
            write_json(request_path, request)
        if error_path.exists():
            failure = json.loads(error_path.read_text())
        else:
            try:
                value = json.loads(result_path.read_text()) if result_path.exists() else generate(
                    url, model, request['prompt'], schema, seed=request['seed'])
                # Validate again here: injected clients and restored replies must
                # obey the same contract as quality.json_model's normal transport.
                jsonschema.validate(value, schema)
                write_json(result_path, value)
                return value
            except (ValueError, jsonschema.ValidationError) as exc:
                failure = {'error': str(exc), 'invalid_fragment': getattr(exc, 'instance', None)}
                write_json(error_path, failure)
        feedback = ('\nYour previous response was structurally invalid. Return a corrected complete '
                    'response for the SAME source and schema. Do not invent evidence to fill a required '
                    'list. Repeating one page does not make two distinct pages. A subject visible on '
                    'only one story page is not a missing recurring subject; omit that unsupported '
                    'claim and assess completeness from the actual recurring subjects.\n' + json.dumps(failure))
    raise ValueError('Local visual planning response failed validation after three saved attempts: ' + str(directory))


def audit_request(project, value):
    prompt, _ = request(project)
    audit_schema = obj({'faithful': {'type': 'boolean'},
        'routing_correct': {'type': 'boolean'}, 'uncertain': {'type': 'boolean'},
        'missing_subject_observations': {'type': 'array', 'items': obj({'name': TEXT,
            'visible_scenes': {'type': 'array', 'minItems': 1,
                'items': {'type': 'string', 'enum': [n for n,_ in story_scenes(project) if n.startswith('pages/')]}},
            'evidence': TEXT})},
        'evidence': TEXT, 'design_or_routing_issues': {'type': 'array', 'items': TEXT}})
    semantic_entries = [{'name': e['name'], 'kind': e['kind'], 'appearance': e['appearance'],
        'frames_where_visible_or_relevant': e['scenes'], 'frames_requiring_visibility': e['required_scenes'],
        'garment_origin': ({'character': e['source_character_id'], 'item': e['source_item']}
                          if e['source_character_id'] else None)} for e in value['entries']]
    audit_prompt = ('Independently check this proposed VISUAL reference library against the complete '
        'story, illustration moments, prop catalogue and costume ledger below. Find missing recurring '
        'plot objects/landmarks or locations, incompatible designs, duplicated source objects, wrong '
        'scene routes, missing part-to-whole links, and transient story states incorrectly baked '
        'into permanent design. Do not force an optional background into a close-up. Do not require '
        'one-off tools or incidental flowers to get references. For a garment, its specified source '
        'character/item must be correct. Harmless unspecified design choices are permitted once; '
        'new events or contradictory appearance are not. A popped/absent bubble must not be routed '
        'to the ending. Meaningful recurring subjects need references even if briefly unnamed. '
        'A tool visible on ONE page is outside this library, even if it solves the problem. '
        'Report potentially missing visual subjects as observations. For EACH '
        'observation list only the story-page scenes where the SAME '
        'subject is actually visible; one page is allowed and must not be repeated to imply recurrence. A generic kit is not every particular tool in it. '
        'A hedge already described inside the garden location does not need a duplicate '
        'reference. A CLEAN canonical garment used on later honey-covered pages is CORRECT: '
        'the base design and later story state are deliberately separate. Only putting honey '
        'or damage into permanent appearance would bake in a transient state. The caller counts distinct pages and decides completeness; '
        'do not decide completeness or add missing-subject complaints to design_or_routing_issues. Structural schema/ID validity '
        'has already been checked by code. A newly identified recurring subject need not have '
        'an ID in the older prop catalogue: its provided design establishes the reference. '
        'faithful checks the supplied designs; routing_correct checks their scene assignment. Neither flags an omitted subject. Put incompatible designs or actual routing problems in design_or_routing_issues. Assess the actual supplied subjects and designs, not internal metadata. A listed '
        'cleaning kit with a design and routes is present, not missing.\n'
        + json.dumps({'source': json.loads(prompt.split('\n')[-1]), 'candidate_visible_designs': semantic_entries}, ensure_ascii=False))
    return audit_prompt, audit_schema

def classify_observations(raw):
    """A single page mentioned twice still cannot establish recurrence."""
    recurring, one_page = [], []
    for observation in raw['missing_subject_observations']:
        scenes = list(dict.fromkeys(observation['visible_scenes']))
        item = {'name': observation['name'], 'distinct_visible_scenes': scenes,
                'evidence': observation['evidence']}
        (recurring if len(scenes) >= 2 else one_page).append(item)
    return {'faithful': raw['faithful'], 'complete': not recurring,
            'routing_correct': raw['routing_correct'], 'uncertain': raw['uncertain'],
            'missing_recurring_subjects': recurring, 'one_page_observations': one_page,
            'issues': raw['design_or_routing_issues'], 'evidence': raw['evidence']}


def compile_library(project, model, generate=None):
    import jsonschema
    from .quality import json_model
    from .storage import write_json
    generate = generate or json_model
    prompt, schema = request(project)
    key = digest([VERSION, prompt, model])
    root = Path(project['book_root']) / 'visual-library' / key[:16]
    approved = root / 'approved.json'
    if approved.exists():
        saved = json.loads(approved.read_text())
        if saved['source_hash'] != key:
            raise ValueError('Visual library source mismatch.')
        validate(project, saved['plan'])
        return saved
    feedback = ''
    for attempt in range(1, 4):
        path = root / f'plan-{attempt:02d}.json'
        request_path = root / f'request-{attempt:02d}.json'
        if not request_path.exists():
            write_json(request_path, {'prompt': prompt + feedback, 'schema': schema, 'model': model})
        value = json.loads(path.read_text()) if path.exists() else checked_model_call(
            root, f'plan-{attempt:02d}', generate, project['config']['ollama_url'], model, prompt + feedback, schema, seed=attempt-1)
        write_json(path, value)
        try:
            validate(project, value)
        except (ValueError, jsonschema.ValidationError) as exc:
            feedback = '\nFix this structural problem: ' + str(exc) + '\nPrior plan: ' + json.dumps(value)
            continue
        review_path = root / f'review-{attempt:02d}-observations-v1.json'
        audit_prompt, audit_schema = audit_request(project, value)
        review = json.loads(review_path.read_text()) if review_path.exists() else checked_model_call(
            root, f'review-{attempt:02d}-observations-v1', generate, project['config']['ollama_url'], model, audit_prompt, audit_schema)
        write_json(review_path, review)
        review = classify_observations(review)
        if (not value['uncertain'] and not value['issues'] and not review['uncertain'] and not review['issues']
                and not review['missing_recurring_subjects']
                and all(review[k] for k in ('faithful', 'complete', 'routing_correct'))):
            saved = {'version': VERSION, 'source_hash': key, 'model': model, 'plan': value, 'review': review}
            write_json(approved, saved)
            return saved
        feedback = '\nCorrect these review findings without rewriting the story: ' + json.dumps({'plan': value, 'review': review})
    raise ValueError('Visual reference planning needs review; all attempts saved in ' + str(root))


def entries(project, spec=None):
    values = project.get('visual_library', {}).get('plan', {}).get('entries', [])
    if spec is None:
        return values
    scenes = dict(story_scenes(project))
    scene = scenes.get(spec['name'])
    wanted, blocked = set(), set()
    if scene and project.get('scene_contract', {}).get('scenes'):
        from .scene_contract import scene_render_details, effective_record
        objects, _ = scene_render_details(project, scene)
        wanted = {o['id'] for o in objects}
        blocked = set((effective_record(project, spec['name']) or {}).get('absent_object_ids', []))
    selected = []
    for entry in values:
        if entry['source_object_id'] in blocked:
            continue
        routed = spec['name'] in entry['scenes']
        if entry['source_object_id'] in wanted:
            # A worn garment already has its character portrait. Only augment a
            # detached/currently altered garment's route, avoiding a second scarf
            # reference on the clean, fully dressed opening pages.
            if entry['source_character_id']:
                from .state_ledger import active_changes
                routed = routed or bool(active_changes(project, scene, entry['source_character_id']))
            else:
                routed = True
        if routed:
            selected.append(entry)
    return selected


def asset_name(entry):
    return ('props/' if entry['kind'] == 'prop' else 'locations/') + entry['id'] + '.png'


def specs(project):
    from .story import style_text, scene_style_text
    result = []
    for entry in entries(project):
        reference = ('characters/' + entry['source_character_id'] + '.png'
                     if entry['source_character_id'] else 'style.png')
        if entry['kind'] == 'prop':
            prompt = ('Create a canonical picture-book OBJECT reference. Show ONE complete inanimate '
                'object, three-quarter view, fully visible on a plain pale background. Subject: '
                + entry['name'] + '. Permanent design: ' + entry['appearance'] + '. '
                'Keep a clear recognizable silhouette, construction and natural object proportions. '
                'No scene, living characters, hands, body parts, story contents, writing or labels. '
                'A carved figure/face belonging to the specified statue is stone decoration, not a living actor. ')
            if entry['source_character_id']:
                prompt += ('Image1 is the approved source character portrait. Extract and illustrate ONLY '
                    + entry['source_item'] + ' as the SAME separate object. Match its colour, knit, '
                    'construction, pattern and proportions. Natural untying/unfolding is allowed. '
                    'Do not include any of its wearer, fur, face, body or limbs. ')
            else:
                prompt += 'Image1 provides painting style and palette only; it supplies no object shapes. '
        else:
            prompt = ('Create a canonical unpopulated LOCATION reference for a picture book. '
                'Show a clear establishing view of ' + entry['name'] + '. Fixed place design: '
                + entry['appearance'] + '. Depict its architecture, ground surfaces, permanent scenery '
                'and coherent layout. No living characters or movable story props; these are added in '
                'individual scenes. Image1 provides painting style and palette only. No labels or lettering. ')
        style = (scene_style_text(project) if project.get('render_settings', {}).get('visual_reference_prompt_policy')
                 else style_text(project))
        if project.get('render_settings', {}).get('positive_flux_prompts'):
            if entry['kind'] == 'prop':
                prompt = (f"One {entry['name']}: {entry['appearance']}. "
                          "A complete three-quarter object view on a plain pale backdrop, "
                          "showing its baseline construction, materials and natural proportions. "
                          "Unmarked artwork surfaces. ")
                if entry['source_character_id']:
                    prompt += (f"Extract {entry['source_item']} from the portrait in Image 1 as this "
                               "separate inanimate object. Match its design, colour, texture and pattern. "
                               "Arrange it naturally as a detached item. ")
                else:
                    prompt += "Image 1 supplies painting style and palette. "
            else:
                prompt = (f"An unpopulated establishing view of {entry['name']}: {entry['appearance']}. "
                          "Show the fixed architecture, ground and permanent scenery in a coherent layout. "
                          "Keep open surfaces clear for staging later scenes. "
                          "Image 1 supplies painting style and palette. Unmarked artwork surfaces. ")
        result.append({'name': asset_name(entry), 'kind': entry['kind'], 'references': [reference],
                       'prompt': prompt + style, 'visual_entry': entry})
    return result


def separate_reference_inputs(project, spec, existing_count):
    """Prefer individual designs within the dev budget; never silently drop inputs."""
    settings=project.get('render_settings', {})
    policy=settings.get('visual_reference_input_policy',
                        project.get('runtime_retry_policy', {}).get('visual_reference_input_policy',0))
    if policy < 1:
        return []
    from .prop_groups import sheet_entries
    selected=[]
    for kind in ('prop','location'):
        group=[e for e in entries(project,spec) if e['kind']==kind]
        if group:
            selected.extend(sheet_entries(project,spec,group))
    if existing_count+len(selected)>6:
        return []
    result=[]
    for item in selected:
        role=(f"the {item['name']} design. Match its shape, materials and colours in this scene's perspective. "
              'The scene action determines its placement and visibility.')
        if item.get('group'):
            group=item['group']
            role+=(f" Keep one {group['inner_detection']} inside one {group['outer_detection']}, "
                   f"with inner diameter about {group['diameter_ratio']:.0%} of the outer diameter.")
        result.append({'asset_name':item['asset_name'],'role':role})
    return result


def reference_sheet(project, spec, kind):
    """Lossless source selection, downscaled only for a bounded conditioning sheet."""
    from PIL import Image, ImageDraw
    from .storage import asset_path, valid_asset
    from .story import asset_specs
    selected = [e for e in entries(project, spec) if e['kind'] == kind]
    if not selected:
        raise ValueError('No visual references requested for this sheet.')
    from .prop_groups import sheet_entries
    panels = sheet_entries(project, spec, selected)
    by_name = {s['name']: s for s in asset_specs(project)}
    source_images = []
    for panel in panels:
        name = panel['asset_name']
        if not valid_asset(project, by_name[name]):
            raise ValueError('Unapproved canonical visual reference: ' + name)
        source_images.append(Image.open(asset_path(project, name)).convert('RGB'))
    if len(source_images) == 1:
        return source_images[0]
    cols = 2 if len(source_images) <= 4 else 3
    rows = (len(source_images)+cols-1)//cols
    width, height = 1024//cols, 1024//rows
    sheet = Image.new('RGB', (1024, 1024), '#fffaf1')
    draw = ImageDraw.Draw(sheet)
    for i, image in enumerate(source_images):
        image.thumbnail((width-12, height-34))
        x, y = (i % cols)*width, (i//cols)*height
        sheet.paste(image, (x+(width-image.width)//2, y+28+(height-34-image.height)//2))
        draw.text((x+8,y+8), str(i+1), fill='#444')
    return sheet


def reference_instruction(project, spec, kind, image_number):
    selected = [e for e in entries(project, spec) if e['kind'] == kind]
    from .prop_groups import sheet_entries
    panels = sheet_entries(project, spec, selected)
    roles = '; '.join(f"panel {i+1}: {e['name']}" for i,e in enumerate(panels))
    proportions = ' '.join(
        f"Panel {i+1} is ONE grouped pair: {p['group']['inner_detection']} inside {p['group']['outer_detection']}. "
        f"Preserve the inner object's diameter at about {p['group']['diameter_ratio']:.0%} of the outer container. "
        'Use this pair only if the scene shows its container; it must not add objects to an absent or cropped view. '
        'Move the visible pair together; do not resize the contents independently or add a second copy. '
        for i,p in enumerate(panels) if p.get('group'))
    if project.get('render_settings', {}).get('compact_prompt_policy',0) >= 11:
        proportions = ' '.join(
            f"Panel {i+1} defines one {p['group']['inner_detection']} inside one {p['group']['outer_detection']}. "
            f"Keep the inner diameter about {p['group']['diameter_ratio']:.0%} of the outer diameter. "
            'Wherever the container is visible, keep this pair together at that relative scale. '
            for i,p in enumerate(panels) if p.get('group'))
    if project.get('render_settings', {}).get('compact_prompt_policy',0) >= 7:
        return (f"Image {image_number} is the {kind} design reference ({roles}). "
                'Match these shapes, materials and colours in the scene perspective; '
                'use the scene action to determine placement and visibility. ' + proportions)
    return (f"Image {image_number} is the canonical {kind} reference ({roles}). "
        'Use these SAME designs where this scene shows the named subjects. Match permanent shape, '
        'materials, colours and distinctive construction. Allow the required perspective, natural '
        'cloth folds, occlusion, lighting and story-state changes; do not copy the reference layout, '
        'labels or empty backdrop. A statue remains the same carved figure, crown and base. '
        'References describe appearance; the story scene determines visibility, action and contents. ' + proportions)

"""Private persistent containment references, generated before scene artwork."""
import json
from pathlib import Path

from .story import digest, object_schema as obj

VERSION = 4


def groups(project, spec=None):
    values = project.get('prop_groups', {}).get('plan', {}).get('groups', [])
    if spec is None:
        return values
    from .visual_library import entries
    routed = {e['id'] for e in entries(project, spec)}
    return [g for g in values if spec['name'] in g['scenes']
            and {g['inner_id'], g['outer_id']} <= routed]


def request(project):
    from .visual_library import entries, story_scenes
    props = [e for e in entries(project) if e['kind'] == 'prop']
    ids = [e['id'] for e in props]
    frames = [name for name, _ in story_scenes(project)]
    facts = project.get('scene_contract', {}).get('persistent_facts', [])
    schema = obj({'groups': {'type': 'array', 'maxItems': 4, 'items': obj({
        'id': {'type': 'string', 'pattern': '^[a-z][a-z0-9_]{0,31}$'},
        'inner_id': {'type': 'string', 'enum': ids}, 'outer_id': {'type': 'string', 'enum': ids},
        'source_fact_id': {'type': 'string', 'enum': ['', *[f['id'] for f in facts]]},
        'inner_detection': {'type': 'string', 'minLength': 1},
        'outer_detection': {'type': 'string', 'minLength': 1},
        'diameter_ratio': {'type': 'number', 'minimum': .1, 'maximum': .8},
        'scenes': {'type': 'array', 'uniqueItems': True, 'minItems': 2,
                   'items': {'type': 'string', 'enum': frames}},
        'evidence': {'type': 'string', 'minLength': 1}})},
        'uncertain': {'type': 'boolean'}, 'issues': {'type': 'array', 'items': {'type': 'string'}}})
    prompt = ('Plan reusable PRIVATE containment/relative-size reference groups from the immutable '
        'story and approved prop catalogue. This version supports ONLY a clearly visible round object '
        'inside a larger round TRANSPARENT container, recurring on at least two story pages. The '
        'same sizes must persist unless the prose actually changes them. Examples: a ball inside a '
        'bubble or a marble inside a clear orb. Do NOT include clothing, liquid levels, flexible '
        'attachments, open bowls, hidden contents, cast, buildings or unrelated neighbouring objects. '
        'Those need other geometry policies. Empty groups is correct if no eligible pair exists. '
        'Use catalogue IDs; inner and outer must differ. Give concise visually distinctive detector '
        'noun phrases, e.g. a red ball / a soap bubble, with no character names. diameter_ratio is '
        'inner diameter divided by outer diameter. Honor any explicit numeric size. Otherwise choose '
        'one plausible canonical size consistent with the described air gap and story action; this '
        'private design decision stays fixed through the book. Large airy container around a small '
        'object needs a generous gap, not a nearly full container. Do not invent growth, shrinkage, '
        'contents or plot events. scenes includes only frames where BOTH may visibly coexist in this '
        'containment relationship. Exclude a popped container or subsequently released object. '
        'Include parts/pronouns implied by ongoing story continuity. Set source_fact_id to the '
        'persistent containment fact defining this pair and its active page interval when provided; '
        'otherwise use an empty string. Use the entire conditional interval, not just pages explicitly '
        'spelling out both names. The scene router still omits subjects that are actually absent. '
        'A subject can join at most one '
        'group per frame. Explain evidence. No uncertainty when the sources are clear.\n'
        + json.dumps({'story': project['story'], 'props': props,
            'frames': dict(story_scenes(project)),
            'facts': project.get('scene_contract', {}).get('persistent_facts', [])}, ensure_ascii=False))
    return prompt, schema


def validate(project, plan):
    import jsonschema
    jsonschema.validate(plan, request(project)[1])
    ids = set()
    occupancy = set()
    facts = {f['id']: f for f in project.get('scene_contract', {}).get('persistent_facts', [])}
    from .visual_library import entries
    objects = {e['id']: e['source_object_id'] for e in entries(project)}
    for g in plan['groups']:
        if g['id'] in ids or g['inner_id'] == g['outer_id']:
            raise ValueError('Containment groups need distinct IDs and distinct objects.')
        ids.add(g['id'])
        if g['source_fact_id']:
            fact = facts[g['source_fact_id']]
            if (fact.get('visibility') == 'absent' or
                    {objects[g['inner_id']], objects[g['outer_id']]} != set(fact['object_ids'])):
                raise ValueError('Containment group must cite its own positive two-object fact.')
        if len([n for n in g['scenes'] if n.startswith('pages/')]) < 2:
            raise ValueError('Containment references require two story pages.')
        for name in g['scenes']:
            for subject in (g['inner_id'], g['outer_id']):
                key = (name, subject)
                if key in occupancy:
                    raise ValueError('An object cannot be duplicated into overlapping groups.')
                occupancy.add(key)


def compile_groups(project, model, generate=None):
    from .quality import json_model
    from .storage import write_json
    from .visual_library import entries
    generate = generate or json_model
    if len([e for e in entries(project) if e['kind'] == 'prop']) < 2:
        return {'version': VERSION, 'plan': {'groups': [], 'uncertain': False, 'issues': []}}
    prompt, schema = request(project)
    key = digest([VERSION, prompt, model])
    root = Path(project['book_root']) / 'prop-groups' / key[:20]
    approved = root / 'approved.json'
    if approved.exists():
        saved = json.loads(approved.read_text())
        if saved['source_hash'] != key:
            raise ValueError('Containment plan source mismatch.')
        validate(project, saved['plan'])
        return saved
    feedback = ''
    for attempt in range(1, 4):
        write_json(root / f'request-{attempt}.json', {'prompt': prompt+feedback, 'schema': schema, 'model': model})
        file = root / f'plan-{attempt}.json'
        plan = json.loads(file.read_text()) if file.exists() else generate(
            project['config']['ollama_url'], model, prompt+feedback, schema, seed=attempt-1)
        write_json(file, plan)
        plan = json.loads(json.dumps(plan))
        facts = {f['id']: f for f in project.get('scene_contract', {}).get('persistent_facts', [])}
        for g in plan['groups']:
            fact = facts.get(g.get('source_fact_id'))
            if fact and isinstance(fact.get('from_page'), int) and isinstance(fact.get('through_page'), int):
                eligible = set(g['scenes']) | {f'pages/page-{n:03d}.png' for n in range(
                    fact['from_page'], fact['through_page']+1)}
                g['scenes'] = sorted(name for name in eligible if
                    {g['inner_id'], g['outer_id']} <= {e['id'] for e in entries(project, {'name': name})})
                g['evidence'] = ('Native effective scene routing: both approved object IDs are relevant '
                    'in these frames under persistent fact ' + fact['id'] + ': ' + fact['requirement']
                    + '. An unnamed contained object remains present when its transparent container is visible.')
        try:
            validate(project, plan)
        except (ValueError, __import__('jsonschema').ValidationError) as exc:
            feedback = '\nFix structural error: ' + str(exc) + '\n' + json.dumps(plan)
            continue
        review_schema = obj({'faithful': {'type': 'boolean'}, 'complete': {'type': 'boolean'},
            'routing_correct': {'type': 'boolean'}, 'sizes_plausible': {'type': 'boolean'},
            'uncertain': {'type': 'boolean'}, 'issues': {'type': 'array', 'items': {'type': 'string'}}})
        rp = root / f'review-{attempt}.json'
        review_prompt = ('Independently check this private group plan. Only repeated round visible '
            'contents in a round transparent container are in scope; do not demand statue/cast or '
            'cloth measurements. Check all eligible pairs, membership, routing until release/pop, '
            'and plausible fixed inner/outer diameter ratios. The supplied scenes have already been '
            'intersected with the native effective object routes. A missing noun in an illustration '
            'brief is NOT absence: a positive persistent containment fact requires the contained '
            'object whenever that transparent container is visible. This fills abbreviated briefs '
            'without changing any prose. Do not require the ball to vanish on a bubble-only brief. '
            'An actually absent container is excluded by the effective route filter. '
            'Unspecified size is a permitted '
            'design choice; contradictory growth or arbitrary changed prose is not.\n'
            + prompt + '\nCandidate: ' + json.dumps(plan))
        write_json(root / f'review-request-{attempt}.json', {'prompt': review_prompt, 'schema': review_schema})
        review = json.loads(rp.read_text()) if rp.exists() else generate(
            project['config']['ollama_url'], model, review_prompt, review_schema)
        write_json(rp, review)
        if (not plan['uncertain'] and not plan['issues'] and not review['uncertain'] and not review['issues']
                and all(review[k] for k in ('faithful', 'complete', 'routing_correct', 'sizes_plausible'))):
            # Existing books inherit the first measurable approved story occurrence
            # from the most recent saved rendition containing that page.
            # Fresh books establish the planned ratio before their first image.
            baselines = {}
            for group in plan['groups']:
                baseline = previous_baseline(project, group, model, generate)
                if baseline:
                    baselines[group['id']] = baseline
                    group['diameter_ratio'] = baseline['ratio']
            saved = {'version': VERSION, 'source_hash': key, 'model': model,
                'plan': plan, 'review': review, 'previous_baselines': baselines}
            validate(project, plan)
            write_json(approved, saved)
            return saved
        feedback = '\nCorrect these findings without changing the story: ' + json.dumps({'plan': plan, 'review': review})
    raise ValueError('Containment planning requires review. Saved attempts: ' + str(root))


def previous_baseline(project, group, model, generate):
    from .storage import valid_asset, asset_path
    from .story import asset_specs
    from .object_geometry import measure
    candidates = []
    for file in (Path(project['book_root']) / 'renders').glob('*/project.json'):
        try:
            old = json.loads(file.read_text())
            prepared_file = file.with_name('prepared-state-project.json')
            if prepared_file.exists():
                prepared = json.loads(prepared_file.read_text())
                if all(prepared[k] == old[k] for k in ('book', 'config', 'render_settings', 'render_root')):
                    old = prepared
            if old['story'] != project['story']:
                continue
            for spec in asset_specs(old):
                if (spec['name'].startswith('pages/') and spec['name'] in group['scenes']
                        and valid_asset(old, spec)):
                    path = asset_path(old, spec['name'])
                    candidates.append((spec['name'], -path.stat().st_mtime_ns, str(path), old))
        except (ValueError, KeyError, OSError):
            continue
    for name, _, path, old in sorted(candidates, key=lambda row: row[:3])[:4]:
        probe = {**project, 'render_settings': {'review_model': model}}
        measurement = measure(probe, Path(path).read_bytes(), group['inner_detection'],
                              group['outer_detection'], generate)
        ratio = measurement['ratio']
        if ratio is not None and .1 <= ratio <= .8:
            return {'source': path, 'scene': name, 'ratio': ratio,
                'source_hash': measurement['source_hash'], 'evidence_dir': measurement['evidence_dir']}
    return None


def asset_name(group):
    return 'prop_groups/' + group['id'] + '.png'


def specs(project):
    from .visual_library import entries, asset_name as single_name
    by_id = {e['id']: e for e in entries(project)}
    result = []
    for group in groups(project):
        inner, outer = by_id[group['inner_id']], by_id[group['outer_id']]
        prompt = ('Create ONE canonical picture-book containment reference. Image 1 supplies ONLY '
            + inner['name'] + '; Image 2 supplies ONLY ' + outer['name'] + '. Show exactly one '
            + inner['name'] + ' visibly inside exactly one ' + outer['name'] + '. Preserve both '
            'approved designs, materials, colours and painted style. The INNER object diameter is '
            f"{group['diameter_ratio']:.1%} of the OUTER container diameter. "
            'Keep the indicated broad gap around the inner object, with both full outlines visible. '
            'Render a single coherent nested pair, not a collage or two separate panels. Plain pale '
            'background, no scene, characters, attachments, honey, stains, dark holes, lettering or '
            'additional objects. Clean canonical designs only; page-specific changes are added later.')
        result.append({'name': asset_name(group), 'kind': 'prop_group',
            'references': [single_name(inner), single_name(outer)], 'prompt': prompt, 'group': group})
        if project.get('render_settings', {}).get('positive_flux_prompts'):
            result[-1]['prompt'] = (f"One {inner['name']} visibly inside one {outer['name']}, "
                "forming a single nested pair on a plain pale backdrop. "
                f"Image 1 defines the {inner['name']}; Image 2 defines the {outer['name']}. "
                "Preserve their approved shapes, materials, colours and painted style. "
                f"The inner diameter is {group['diameter_ratio']:.1%} of the outer diameter. "
                "Show the gap around the inner object and both complete outlines. "
                "Clean baseline surfaces, evenly lit and unmarked.")
    return result


def sheet_entries(project, spec, original):
    """Replace two separate panels by one approved group; never duplicate members."""
    active = groups(project, spec)
    membership = {cid: g for g in active for cid in (g['inner_id'], g['outer_id'])}
    done, result = set(), []
    from .visual_library import asset_name as single_name
    for entry in original:
        group = membership.get(entry['id'])
        if group:
            if group['id'] not in done:
                result.append({'name': group['inner_detection'] + ' inside ' + group['outer_detection'],
                    'asset_name': asset_name(group), 'group': group})
                done.add(group['id'])
        else:
            result.append({'name': entry['name'], 'asset_name': single_name(entry)})
    return result


def check(project, group, png, generate, reference=False):
    from .object_geometry import measure, verdict
    measured = measure(project, png, group['inner_detection'], group['outer_detection'], generate)
    decision = verdict(measured['ratio'], group['diameter_ratio'], .20 if reference else .25)
    if reference and measured['ratio'] is not None:
        # An uncluttered canonical reference must meet the declared design band;
        # broad scene-boundary uncertainty is not permission to shift the canon.
        inside = .8*group['diameter_ratio'] <= measured['ratio'] <= 1.2*group['diameter_ratio']
        decision.update(accepted=inside, status='consistent' if inside else 'mismatch')
    # Crops, deformation and uncertain boundaries are not numeric size failures.
    # Group references themselves require full measurable outlines before use.
    accepted = decision['accepted'] if decision['accepted'] is not None else not reference
    issue = ('Persistent size mismatch: ' + group['inner_detection'] + ' is '
        f"{measured['ratio']:.0%} of {group['outer_detection']}, canonical {group['diameter_ratio']:.0%}."
        if decision['status'] == 'mismatch' else 'Canonical containment reference has no reliable full-outline measurement.')
    return {'id': group['id'], 'kind': 'object_scale', 'accepted': accepted,
        'measurement': measured, 'decision': decision, 'review': {
            'uncertain': reference and decision['status'] == 'unmeasurable',
            'evidence': measured['audit']['evidence'], 'issues': [] if accepted else [issue],
            'retry_instructions': [] if accepted else [
                f"Keep {group['inner_detection']} about {group['diameter_ratio']:.0%} of "
                + group['outer_detection'] + " in diameter, as in the grouped reference. Preserve the "
                + ('container size and the two approved object designs. Keep ONLY these two '
                   'inanimate objects on a plain backdrop.' if reference else
                   'container size, character identities, scene action and all unaffected details.')]}}


def review_reference(project, spec, png, generate):
    from .quality import VISUAL_CHECKS, passed
    from .storage import asset_path
    group = spec['group']
    schema = obj({'same_designs': {'type': 'boolean'}, 'one_each': {'type': 'boolean'},
        'contained': {'type': 'boolean'}, 'no_extras': {'type': 'boolean'}, 'style_matches': {'type': 'boolean'},
        'uncertain': {'type': 'boolean'}, 'evidence': {'type': 'string'},
        'issues': {'type': 'array', 'items': {'type': 'string'}},
        'retry_instructions': {'type': 'array', 'items': {'type': 'string'}}})
    prompt = ('Review candidate IMAGE1 as one reusable containment reference. IMAGE2 supplies the '
        'inner object, IMAGE3 its transparent outer container. Verify SAME two designs, exactly '
        'one each, actual visible containment, no invented shapes, stains, attachments, scenery, '
        'living cast or text. Both complete outlines must be visible. Style concerns paint/line '
        'technique, not copying source layouts. Sizes are measured separately; do not guess ratios.\n'
        + json.dumps(group))
    result = generate(project['config']['ollama_url'], project['render_settings']['review_model'],
        prompt, schema, [png, *[asset_path(project, n).read_bytes() for n in spec['references']]])
    checks = dict.fromkeys(VISUAL_CHECKS, True)
    checks.update(scene_matches=all(result[k] for k in ('same_designs', 'contained', 'one_each')),
        style_matches=result['style_matches'], reference_background_ok=result['no_extras'])
    report = {'checks': checks, 'characters': [], 'unexpected_character_count': 0,
        'uncertain': result['uncertain'], 'evidence': result['evidence'],
        'issues': result['issues'], 'retry_instructions': result['retry_instructions'], 'retry_scene': ''}
    geometry = check(project, group, png, generate, reference=True)
    from .visual_review import apply_checks
    apply_checks(report, [geometry])
    return {'accepted': passed(report, []), 'review': report, 'visual_group_review': result,
        'object_scale_checks': [geometry], 'detections': {}, 'scale_review': None, 'inventory': None}


def compose_spheres(inner_image, outer_image, inner_box, outer_box, ratio):
    """A conditioning reference from existing pixels, with an exact shared scale."""
    from PIL import Image, ImageDraw, ImageFilter
    # Source boundaries must have been independently audited first. This is only
    # for the supported round-object geometry, never a general subject cutout.
    for box in (inner_box, outer_box):
        w, h = box[2]-box[0], box[3]-box[1]
        if min(w,h) <= 10 or not .85 <= w/h <= 1.18:
            raise ValueError('Source is not a full round object suitable for spherical assembly.')
    crop_box = tuple(round(x) for x in inner_box)
    crop = inner_image.convert('RGB').crop(crop_box)
    diameter = ((outer_box[2]-outer_box[0])+(outer_box[3]-outer_box[1])) / 2 * ratio
    source_diameter = sum(crop.size)/2
    size = tuple(max(1, round(d*diameter/source_diameter)) for d in crop.size)
    crop = crop.resize(size, Image.Resampling.LANCZOS)
    # A supersampled ellipse removes the source paper/shadow outside the sphere;
    # a narrow feather preserves the painted antialiased silhouette.
    mask = Image.new('L', (size[0]*4, size[1]*4))
    ImageDraw.Draw(mask).ellipse((2,2,mask.width-3,mask.height-3), fill=255)
    mask = mask.resize(size, Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(.35))
    cx, cy = (outer_box[0]+outer_box[2])/2, (outer_box[1]+outer_box[3])/2
    at = (round(cx-size[0]/2), round(cy-size[1]/2))
    result = outer_image.convert('RGB').copy()
    result.paste(crop, at, mask)
    return result, {'inner_box': inner_box, 'outer_box': outer_box, 'target_ratio': ratio,
        'placed_size': list(size), 'placed_at': list(at), 'method': 'audited spherical cutout on original container pixels'}


def assemble_reference(project, spec, generate=None):
    import hashlib
    import io
    import logging
    from PIL import Image
    from .object_geometry import measure
    from .quality import json_model
    from .storage import asset_path, valid_asset, write_json, write_exclusive
    from .story import asset_specs
    generate = generate or json_model
    by_name = {s['name']: s for s in asset_specs(project)}
    data = []
    for name in spec['references']:
        if not valid_asset(project, by_name[name]):
            raise ValueError('Unapproved source for containment assembly: ' + name)
        data.append(asset_path(project, name).read_bytes())
    hashes = [hashlib.sha256(x).hexdigest() for x in data]
    key = digest([1, spec['group'], hashes])
    root = Path(project['book_root']) / 'prop-group-assembly' / key[:20]
    record = root / 'assembly.json'
    image_path = root / 'reference.png'
    if record.exists():
        saved = json.loads(record.read_text())
        if saved['source_hashes'] != hashes:
            raise ValueError('Containment assembly source mismatch.')
        if saved['available']:
            if hashlib.sha256(image_path.read_bytes()).hexdigest() != saved['png_sha256']:
                raise ValueError('Containment assembly pixels changed after preparation.')
            return {**saved, 'path': str(image_path)}
        return None
    group = spec['group']
    boxes, evidence = [], []
    for index, (png, subject_id) in enumerate(zip(data, ('inner', 'outer'))):
        measured = measure(project, png, group['inner_detection'], group['outer_detection'], generate)
        subjects = {s['id']: s for s in measured['audit']['subjects']}
        subject = subjects.get(subject_id, {})
        bi = subject.get('box_index', -1)
        adequate = (not measured['audit']['uncertain'] and
            all(subject.get(k) for k in ('present', 'box_tight', 'outline_complete')) and
            not subject.get('deformed') and 0 <= bi < len(measured['boxes']))
        other = subjects.get('outer' if subject_id == 'inner' else 'inner', {})
        if not adequate or other.get('present'):
            reason = 'Individual reference boundary/subject could not be isolated reliably.'
            write_json(record, {'available': False, 'source_hashes': hashes, 'reason': reason,
                'evidence_dir': measured['evidence_dir']})
            logging.warning('Book v2: %s Falling back to native generated group reference.', reason)
            return None
        boxes.append(measured['boxes'][bi]['bbox'])
        evidence.append(measured['evidence_dir'])
    try:
        image, proof = compose_spheres(*[Image.open(io.BytesIO(png)) for png in data],
                                      *boxes, group['diameter_ratio'])
    except ValueError as exc:
        write_json(record, {'available': False, 'source_hashes': hashes, 'reason': str(exc)})
        return None
    buf = io.BytesIO(); image.save(buf, format='PNG'); png = buf.getvalue()
    write_exclusive(image_path, png)
    saved = {'available': True, 'source_hashes': hashes, 'evidence_dirs': evidence,
        'png_sha256': hashlib.sha256(png).hexdigest(), 'geometry': proof,
        'review_required': True}
    write_json(record, saved)
    return {**saved, 'path': str(image_path)}

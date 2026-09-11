"""Focused state/prop veto; it can never clear identity, anatomy or scale failures."""
import io
import json
import re


def protected_review_context(project, spec, png):
    """Replace a contradictory BEFORE reference only with verified pixel evidence.

    The broad audit sees the complete candidate and a magnified AFTER crop.
    The separate state audit retains before/after comparison; neither clears
    another audit's failures.
    """
    from .state_edit import restore_cloth_before_edit
    if (spec['kind'] != 'state' or not spec.get('edits')
            or not project.get('render_settings',{}).get('quality_required')
            or not all(restore_cloth_before_edit(c) for c in spec['changes'])):
        return None
    from PIL import Image
    from .story import asset_specs
    from .storage import asset_path, valid_asset
    from .state_assets import variant_inputs, outside_pixels_unchanged, png_bytes
    import hashlib
    baseline_name = spec['references'][0]
    baseline_spec = next(s for s in asset_specs(project) if s['name'] == baseline_name)
    if not valid_asset(project, baseline_spec) or not outside_pixels_unchanged(project, spec, png):
        return None
    _, mask = variant_inputs(project, spec)
    box = mask.getbbox()
    if not box or sum(mask.histogram()[1:]) > mask.width*mask.height*.02:
        return None
    after = Image.open(io.BytesIO(png)).convert('RGB')
    # Keep surrounding cloth/seams visible so patch boundaries can be audited.
    x0,y0,x1,y1 = box
    pad = max(16, round(max(x1-x0,y1-y0)*.25))
    box = (max(0,x0-pad),max(0,y0-pad),min(after.width,x1+pad),min(after.height,y1+pad))
    crop = after.crop(box)
    crop.thumbnail((512,512),Image.Resampling.LANCZOS)
    factor = 512/max(crop.size)
    crop = crop.resize((round(crop.width*factor),round(crop.height*factor)),Image.Resampling.LANCZOS)
    return {'crop':png_bytes(crop), 'proof':{
        'baseline':baseline_name, 'baseline_sha256':hashlib.sha256(asset_path(project,baseline_name).read_bytes()).hexdigest(),
        'candidate_sha256':hashlib.sha256(png).hexdigest(), 'outside_pixels_unchanged':True,
        'baseline_signature':baseline_spec['signature'], 'candidate_crop_box':box}}


def observe_surface(project, change, png, generate, visible_ids):
    """One image per observation prevents candidate/reference role swapping."""
    from PIL import Image
    from .state_assets import measure_part, select_boxes, png_bytes
    from .state_ledger import obj
    from .story import digest
    from .storage import checked_root, write_json
    key = digest(['surface-observation-v5', sorted(visible_ids), change['character_id'], change['part'], change['surface'],
                  change['reference_edit']['target_query'], project['render_settings']['review_model'],
                  __import__('hashlib').sha256(png).hexdigest()])
    directory = checked_root(project) / 'quality' / 'state-observations'
    path = directory / (key + '.json')
    if path.exists():
        return json.loads(path.read_text())
    image = Image.open(io.BytesIO(png)).convert('RGB')
    from .detection import detect_cast
    actor = next(c for c in project['book']['characters'] if c['id'] == change['character_id'])
    detected = detect_cast(png, [c for c in project['book']['characters'] if c['id'] in visible_ids])
    actor_box = detected.get(actor['id'], {}).get('bbox')
    # A global garment query called the child's red coat a waistcoat. Establish
    # the correct actor first; only then search within that actor's measured box.
    if actor_box:
        x0,y0,x1,y1 = actor_box
        image = image.crop((max(0,int(x0)-8),max(0,int(y0)-8),min(image.width,int(x1)+9),min(image.height,int(y1)+9)))
    garments = re.search(r'\b(waistcoat|coat|hat|scarf|shirt|dress|ears?|tail)\b', change['surface']+' '+change['part'], re.I)
    measured = None
    # A detached scarf crop cannot establish whether it is attached to a neck.
    # Keep the body/attachment context for changes to an entire garment.
    attachment_context = bool(re.search(r'\b(scarf|hat|cape|coat|shirt|dress)\b',
                                       change['reference_edit']['target_query'], re.I))
    if garments and actor_box and not attachment_context:
        proposals = measure_part(png_bytes(image), 'a '+garments[1].lower()+'.')
        try:
            selected = select_boxes(proposals, 'single')[0]
            x0,y0,x1,y1 = selected['bbox']
            if (x1-x0)*(y1-y0) > image.width*image.height*.75:
                raise ValueError('A whole-actor box is not a local garment measurement.')
            measured = [max(0,int(x0)-12),max(0,int(y0)-12),min(image.width,int(x1)+13),min(image.height,int(y1)+13)]
            image = image.crop(measured)
        except ValueError:
            pass  # Ambiguous localisation cannot pick an arbitrary actor's coat.
    factor = 768/max(image.size)
    image = image.resize((round(image.width*factor),round(image.height*factor)),Image.Resampling.LANCZOS)
    schema = obj({'surface_visibility': {'type':'string','enum':['fully_visible','partly_visible','hidden','unclear']},
                  'target_objects': {'type':'array','items':obj({'location':{'type':'string'},'description':{'type':'string'}})},
                  'other_marks': {'type':'array','items':obj({'location':{'type':'string'},'description':{'type':'string'}})},
                  'description': {'type':'string'}})
    report = generate(project['config']['ollama_url'],project['render_settings']['review_model'],
        'Observe this ONE image without assuming a requested edit has happened. Describe the visible '
        'physical surface and whether it faces the viewer or is hidden. List EACH separate attached target '
        'object on the named garment/body part, with its physical location and visible appearance. Count '
        'a circular button only when a circular button is actually visible; thread crosses, gaps and stains '
        'are other_marks, not intact buttons. Do not count a separate object held by another actor as an '
        'attached object. List other visible marks, stating whether they are on the FRONT, SIDE or BACK. '
        'Establish the torso orientation from the garment cut and arm openings. A face looking back '
        'over a shoulder does not make the back of its torso into the front. '
        'Do not infer hidden objects, guess a required number, or describe another reference image. '
        'Distinguish fabric held by hands/flippers across the belly from fabric actually wrapped '
        'around or fastened to the neck/shoulders. Describe the visible bare neck and the position '
        'of the fabric separately. Overlapping the torso in the picture does not establish attachment. '
        'For a stain/removed hat, describe actual marks or absence in the same way.\n'
        +json.dumps({'part':change['part'],'surface_to_check':change['surface'],
                    'actor':actor['name'],
                    'attached_target_query':change['reference_edit']['target_query'],
                    'measured_crop':measured is not None}),schema,[png_bytes(image)])
    result={'observation':report,'crop_box_within_actor':measured,'actor_box':actor_box}
    write_json(path,result)
    return result


def review_states(project, spec, png, generate):
    from PIL import Image
    from .state_ledger import active_changes, obj, character_reference
    from .state_assets import outside_pixels_unchanged, variant_inputs, png_bytes, prop_reference
    from .storage import asset_path
    if spec['kind'] == 'state' and spec.get('edit_mode') == 'clothing_addition':
        changes, props = spec['changes'], []
        images = [png, asset_path(project,spec['references'][0]).read_bytes()]
        mapping = ('Image1 is the candidate AFTER portrait. Image2 is the approved BEFORE portrait. '
                   'The only permitted change is the explicitly added clothing. Its natural coverage of '
                   'fur/body is allowed. Identity, face, anatomy, underlying proportions, existing outfit '
                   'and painted style must remain. This is a whole-reference edit, with no claim of '
                   'pixel-exact preservation or a measured mask.')
    elif spec['kind'] == 'state':
        changes, props = spec['changes'], []
        before, mask = variant_inputs(project, spec)
        if not outside_pixels_unchanged(project, spec, png):
            return {'accepted': False, 'issues': ['Protected state edit changed pixels outside its measured mask.'],
                    'uncertain': False, 'items': [], 'outside_pixels_unchanged': False}
        box = mask.getbbox()
        after = Image.open(io.BytesIO(png)).convert('RGB')
        # Both local crops use precisely the same measured coordinates.
        images = [png, png_bytes(before), png_bytes(before.crop(box).resize((512,512))),
                  png_bytes(after.crop(box).resize((512,512)))]
        mapping = 'Image1 edited portrait; Image2 unchanged baseline; Image3 magnified BEFORE; Image4 same area AFTER.'
        protected_context = protected_review_context(project, spec, png)
        if protected_context is not None:
            images = [png, protected_context['crop']]
            mapping = ('Image1 is the complete AFTER portrait; Image2 is its magnified AFTER edit region. '
                       'Exact RGB comparison proves every pixel outside the measured mask still matches '
                       'the approved baseline. BEFORE appearance is recorded by the separate single-image '
                       'observation below. There is no BEFORE portrait among these images.')
    elif spec['kind'] == 'scene' and project.get('art_plan'):
        scene = project['book']['cover'] if spec['name'] == 'cover.png' else next(
            p for p in project['book']['pages'] if spec['name'] == f"pages/page-{p['page_number']:03d}.png")
        changes, props = active_changes(project, scene), spec.get('props', [])
        if not changes and not props:
            return None
        images, labels = [png], ['Image1 is the candidate scene.']
        for cid in dict.fromkeys(c['character_id'] for c in changes):
            images.append(asset_path(project, character_reference(project, scene, cid)).read_bytes())
            labels.append(f'Image{len(images)} is the approved CURRENT-STATE reference for {cid}.')
        for prop in props:
            data, description = prop_reference(project, prop)
            images.append(data)
            from .state_ledger import is_addition
            change=next(c for c in project['art_plan']['ledger']['changes'] if c['id']==prop['source_change_id'])
            role='approved garment worn by its former owner' if is_addition(change) else 'measured source-detail reference'
            labels.append(f"Image{len(images)} is the {role} for {prop['id']}: {description}.")
        mapping = '\n'.join(labels)
    else:
        return None
    observations = []
    for change in changes:
        reference = asset_path(project, spec['references'][0]).read_bytes() if spec['kind']=='state' else asset_path(
            project, character_reference(project,scene,change['character_id'])).read_bytes()
        observations.append({'id':change['id'],
            'reference_role':'BEFORE edit' if spec['kind']=='state' else 'REQUIRED current state',
            'reference':observe_surface(project,change,reference,generate,[change['character_id']]),
            'candidate':observe_surface(project,change,png,generate,
                         [spec['character_id']] if spec['kind']=='state' else scene['character_ids'])})
    ids = [c['id'] for c in changes] + [p['id'] for p in props]
    schema = obj({'items': {'type':'array', 'items': obj({
        'id': {'type':'string','enum':ids}, 'observation': {'type':'string'},
        'visibility': {'type':'string','enum':['visible','physically_occluded','unclear']},
        'matches': {'type':'boolean'}})}, 'uncertain': {'type':'boolean'},
        'issues': {'type':'array','items':{'type':'string'}},
        'retry_instructions': {'type':'array','items':{'type':'string'}}})
    recipes = ([e['plan'] for e in spec.get('edits',[])] if spec['kind']=='state' else
               [project['state_edits'][c['id']]['plan'] for c in changes if c['id'] in project.get('state_edits',{})])
    prompt = ('Audit ONLY consequential costume states and detached-prop design in candidate Image1. '
        'First record what you actually see at the named physical part, then compare. Count clearly visible '
        'fastenings on the current-state reference and the same candidate surface. A restored lost button, '
        'extra fastening, altered prop shape/pattern, or a front mark moved to the back is a failure. '
        'The reference is the SAME character, not another figure. Do not invent hidden details. '
        'In a scene, a physically hidden front can remain unverified if the back is correctly plain; '
        'A lost button means ONLY the selected button in reference_edit.selection, not every button. '
        'The intact buttons still present in the approved current-state reference must remain. '
        'this is legitimate occlusion, not restoration. An unclear visible detail is uncertain, not a pass. '
        'A detached object required visibly in this scene must actually be visible and match its source; '
        'mere mention or hiding it cannot pass. Surrounding fabric is crop context, not part of a detached '
        'button. Distinguish attached thread holes from invented dangling thread or cross-shaped marks. '
        'For flexible garments, compare the same material, colour, construction and distinctive design, '
        'allowing natural folds, drape and perspective. A cape may trail beside the torso in a front view '
        'while being attached over the shoulders/back. Side-visible trailing fabric is not evidence that '
        'it became a scarf. Require visible contradictory construction, length or attachment before '
        'declaring a different garment; do not infer a missing back drape from a hidden back. A removed '
        'garment may naturally untie and drape over its new support. Its former neck knot and worn shape '
        'are not required on the detached prop unless the story explicitly says they remain. '
        'Distinguish HOLDING a removed garment in front of the body from WEARING it: inspect the '
        'neck/shoulder attachment and visible bare surface. Fabric held across the belly or chest by '
        'hands/flippers is not worn around the neck merely because it overlaps the torso in the image. '
        'If the neck is bare and the hands hold the garment, record it as held. A real collar, knot or '
        'wrap visibly attached around the neck still fails a removal requirement. '
        'For an edited reference portrait every requested changed part must be visibly verifiable; '
        'occlusion is not a successful local edit. Preserve its other details. Return exactly one '
        'observation per required ID. Give affirmative precise retry instructions for real failures.\n'
        + mapping + '\n' + json.dumps({'asset_kind':spec['kind'], 'changes':changes, 'props':props,
                                      'final_material_recipes':recipes})
        + '\nSeparately observed single-image evidence (roles cannot be interchanged): '+json.dumps(observations)
        + '\nAn off-surface mark MUST set matches=false even if the correct surface is hidden. '
          'An attached target count larger than the required reference count is a failure when those '
          'objects are clearly visible. The current-state reference is authoritative for remaining '
          'fastenings: never invent a zero-button requirement. Read observations literally; do not swap '
          'before/after image roles. Use the full figure to establish torso orientation; a garment crop '
          'alone can mistake the back for the front. Reject a cross on the back if the required mark is '
          'front-only; merely seeing the one legitimate remaining button is not a failure.')
    if recipes:
        prompt += ('\nThe final_material_recipes translate the story change into precise visible material '
                   'and remaining-object inventory. Use them to resolve vague wording such as a button '
                   'leaving a gap. Fine loose thread or crossed sewing stitches explicitly required by the '
                   'recipe are legitimate on that front cloth surface; do not demand a torn hole. '
                   'The unchanged lower fastening remains required. Before/after observations have explicit '
                   'roles: never report the observed BEFORE count as the AFTER count. An actual solid '
                   'disc or ambiguous button-like dot in the selected region still fails.')
    if spec.get('edit_mode') == 'clothing_addition':
        prompt += ('\nThis approved operation ADDS the named garment over the baseline. The BEFORE '
                   'portrait correctly lacks it; its presence AFTER is required, not an extra-object error. '
                   'Compare unchanged identity and existing clothes separately from the intended addition. '
                   'Judge whether the new garment is naturally worn on the specified body surface. '
                   'Do not require it to appear in the BEFORE image or invent pixel-preservation proof.')
    report = generate(project['config']['ollama_url'], project['render_settings']['review_model'], prompt, schema, images)
    complete = sorted(r['id'] for r in report['items']) == sorted(ids)
    allowed = lambda r: r['visibility'] == 'visible' or (spec['kind'] == 'scene'
                        and r['visibility'] == 'physically_occluded' and r['id'] not in {p['id'] for p in props})
    accepted = (complete and report['uncertain'] is False and report['issues'] == []
                and all(r['matches'] is True and allowed(r) for r in report['items']))
    return {**report, 'accepted': accepted, 'surface_observations': observations,
            'outside_pixels_unchanged': (True if spec['kind'] == 'state'
                                        and spec.get('edit_mode') != 'clothing_addition' else None)}


def apply_state_review(report, state_review):
    if state_review is None or state_review['accepted'] is True:
        return
    report['checks']['scene_matches'] = False
    report['issues'].extend(state_review.get('issues') or ['Consequential visual state could not be verified.'])
    report.setdefault('retry_instructions', []).extend(state_review.get('retry_instructions', []))
    if state_review.get('uncertain'):
        report['uncertain'] = True

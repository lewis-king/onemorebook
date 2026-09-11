"""Visual identity checks for canonical objects/places and their scene instances."""
import json

from .story import object_schema as obj

TEXT = {'type': 'string', 'minLength': 1}


def review_reference(project, spec, png, generate):
    from .quality import VISUAL_CHECKS, passed
    from .storage import asset_path
    entry = spec['visual_entry']
    schema = obj({'design_matches': {'type': 'boolean'}, 'style_matches': {'type': 'boolean'},
        'object_complete': {'type': 'boolean'}, 'no_living_cast': {'type': 'boolean'},
        'no_unwanted_text': {'type': 'boolean'}, 'uncertain': {'type': 'boolean'},
        'evidence': TEXT, 'issues': {'type': 'array', 'items': TEXT},
        'retry_instructions': {'type': 'array', 'items': TEXT}})
    prompt = ('Review IMAGE1 as a canonical picture-book ' + entry['kind'] + ' reference. '
        'IMAGE2 is its approved ' + ('SOURCE GARMENT portrait' if entry['source_character_id'] else 'STYLE reference')
        + '. Check the named subject against its permanent design and actual source. A garment must '
        'match the source garment colour, knit/pattern, construction, slender/wide proportions and '
        'distinctive details, without any wearer pixels. It may naturally untie/unfold. A prop reference '
        'shows the entire ONE inanimate object on a clean simple backdrop. A statue may have a carved '
        'face/body, but must be clearly inanimate stone and match its figure/crown/base specification. '
        'A location reference shows the specified fixed environment with no cast or movable story '
        'props baked in. No living characters, extraneous faces/hands, writing, collages or ambiguity. '
        'STYLE means paint/line technique, texture, palette and lighting treatment, NOT the subject, '
        'geography or whether the scene is indoors/outdoors. A warm gouache interior may correctly '
        'use an outdoor gouache garden as its STYLE example. Never require a room to become a garden '
        'or copy objects, bubbles, statues or layout from a style reference. Different scene content '
        'is expected and is not evidence of a style mismatch. For an object, source style scenery '
        'must also disappear. Compare actual drawing technique and colours only for style_matches. '
        'Ignore harmless paint texture and lighting differences. Reject consequential geometry/design '
        'discrepancies, not imaginary invisible details. Give concrete affirmative corrections.\n'
        + json.dumps(entry, ensure_ascii=False))
    result = generate(project['config']['ollama_url'], project['render_settings']['review_model'],
        prompt, schema, [png, asset_path(project, spec['references'][0]).read_bytes()])
    checks = dict.fromkeys(VISUAL_CHECKS, True)
    checks.update(scene_matches=result['design_matches'], style_matches=result['style_matches'],
        anatomy_sound=result['object_complete'], no_unwanted_text=result['no_unwanted_text'],
        reference_background_ok=result['no_living_cast'])
    report = {'checks': checks, 'characters': [],
        'unexpected_character_count': 0 if result['no_living_cast'] else 1,
        'uncertain': result['uncertain'], 'evidence': result['evidence'], 'issues': result['issues'],
        'retry_instructions': result['retry_instructions'], 'retry_scene': ''}
    return {'accepted': passed(report, []), 'review': report, 'visual_reference_review': result,
            'detections': {}, 'scale_review': None, 'inventory': None}


def review_scene(project, spec, png, generate):
    from .storage import asset_path
    from .visual_library import entries, asset_name
    checks = []
    for entry in entries(project, spec):
        source = asset_path(project, asset_name(entry)).read_bytes()
        schema = obj({'visible': {'type': 'boolean'}, 'same_design': {'type': 'boolean'},
            'uncertain': {'type': 'boolean'}, 'evidence': TEXT,
            'issues': {'type': 'array', 'items': TEXT},
            'retry_instructions': {'type': 'array', 'items': TEXT}})
        prompt = ('Compare ONLY the named recurring ' + entry['kind'] + ' in candidate IMAGE1 '
            'to its canonical design in IMAGE2. Other characters/props are outside this narrow check. '
            'First determine if the subject is actually visible. Presence, the required action and '
            'persistent state are checked separately by the native scene/event/continuity gates. '
            'This pass checks DESIGN ONLY. If absent, same_design=true and no issues; a reference '
            'must never force unseen scenery or a previously used kit into a close-up. If visible, preserve its core '
            'silhouette, material, colour, construction, distinctive details and relative object-part '
            'proportions. A statue must depict the SAME figure, with the SAME crown, pose/construction '
            'and base; a different statue or bust/full-figure substitution fails. A garment remains '
            'the SAME fabric design and plausible dimensions, although it folds, drapes and unties. '
            'Allow cropping, camera angle, foreshortening, painted lighting, natural cloth deformation, '
            'occlusion and explicitly required story-state changes such as honey, damage or contents. '
            'A location preserves recognisable architecture, landmarks/materials and coherent layout, '
            'not an identical camera framing or every flower. Do not hallucinate differences in '
            'hidden parts. For a consequential mismatch identify the visible evidence and give a '
            'specific edit that preserves the rest of the image. No new events or actors.\n'
            + json.dumps({'subject': {k:entry[k] for k in ('id','name','kind','appearance')},
                          'scene': spec['prompt']}, ensure_ascii=False))
        result = generate(project['config']['ollama_url'], project['render_settings']['review_model'],
            prompt, schema, [png, source])
        accepted = not result['uncertain'] and not result['issues'] and result['same_design']
        checks.append({'id': entry['id'], 'kind': entry['kind'], 'scope': 'visible design; presence uses native scene gates',
                       'accepted': accepted, 'review': result})
    return checks


def apply_checks(report, checks):
    for check in checks:
        if check['accepted']:
            continue
        result = check['review']
        report['checks']['scene_matches'] = False
        report['uncertain'] = report['uncertain'] or result['uncertain']
        report['issues'].extend(result['issues'] or [
            'Recurring reference ' + check['id'] + ' is missing or its visual design could not be verified.'])
        report.setdefault('retry_instructions', []).extend(result['retry_instructions'] or [
            'Depict ' + check['id'] + ' with the same design as its canonical reference, preserving the story action.'])

"""Blind, aligned patch review for a removed fastening; no before/after role swap."""
import hashlib
import io
import json
import math
import re

MATERIAL_PROMPT = '''Describe the central visible feature in this ONE magnified patch of clothing.
No story, requested edit or other reference image is supplied. Report only its actual appearance.
A sewing_button is a discrete round solid disc, often with a rim and sewing holes. A button_like_dot
is a compact dark/round solid mark too small or ambiguous to distinguish confidently from a button.
loose_thread consists of fine flexible lines, loops or crossed stitches on continuous fabric, without
a solid disc. plain_cloth is continuous textile with no distinct central object. tear_or_hole is an
actual opening through the textile. Use unclear if evidence is insufficient. Describe shape and
material before choosing. Do not infer that anything was removed or that a requested edit succeeded.
'''


def material_schema():
    from .story import object_schema
    return object_schema({'kind': {'type':'string','enum':['sewing_button','button_like_dot','loose_thread','plain_cloth','tear_or_hole','unclear']},
                          'observed_shape': {'type':'string'}, 'observed_material': {'type':'string'},
                          'uncertain': {'type':'boolean'}})


def classify_material(png, project, generate):
    from .storage import checked_root, write_json
    from .story import digest
    request = {'version':1, 'image_sha256':hashlib.sha256(png).hexdigest(), 'prompt':MATERIAL_PROMPT,
               'schema':material_schema(), 'model':project['render_settings']['review_model']}
    path = checked_root(project) / 'quality' / 'material-observations' / (digest(request)+'.json')
    if path.exists():
        return json.loads(path.read_text())['result']
    result = generate(project['config']['ollama_url'],request['model'],request['prompt'],request['schema'],[png])
    write_json(path, {**request, 'result':result})
    return result


def clear_replacement_material(result):
    return result['uncertain'] is False and result['kind'] in ('plain_cloth','loose_thread')


def review_removed_fastening(project, spec, png, generate):
    from PIL import Image
    from .state_assets import detail_directory, png_bytes
    if spec['kind'] != 'state':
        return None
    checks = []
    image = Image.open(io.BytesIO(png)).convert('RGB')
    for change in spec['changes']:
        if not (re.search(r'\bbuttons?\b',change['part'],re.I)
                and re.search(r'\b(missing|removed|lost|fallen)\b',change['after_state'],re.I)):
            continue
        measurement = json.loads((detail_directory(project,change)/'measurement.json').read_text())
        for index, selected in enumerate(measurement['selected']):
            x0,y0,x1,y1 = selected['bbox']
            pad = max(16,round(max(x1-x0,y1-y0)*.1))
            box = (max(0,math.floor(x0)-pad), max(0,math.floor(y0)-pad),
                   min(image.width,math.ceil(x1)+pad), min(image.height,math.ceil(y1)+pad))
            crop = image.crop(box).resize((512,512),Image.Resampling.LANCZOS)
            result = classify_material(png_bytes(crop),project,generate)
            # This rule verifies absence of an intact fastening, not a new design.
            # Ambiguous dark dots and invented tears cannot stand in for a clear
            # cloth/thread surface. Other changes retain their existing QA path.
            accepted = clear_replacement_material(result)
            checks.append({'change_id':change['id'],'selected_index':index,'crop_box':box,
                           'result':result,'accepted':accepted})
    if not checks:
        return None
    return {'accepted':all(c['accepted'] for c in checks),'patches':checks}


def apply_material_review(report, review):
    if review is None or review['accepted']:
        return
    report['checks']['scene_matches'] = False
    for patch in review['patches']:
        if patch['accepted']:
            continue
        observed = patch['result']
        report['issues'].append(f"{patch['change_id']}: measured replacement patch contains {observed['kind']} "
                               f"({observed['observed_shape']}); clear cloth or loose thread is required.")
        report.setdefault('retry_instructions',[]).append(
            'Paint continuous matching clothing fabric with fine loose sewing threads at the selected fastening position. Preserve every other fastening.')

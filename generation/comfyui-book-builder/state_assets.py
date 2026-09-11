"""Measured, protected costume edits and private detail references."""
import hashlib
import io
import json
import math


def png_bytes(image):
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()


def select_boxes(proposals, selection):
    from .detection import iou
    boxes = []
    for proposal in sorted(proposals, key=lambda p: p['score'], reverse=True):
        if proposal['score'] < .35:
            continue
        box = proposal['bbox']
        if not all(math.isfinite(v) for v in box) or box[2] <= box[0] or box[3] <= box[1]:
            continue
        if not any(iou(box, other['bbox']) > .5 for other in boxes):
            boxes.append(proposal)
    # Grounding DINO sometimes also labels the enclosing waistcoat/body as a
    # button. IoU NMS misses these much larger containers. Keep the stronger
    # measured object inside, not a weaker enclosing box of the same class.
    def contains_weaker_container(outer):
        a = outer['bbox']; area = (a[2]-a[0])*(a[3]-a[1])
        return any(inner is not outer and inner['score'] > outer['score']
                   and area > 4*(inner['bbox'][2]-inner['bbox'][0])*(inner['bbox'][3]-inner['bbox'][1])
                   and a[0] <= inner['bbox'][0] and a[1] <= inner['bbox'][1]
                   and a[2] >= inner['bbox'][2] and a[3] >= inner['bbox'][3] for inner in boxes)
    boxes = [b for b in boxes if not contains_weaker_container(b)]
    if not boxes or (selection == 'single' and len(boxes) != 1):
        raise ValueError('The changed costume part cannot be located unambiguously on its baseline portrait.')
    if selection in ('single', 'all'):
        return boxes
    axis, reverse = {'topmost': (1, False), 'bottommost': (3, True),
                     'leftmost': (0, False), 'rightmost': (2, True)}[selection]
    return [sorted(boxes, key=lambda p: p['bbox'][axis], reverse=reverse)[0]]


def measure_part(png, query):
    # The cast detector already runs locally on CPU and retains multiple same-
    # class proposals. The selected object is measured, never LLM coordinates.
    from .detection import detect_cast
    known, candidates = detect_cast(png, [{'id': 'part', 'appearance': query, 'detection_prompt': query}], True)
    return [*known.values(), *candidates]


def region_mask(size, selected, proposals):
    import numpy as np
    from PIL import Image
    width, height = size
    pixels = np.zeros((height, width), dtype=np.float32)
    for record in selected:
        x0, y0, x1, y1 = record['bbox']
        if min(x0, y0) < 0 or x1 > width or y1 > height or (x1-x0)*(y1-y0) > width*height*.35:
            raise ValueError('Detected edit region is outside the portrait or too broad for a protected local edit.')
        pad = max(16, round(max(x1-x0, y1-y0)*.1))
        left, top = max(0, math.floor(x0)-pad), max(0, math.floor(y0)-pad)
        right, bottom = min(width, math.ceil(x1)+pad), min(height, math.ceil(y1)+pad)
        # Eight-pixel feather is entirely inside the measured padded rectangle.
        yy, xx = np.mgrid[top:bottom, left:right]
        edge = np.minimum.reduce([xx-left+1, right-xx, yy-top+1, bottom-yy])
        pixels[top:bottom, left:right] = np.maximum(pixels[top:bottom, left:right], np.minimum(1, edge/8))
    from .detection import iou
    for other in select_boxes(proposals, 'all'):
        if any(iou(other['bbox'], chosen['bbox']) > .5 for chosen in selected):
            continue
        # Never erase a neighbouring fastening while editing the chosen one.
        x0, y0, x1, y1 = other['bbox']
        pixels[max(0, math.floor(y0)-3):min(height, math.ceil(y1)+3),
               max(0, math.floor(x0)-3):min(width, math.ceil(x1)+3)] = 0
    if not pixels.any() or np.count_nonzero(pixels) > width*height*.45:
        raise ValueError('The protected edit mask is empty or covers too much of the portrait.')
    return Image.fromarray((pixels*255).astype('uint8'), 'L')


def detail_directory(project, change):
    from .storage import checked_root
    return checked_root(project) / 'visual-state' / change['id']


def prepare_details(project):
    from PIL import Image
    from .storage import asset_path, write_json, write_exclusive, valid_asset
    from .story import asset_specs
    from .quality import json_model
    from .state_ledger import obj, is_addition
    specs = {s['name']: s for s in asset_specs(project)}
    edits = {}
    for change in project.get('art_plan', {}).get('ledger', {}).get('changes', []):
        source_name = f"characters/{change['character_id']}.png"
        if not valid_asset(project, specs[source_name]):
            raise ValueError('State variants require an approved baseline: ' + source_name)
        if is_addition(change):
            # No existing cape/hat pixels can be measured before it is added.
            # The native reference edit must pass normal identity/anatomy/style
            # checks AND a separate before/after clothing audit instead.
            continue
        source = asset_path(project, source_name).read_bytes()
        directory = detail_directory(project, change)
        record_path = directory / 'measurement.json'
        if record_path.exists():
            record = json.loads(record_path.read_text())
            if record['source_sha256'] != hashlib.sha256(source).hexdigest() or record['change'] != change:
                raise ValueError('Saved state measurement differs from its immutable source or plan.')
        else:
            proposal_path = directory / 'detector-proposals.json'
            if proposal_path.exists():
                previous = json.loads(proposal_path.read_text())
                if previous['source_sha256'] != hashlib.sha256(source).hexdigest() or previous['change'] != change:
                    raise ValueError('Saved detector proposals differ from the source or state plan.')
                proposals = previous['proposals']
            else:
                proposals = measure_part(source, change['reference_edit']['target_query'])
            selected = select_boxes(proposals, change['reference_edit']['selection'])
            write_json(directory / 'detector-proposals.json', {'proposals': proposals, 'selected': selected,
                       'source_sha256': hashlib.sha256(source).hexdigest(), 'change': change})
            portrait = Image.open(io.BytesIO(source)).convert('RGB')
            mask = region_mask(portrait.size, selected, proposals)
            # Actual pixels, with a small context margin. A crop establishes the
            # prop design; it is never a newly invented generic replacement.
            x0 = max(0, math.floor(min(p['bbox'][0] for p in selected))-5)
            y0 = max(0, math.floor(min(p['bbox'][1] for p in selected))-5)
            x1 = min(portrait.width, math.ceil(max(p['bbox'][2] for p in selected))+5)
            y1 = min(portrait.height, math.ceil(max(p['bbox'][3] for p in selected))+5)
            crop = portrait.crop((x0,y0,x1,y1))
            crop.thumbnail((512,512), Image.Resampling.LANCZOS)
            factor = 512 / max(crop.size)
            crop = crop.resize((round(crop.width*factor), round(crop.height*factor)), Image.Resampling.LANCZOS)
            data, mask_data = png_bytes(crop), png_bytes(mask)
            write_exclusive(directory / 'detail.png', data)
            write_exclusive(directory / 'mask.png', mask_data)
            record = {'source_sha256': hashlib.sha256(source).hexdigest(), 'source_name': source_name,
                      'change': change, 'proposals': proposals, 'selected': selected, 'crop_box': [x0,y0,x1,y1],
                      'detail_sha256': hashlib.sha256(data).hexdigest(), 'mask_sha256': hashlib.sha256(mask_data).hexdigest()}
            write_json(record_path, record)
        for kind in ('detail', 'mask'):
            if hashlib.sha256((directory / f'{kind}.png').read_bytes()).hexdigest() != record[kind+'_sha256']:
                raise ValueError('Saved state-reference pixels changed: ' + kind)
        review_path = directory / 'measurement-review.json'
        if review_path.exists():
            review = json.loads(review_path.read_text())
        else:
            schema = obj({'matches': {'type':'boolean'}, 'description': {'type':'string'},
                          'uncertain': {'type':'boolean'}, 'issues': {'type':'array','items':{'type':'string'}}})
            review = json_model(project['config']['ollama_url'], project['render_settings']['review_model'],
                'Image 1 is the immutable baseline portrait. Image 2 is a magnified measured detail from it. '
                'Check that the crop contains the requested existing item/part and its selected position. '
                'Describe its ACTUAL colour, shape, pattern and any clearly countable identifying marks '
                '(for example sewing holes). Do not invent fine detail; uncertain features must be described '
                'as unresolved. This is a reference-localisation check, not approval of an edited picture. '
                'The crop must match the physical part and surface in this instruction:\n' + json.dumps(change),
                schema, [source, (directory/'detail.png').read_bytes()])
            write_json(review_path, review)
        if not review['matches'] or review['uncertain'] or review['issues']:
            raise ValueError('Costume-detail localisation needs review: ' + str(review_path))
        if project['render_settings'].get('state_edit_policy',1) >= 2:
            from .state_edit import prepare_edit
            edits[change['id']] = prepare_edit(project,change,record,review)
    if project['render_settings'].get('state_edit_policy',1) >= 2:
        from .state_edit import attach_edits
        return attach_edits(project,edits)
    return project


def variant_inputs(project, spec):
    import numpy as np
    from PIL import Image
    from .storage import asset_path
    baseline = asset_path(project, spec['references'][0]).read_bytes()
    portrait = Image.open(io.BytesIO(baseline)).convert('RGB')
    mask = np.zeros((portrait.height, portrait.width), dtype=np.uint8)
    for change in spec['changes']:
        directory = detail_directory(project, change)
        record = json.loads((directory/'measurement.json').read_text())
        if record['source_sha256'] != hashlib.sha256(baseline).hexdigest():
            raise ValueError('Protected state edit source changed.')
        data = (directory/'mask.png').read_bytes()
        if hashlib.sha256(data).hexdigest() != record['mask_sha256']:
            raise ValueError('Protected state edit mask changed.')
        mask = np.maximum(mask, np.asarray(Image.open(io.BytesIO(data)).convert('L')))
    return portrait, Image.fromarray(mask, 'L')


def outside_pixels_unchanged(project, spec, png):
    import numpy as np
    from PIL import Image
    before, mask = variant_inputs(project, spec)
    after = Image.open(io.BytesIO(png)).convert('RGB')
    return (after.size == before.size
            and not np.any(np.any(np.asarray(before) != np.asarray(after), axis=2)[np.asarray(mask) == 0]))


def scene_props(project, scene):
    from .state_ledger import scene_requirements
    wanted = scene_requirements(project, scene)['props']
    return [p for p in project.get('art_plan', {}).get('ledger', {}).get('detached_props', []) if p['id'] in wanted]


def prop_reference(project, prop):
    change = next(c for c in project['art_plan']['ledger']['changes'] if c['id'] == prop['source_change_id'])
    from .state_ledger import is_addition
    if is_addition(change):
        from .story import asset_specs
        from .storage import asset_path, valid_asset
        choices = [s for s in asset_specs(project) if s['kind']=='state'
                   and any(c['id']==change['id'] for c in s['changes'])]
        # Prefer the simplest already approved view containing the garment.
        choices.sort(key=lambda s:len(s['changes']))
        spec = next((s for s in choices if valid_asset(project,s)),None)
        if spec is None:
            raise ValueError('A detached added garment needs its approved worn reference first.')
        return (asset_path(project,spec['name']).read_bytes(),
                prop['description'] + '. This is the approved worn design on the SAME character. '
                'Compare ONLY the garment as a detached object in the candidate, not the reference body or pose.')
    directory = detail_directory(project, change)
    record = json.loads((directory/'measurement.json').read_text())
    data = (directory/'detail.png').read_bytes()
    if hashlib.sha256(data).hexdigest() != record['detail_sha256']:
        raise ValueError('Detached prop reference no longer matches its measured origin.')
    review = json.loads((directory/'measurement-review.json').read_text())
    if review['matches'] is not True or review['uncertain'] or review['issues']:
        raise ValueError('Detached prop lacks a valid source-detail review.')
    return data, review['description']

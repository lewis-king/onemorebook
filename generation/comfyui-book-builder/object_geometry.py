"""Blind local boundary checks before comparing persistent object dimensions."""
import io
import json
import math
import hashlib
from pathlib import Path

from .story import digest, object_schema as obj

VERSION = 1


def proposals(png, phrases):
    """Keep nested detections: ordinary cross-class NMS destroys containment."""
    import folder_paths
    import torch
    from PIL import Image
    from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
    path = Path(folder_paths.models_dir) / 'grounding-dino-tiny'
    if not (path / 'model.safetensors').is_file():
        raise ValueError('Object scale checks require the existing local grounding-dino-tiny model.')
    image = Image.open(io.BytesIO(png)).convert('RGB')
    previous = torch.get_num_threads()
    try:
        torch.set_num_threads(min(previous, 8))
        processor = AutoProcessor.from_pretrained(path, local_files_only=True)
        model = AutoModelForZeroShotObjectDetection.from_pretrained(path, local_files_only=True).to('cpu').eval()
        query = ' '.join(p.strip().rstrip('.') + '.' for p in phrases)
        inputs = processor(images=image, text=query, return_tensors='pt')
        with torch.inference_mode():
            raw = model(**inputs)
        found = processor.post_process_grounded_object_detection(raw, inputs.input_ids,
            threshold=.25, text_threshold=.18, target_sizes=[image.size[::-1]])[0]
        return [{'bbox': b, 'score': s, 'label': label} for b, s, label in zip(
            found['boxes'].tolist(), found['scores'].tolist(), found['text_labels'])]
    finally:
        torch.set_num_threads(previous)


def audit_schema():
    return obj({'subjects': {'type': 'array', 'minItems': 2, 'maxItems': 2, 'items': obj({
        'id': {'type': 'string', 'enum': ['inner', 'outer']}, 'present': {'type': 'boolean'},
        'box_index': {'type': 'integer', 'minimum': -1}, 'box_tight': {'type': 'boolean'},
        'outline_complete': {'type': 'boolean'}, 'deformed': {'type': 'boolean'},
        'evidence': {'type': 'string'}})}, 'contained': {'type': 'boolean'},
        'shared_depth': {'type': 'boolean'}, 'uncertain': {'type': 'boolean'},
        'evidence': {'type': 'string'}})


def measured_ratio(boxes, audit, size):
    subjects = {s['id']: s for s in audit['subjects']}
    if (set(subjects) != {'inner', 'outer'} or audit['uncertain'] or not audit['contained']
            or not audit['shared_depth']):
        return None
    indices = [s['box_index'] for s in subjects.values()]
    if len(set(indices)) != 2:
        return None
    dimensions = {}
    selected = {}
    for key, subject in subjects.items():
        i = subject['box_index']
        if (not all(subject[k] for k in ('present', 'box_tight', 'outline_complete'))
                or subject['deformed'] or not isinstance(i, int) or not 0 <= i < len(boxes)):
            return None
        b = boxes[i]['bbox']
        if (len(b) != 4 or not all(math.isfinite(v) for v in b)
                or not 0 <= b[0] < b[2] <= size[0] or not 0 <= b[1] < b[3] <= size[1]):
            return None
        selected[key] = b
        dimensions[key] = ((b[2]-b[0]) + (b[3]-b[1])) / 2
    inner, outer = selected['inner'], selected['outer']
    # A visually asserted containment cannot rescue reversed/wrong boxes.
    margin = .03 * max(outer[2]-outer[0], outer[3]-outer[1])
    if any((inner[0] < outer[0]-margin, inner[1] < outer[1]-margin,
            inner[2] > outer[2]+margin, inner[3] > outer[3]+margin)):
        return None
    ratio = dimensions['inner'] / dimensions['outer']
    if not 0 < ratio < 1:
        return None
    return ratio


def verdict(ratio, target, tolerance=.25):
    if ratio is None:
        return {'status': 'unmeasurable', 'accepted': None}
    # Allow modest boundary uncertainty as well as illustration variation.
    interval = [ratio*.96/1.04, ratio*1.04/.96]
    acceptable = [target*(1-tolerance), target*(1+tolerance)]
    decisive = interval[1] < acceptable[0] or interval[0] > acceptable[1]
    return {'status': 'mismatch' if decisive else 'consistent', 'accepted': not decisive,
        'observed_ratio': ratio, 'measurement_interval': interval,
        'target_ratio': target, 'acceptable_interval': acceptable}


def measure(project, png, inner, outer, generate, detect=proposals):
    from PIL import Image, ImageDraw, ImageFont
    from .storage import write_json, write_exclusive
    model = project['render_settings']['review_model']
    source_hash = hashlib.sha256(png).hexdigest()
    key = digest([VERSION, source_hash, inner, outer, model])
    root = Path(project['book_root']) / 'object-geometry' / key[:20]
    saved = root / 'measurement.json'
    if saved.exists():
        return json.loads(saved.read_text())
    bp = root / 'proposals.json'
    boxes = json.loads(bp.read_text()) if bp.exists() else detect(png, [inner, outer])
    write_json(bp, boxes)
    image = Image.open(io.BytesIO(png)).convert('RGB')
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 24)
    except OSError:
        font = ImageFont.load_default()
    for index, box in enumerate(boxes):
        color = ['#0066ff', '#ff0066', '#009933', '#aa00cc'][index % 4]
        draw.rectangle(box['bbox'], outline=color, width=3)
        x, y = box['bbox'][:2]
        draw.rectangle((x, y, x+36, y+32), fill='white')
        draw.text((x+4, y+1), str(index), font=font, fill=color)
    buf = io.BytesIO(); image.save(buf, format='PNG'); overlay = buf.getvalue()
    write_exclusive(root / 'boxes.png', overlay)
    prompt = ('Inspect ORIGINAL artwork IMAGE1. IMAGE2 is a numbered bounding-box overlay. '
        'Independently identify inner subject: ' + inner + '; outer container: ' + outer + '. '
        'Detector labels are fallible proposals. Do not invent missing objects, confuse reflections '
        'with opaque contents, or mistake an inner highlight ring for a transparent container boundary. '
        'Select one box per actual subject only when its edges tightly bound the OUTERMOST visible '
        'top, bottom, left and right extrema. Rectangular boxes naturally contain background or '
        'neighbouring pixels in their corners; that alone does NOT make a box too large. A box is '
        'too large when an edge extends past the subject extrema to include an adjacent object. '
        'If absent or no adequate proposal, use box_index=-1. Confirm full visible outlines, actual '
        'containment, shared depth and whether squeezed/deformed. Normal spherical shading is not '
        'deformation. Do not infer hidden bounds through opaque occlusion, extrapolate a crop, '
        'assess intended proportions or calculate a ratio. Describe visible boundaries only.\n'
        + json.dumps(boxes))
    schema = audit_schema()
    write_json(root / 'request.json', {'prompt': prompt, 'schema': schema, 'model': model,
        'source_hash': source_hash, 'inner': inner, 'outer': outer})
    audit = generate(project['config']['ollama_url'], model, prompt, schema, [png, overlay])
    write_json(root / 'audit.json', audit)
    value = {'version': VERSION, 'source_hash': source_hash, 'audit': audit, 'boxes': boxes,
        'ratio': measured_ratio(boxes, audit, image.size), 'evidence_dir': str(root)}
    write_json(saved, value)
    return value

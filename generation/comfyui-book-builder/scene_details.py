"""Evidence-only extra-fastening veto. A matching count never approves artwork."""
import hashlib
import io
import json
import math
import re

from .material import MATERIAL_PROMPT, material_schema

DETAIL_PROMPT = MATERIAL_PROMPT + '''
Also identify what immediately supports the central object: garment_fabric when it visibly
rests on the clothing textile; hand_or_paw when fingers/paws hold it; other for another
visible support; unclear when the crop does not establish this. Describe the surrounding
support before choosing. Do not infer attachment from the object's name or a requested count.
'''


def detail_schema():
    schema = material_schema()
    schema['properties'].update({
        'support_surface': {'type':'string','enum':['garment_fabric','hand_or_paw','other','unclear']},
        'support_evidence': {'type':'string','minLength':1}})
    schema['required'].extend(('support_surface','support_evidence'))
    return schema


def object_proposals(proposals, size):
    """Higher recall than portrait mask selection; every object needs material QA."""
    from .detection import iou
    width,height = size
    selected = []
    for obj in sorted(proposals,key=lambda x:x['score'],reverse=True):
        a,b,c,d = obj['bbox']
        if (not all(math.isfinite(v) for v in (a,b,c,d)) or obj['score'] < .25
                or a < 0 or b < 0 or c > width or d > height or c <= a or d <= b
                or (c-a)*(d-b) > width*height*.45):
            continue
        if not any(iou(obj['bbox'],old['bbox']) > .5 for old in selected):
            selected.append(obj)
    return selected


def crop_box(box, size, pad):
    a,b,c,d = box
    return (max(0,math.floor(a)-pad),max(0,math.floor(b)-pad),
            min(size[0],math.ceil(c)+pad),min(size[1],math.ceil(d)+pad))


def garment_query(actor, garment):
    """Use an explicitly stated local clothing colour, never a nearby fur colour."""
    appearance = actor['appearance'].lower()
    match = re.search(r'\b'+re.escape(garment)+r'\b',appearance)
    if not match:
        return garment
    clause = re.split(r'[,.;]|\band\b',appearance[:match.start()])[-1]
    colour = re.search(r'\b(red|blue|green|yellow|orange|purple|pink|white|black|grey|gray|brown|cream|navy|teal|turquoise)'
        r'(?:\s+(?:buttoned|hooded|woollen|woolen|sleeveless|knitted|long|short|silk|cotton|denim|striped|spotted)){0,3}\s*$',clause)
    return colour[1]+' '+garment if colour else garment


def measure_objects(png, actor, visible_cast, garment):
    from PIL import Image
    from .detection import detect_cast
    from .state_assets import measure_part, select_boxes, png_bytes
    image = Image.open(io.BytesIO(png)).convert('RGB')
    actors = detect_cast(png,visible_cast)
    record = {'actor_detections':actors,'status':'unresolved','objects':[]}
    if actor['id'] not in actors:
        return record, []
    actor_box = crop_box(actors[actor['id']]['bbox'],image.size,8)
    actor_image = image.crop(actor_box)
    garments = measure_part(png_bytes(actor_image),'a '+garment+'.')
    record.update(actor_crop_box=actor_box,garment_proposals=garments)
    try:
        selected = select_boxes(garments,'single')[0]
        a,b,c,d = selected['bbox']
        if (c-a)*(d-b) > actor_image.width*actor_image.height*.75:
            return record, []
    except ValueError:
        return record, []
    garment_box = crop_box(selected['bbox'],actor_image.size,6)
    garment_image = actor_image.crop(garment_box)
    proposals = measure_part(png_bytes(garment_image),'a round sewing button.')
    records, crops = [], []
    for obj in object_proposals(proposals,garment_image.size):
        a,b,c,d = obj['bbox']
        pad = max(6,round(max(c-a,d-b)*.3))
        patch = crop_box(obj['bbox'],garment_image.size,pad)
        dx,dy = actor_box[0]+garment_box[0],actor_box[1]+garment_box[1]
        records.append({'proposal':obj,'crop_within_garment':patch,
                        'bbox_in_scene':[a+dx,b+dy,c+dx,d+dy]})
        crops.append(png_bytes(garment_image.crop(patch).resize((512,512),Image.Resampling.LANCZOS)))
    record.update(status='observed',garment_crop_within_actor=garment_box,
                  button_proposals=proposals,objects=records)
    return record,crops


def observe_objects(project, png, actor, visible_cast, garment, generate):
    from .storage import checked_root, write_json, write_exclusive
    from .story import digest
    request = {'version':2,'source_sha256':hashlib.sha256(png).hexdigest(),
               'actor':actor,'visible_cast':visible_cast,'garment':garment,
               'detector':project['render_settings'].get('model_files',{}).get('object_detector'),
               'prompt':DETAIL_PROMPT,'schema':detail_schema(),
               'model':project['render_settings']['review_model']}
    directory = checked_root(project)/'quality'/'scene-fastening-observations'/digest(request)
    path = directory/'observation.json'
    if path.exists():
        return json.loads(path.read_text())['observation']
    measured,crops = measure_objects(png,actor,visible_cast,garment)
    directory.mkdir(parents=True,exist_ok=True)
    for index,(item,crop) in enumerate(zip(measured['objects'],crops)):
        write_exclusive(directory/f'object-{index:02}.png',crop)
        observation_path = directory/f'object-{index:02}.json'
        image_hash = hashlib.sha256(crop).hexdigest()
        if observation_path.exists():
            saved = json.loads(observation_path.read_text())
            if saved['image_sha256'] != image_hash:
                raise ValueError('Saved detail observation differs from its measured crop.')
            result = saved['result']
        else:
            result = generate(project['config']['ollama_url'],request['model'],request['prompt'],request['schema'],[crop])
            write_json(observation_path,{'image_sha256':image_hash,'result':result})
        item.update(image_sha256=image_hash,result=result)
    write_json(path,{**request,'observation':measured})
    return measured


def remaining_inventory(project, change):
    """Use original measured objects/removal, never an LLM's requested count."""
    from .storage import asset_path
    from .state_assets import detail_directory, select_boxes
    from .detection import iou
    directory = detail_directory(project,change)
    record = json.loads((directory/'measurement.json').read_text())
    if (record['change'] != change or record['source_sha256'] != hashlib.sha256(
            asset_path(project,record['source_name']).read_bytes()).hexdigest()):
        raise ValueError('Original fastening measurement changed.')
    review = json.loads((directory/'measurement-review.json').read_text())
    if not review['matches'] or review['uncertain'] or review['issues']:
        raise ValueError('Original fastening measurement was not verified.')
    original = select_boxes(record['proposals'],'all')
    removed = record['selected']
    matched = [{i for i,o in enumerate(original) if iou(r['bbox'],o['bbox']) > .5} for r in removed]
    if not matched or any(len(m) != 1 for m in matched) or len(set.union(*matched)) != len(removed):
        raise ValueError('Selected removals do not map uniquely to the original measured fastenings.')
    return {'original':len(original),'removed':len(removed),'remaining':len(original)-len(removed),
            'baseline_sha256':record['source_sha256']}


def confirmed_attached(item):
    r = item['result']
    return r['kind'] == 'sewing_button' and r['uncertain'] is False and r['support_surface'] == 'garment_fabric'


def review_scene_fastening_inventory(project, spec, png, generate):
    from .state_ledger import active_changes
    from .state_edit import restore_cloth_before_edit
    if spec['kind'] != 'scene' or not project.get('art_plan'):
        return None
    scene = project['book']['cover'] if spec['name'] == 'cover.png' else next(
        p for p in project['book']['pages'] if spec['name'] == f"pages/page-{p['page_number']:03d}.png")
    cast = [c for c in project['book']['characters'] if c['id'] in scene['character_ids']]
    changes = [c for c in active_changes(project,scene) if restore_cloth_before_edit(c)]
    items = []
    for change in changes:
        # Combined removals need a union of baseline measurements. Until that is
        # calibrated, retain the existing state audit rather than invent a count.
        if sum(c['character_id'] == change['character_id'] for c in changes) != 1:
            continue
        garment = re.search(r'\b(waistcoat|coat|shirt|dress|jacket|cardigan|vest)\b',
                            change['part']+' '+change['surface'],re.I)
        if not garment:
            continue
        actor = next(c for c in cast if c['id'] == change['character_id'])
        inventory = remaining_inventory(project,change)
        observed = observe_objects(project,png,actor,cast,garment_query(actor,garment[1].lower()),generate)
        confirmed = [o for o in observed['objects'] if confirmed_attached(o)]
        items.append({'change_id':change['id'],'character_id':actor['id'],'inventory':inventory,
                      'observation':observed,'confirmed_attached_count':len(confirmed),
                      'excess_visible':len(confirmed) > inventory['remaining']})
    return {'excess_visible':any(i['excess_visible'] for i in items),'items':items,
            'scope':'Extra-object veto only; a low/matching count is not proof of correct or fully visible state.'} if items else None


def apply_scene_fastening_review(report, review):
    if not review or not review['excess_visible']:
        return
    report['checks']['scene_matches'] = False
    for item in review['items']:
        if item['excess_visible']:
            report['issues'].append(f"{item['character_id']}: magnified clothing patches confirm "
                f"{item['confirmed_attached_count']} attached solid buttons; the measured current inventory "
                f"allows {item['inventory']['remaining']}.")
            report.setdefault('retry_instructions',[]).append(
                f"Preserve {item['character_id']}'s current reference: exactly {item['inventory']['remaining']} "
                "intact attached buttons, with continuous matching cloth and fine loose thread at the removed fastening.")

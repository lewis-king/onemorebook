"""Saved, source-specific descriptions of the material replacing a changed detail."""
import copy
import hashlib
import json
import re


def prepare_edit(project, change, measurement, detail_review, generate=None):
    from .quality import json_model
    from .state_assets import select_boxes, detail_directory
    from .state_ledger import obj
    from .storage import asset_path, write_json
    from .story import digest
    generate = generate or json_model
    character = next(c for c in project['book']['characters'] if c['id']==change['character_id'])
    evidence = {'change':change,'character':character,'actual_detail':detail_review['description'],
                'detected_objects':select_boxes(measurement['proposals'],'all'),
                'selected_objects':measurement['selected'],
                'story_evidence':[p['text'] for p in project['story']['pages']
                                  if any(e['pageNumber']==p['pageNumber'] for e in change['evidence'])]}
    schema = obj({'desired_region':{'type':'string'},'preserved_features':{'type':'string'},
                  'inventory_after':{'type':'string'},'evidence':{'type':'string'},'uncertain':{'type':'boolean'}})
    prompt = '''Describe the final MATERIAL/SURFACE to paint inside one protected local edit region.
Image 1 is the unchanged baseline portrait; Image 2 is a magnified detail of the selected part.
The rest of the portrait will be copied pixel-for-pixel, so preserve the existing pose and design.
The supplied state change is a story event. Describe what is visibly PRESENT in the final region,
affirmatively, in concrete colours, materials and texture. A command such as "remove the button"
or a vague "gap" keeps regenerating a button-shaped mark. Do not use absence/negation wording in
desired_region. When a sewn button falls off, the resulting surface is the same surrounding cloth
with tiny loose sewing threads; that does not imply a torn fabric hole unless the story says so.
A hat taken off reveals the character's already-established hair/head. A stain adds its actual
colour to the SAME existing material. Choose the appropriate physical result for THIS event.
Never invent an unrelated change, repair, prop or injury. Keep language concise and factual.
State preserved_features separately, including the other measured objects. Derive inventory_after
from the measured baseline and the SINGLE selected part; don't erase all buttons when only one
falls off. Describe remaining items by location. Evidence explains how the story and actual source
support this material; uncertain=true if a necessary replacement feature is unknown.
''' + json.dumps(evidence)
    directory = detail_directory(project,change)
    source = asset_path(project,measurement['source_name']).read_bytes()
    detail = (directory/'detail.png').read_bytes()
    request = {'prompt':prompt,'schema':schema,'model':project['render_settings']['review_model'],
               'source_sha256':hashlib.sha256(source).hexdigest(), 'detail_sha256':hashlib.sha256(detail).hexdigest()}
    path = directory/'edit-plan.json'
    if path.exists():
        record = json.loads(path.read_text())
        if record['request_hash'] != digest(request):
            raise ValueError('Saved material plan does not match the measured source/settings.')
    else:
        result = generate(project['config']['ollama_url'],request['model'],prompt,schema,[source,detail])
        record = {'request_hash':digest(request),'request':request,'result':result}
        write_json(path,record)
    if record['result']['uncertain']:
        raise ValueError('Replacement material is uncertain: '+str(path))
    return {'plan':record['result'],'hash':digest(record),'source_sha256':request['source_sha256']}


def attach_edits(project, edits):
    from .storage import checked_root, write_json
    from .story import asset_specs
    prepared = copy.deepcopy(project)
    prepared['state_edits'] = edits
    root = checked_root(prepared)
    # A resumed run may change retry decisions while keeping every canonical
    # generation input identical. Preserve that immutable checkpoint and save
    # the runtime policy separately; the returned project retains the policy.
    snapshot = {k: v for k, v in prepared.items() if k != 'runtime_retry_policy'}
    write_json(root/'prepared-state-project.json',snapshot)
    if prepared.get('runtime_retry_policy'):
        from .story import digest
        policy = prepared['runtime_retry_policy']
        write_json(root/'retry-policies'/f'{digest(policy)}.json',policy)
    write_json(root/'prepared-state-asset-plan.json',asset_specs(prepared))
    return prepared


def restore_cloth_before_edit(change):
    # This preparation only removes small fastenings from an existing cloth
    # surface. It cannot invent the anatomy hidden under a removed hat or shoe.
    return bool(re.search(r'\bbuttons?\b',change['part'],re.I)
                and re.search(r'\b(missing|removed|lost|fallen)\b',change['after_state'],re.I))


def edit_prompt(spec):
    pieces = ['Edit only the measured fastening/part regions of this same portrait.']
    for edit in spec['edits']:
        plan = edit['plan']
        pieces += ['Final visible region: '+plan['desired_region'],
                   'Preserve exactly: '+plan['preserved_features'], 'Final inventory: '+plan['inventory_after']]
    pieces.append('Preserve all other character pixels, the pale background and established painted texture.')
    return ' '.join(pieces)

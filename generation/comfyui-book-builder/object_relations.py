"""Private, time-bounded physical contents; never changes the public story JSON."""
import json
from pathlib import Path
from .story import digest, object_schema as obj

VERSION = 1
TEXT = {'type':'string','minLength':1}


def compile_relations(project, model, generate=None):
    from .quality import json_model
    from .storage import write_json
    import jsonschema
    generate = generate or json_model
    objects = project.get('scene_contract',{}).get('objects',[])
    ids = [o['id'] for o in objects]
    source = {'pages':project['story']['pages'], 'objects':objects,
              'facts':project.get('scene_contract',{}).get('persistent_facts',[])}
    key=digest([VERSION,source,model])
    root=Path(project['book_root'])/'object-relations'/key[:16]
    approved=root/'approved.json'
    if approved.exists():
        value=json.loads(approved.read_text())
        if value.get('source_hash')!=key or value.get('relations_hash')!=digest(value.get('relations')):
            raise ValueError('Saved object relationship provenance mismatch.')
        return value
    if len(ids)<2:
        return {'version':VERSION,'source_hash':key,'relations':[], 'relations_hash':digest([])}
    relation=obj({'id':TEXT,'content_id':{'type':'string','enum':ids},
        'container_id':{'type':'string','enum':ids},
        'from_page':{'type':'integer','minimum':1,'maximum':len(source['pages'])},
        'through_page':{'type':'integer','minimum':1,'maximum':len(source['pages'])},
        'source_evidence':TEXT})
    schema=obj({'relations':{'type':'array','maxItems':12,'items':relation}})
    audit_schema=obj({'correct_contents':{'type':'boolean'},'correct_intervals':{'type':'boolean'},
        'complete':{'type':'boolean'},'uncertain':{'type':'boolean'},'issues':{'type':'array','items':TEXT},'evidence':TEXT})
    request=('Extract persistent PHYSICAL CONTENTS into typed relationships: one existing object remains '
        'inside another existing object/cavity across story pages. Use only supplied object IDs. Exclude '
        'clothes worn on bodies, contact/attachments, objects resting ON supports and imaginary/metaphorical '
        'contents. A bubble containing a ball qualifies; a scarf worn by an animal does not. '
        'Give the inclusive page interval where the content remains inside. Read prose and the chosen '
        'illustration moment together for insertion/removal transition pages. Do not continue containment '
        'after retrieval, emptying, disappearance or destruction. Do not require drawing contents through '
        'opaque walls: this relation preserves physical state when the relevant interior is shown. '
        'Cite the actual introduction and removal/end evidence. Return an empty list when no containment '
        'is established.\n'+json.dumps(source,ensure_ascii=False))
    for attempt in (1,2):
        draft_path=root/f'draft-{attempt}.json'
        write_json(root/f'request-{attempt}.json',{'prompt':request,'schema':schema,'model':model})
        draft=json.loads(draft_path.read_text()) if draft_path.exists() else generate(
            project['config']['ollama_url'],model,request,schema)
        jsonschema.validate(draft,schema);write_json(draft_path,draft)
        structural = (len({r['id'] for r in draft['relations']})==len(draft['relations'])
            and all(r['content_id']!=r['container_id'] and r['from_page']<=r['through_page'] for r in draft['relations']))
        audit_path=root/f'review-{attempt}.json'
        audit_prompt=('Independently check the typed physical contents against the story. Verify the '
            'contained object and container, introduction/removal intervals, and missing recurring '
            'containment. Check the chosen illustrated moment on transition pages. Objects ON a support '
            'and worn clothes are not contents. Never extend an interval merely to make all pages match.\n'
            +json.dumps({'source':source,'candidate':draft},ensure_ascii=False))
        write_json(root/f'review-request-{attempt}.json',{'prompt':audit_prompt,'schema':audit_schema,'model':model})
        audit=json.loads(audit_path.read_text()) if audit_path.exists() else generate(
            project['config']['ollama_url'],model,audit_prompt,audit_schema)
        jsonschema.validate(audit,audit_schema);write_json(audit_path,audit)
        if structural and all(audit[k] for k in ('correct_contents','correct_intervals','complete')) and not audit['uncertain'] and not audit['issues']:
            result={'version':VERSION,'source_hash':key,'model':model,**draft,
                    'relations_hash':digest(draft['relations']),'review':audit}
            write_json(approved,result);return result
        request+='\nCorrect this draft without changing the story: '+json.dumps({'draft':draft,'audit':audit,'structural_valid':structural})
    raise ValueError('Physical contents plan did not pass; saved its reports before rendering.')


def active(project, name):
    from .scene_contract import scene_page_number
    number=scene_page_number(project,name)
    if number is None:return []
    return [r for r in project.get('object_relations',{}).get('relations',[])
            if r['from_page']<=number<=r['through_page']]


def inspect_contents(project,spec,png,generate):
    relations=active(project,spec['name'])
    if not relations:return {'accepted':True,'items':[],'issues':[],'retry_instructions':[],'uncertain':False}
    objects={o['id']:o for o in project['scene_contract']['objects']}
    wanted=[{'id':r['id'],'container':objects[r['container_id']]['name'],
             'content':objects[r['content_id']]['name']} for r in relations]
    schema=obj({'items':{'type':'array','items':obj({'id':{'type':'string','enum':[r['id'] for r in relations]},
        'interior':{'type':'string','enum':['not_visible','occupied','visibly_empty','unclear']},
        'expected_content':{'type':'string','enum':['visible','physically_occluded','absent','unclear']},
        'occluding_surface':{'type':'string'},'observation':TEXT})}})
    prompt=('Observe these container/cavity interiors in IMAGE1. Report what is actually drawn, not '
        'what the story would like. not_visible means the opening/interior is offscreen or hidden by '
        'an opaque surface. visibly_empty means the relevant visible interior has no contents. occupied '
        'requires visible contents. Identify whether the named content itself is visible, physically '
        'occluded by a SPECIFIC visible surface, absent, or unclear. Name the actual blocking surface '
        'for physical occlusion; do not invent an unseen deeper pocket or offscreen explanation for '
        'a visibly empty opening. Tiny painted highlights alone are not identifiable contents. '
        'Each image may be correct or defective. No pass/fail judgement is requested: return visual '
        'observations, one per relationship ID.\n'+json.dumps(wanted))
    raw=generate(project['config']['ollama_url'],project['render_settings']['review_model'],prompt,schema,[png])
    complete=sorted(x['id'] for x in raw['items'])==sorted(x['id'] for x in relations)
    issues=[];retry=[];uncertain=not complete
    for item in raw['items']:
        hidden=(item['expected_content']=='physically_occluded' and bool(item['occluding_surface'].strip()))
        ok=(item['interior']=='not_visible' or item['expected_content']=='visible' or
            (item['interior']!='visibly_empty' and hidden))
        if item['interior']=='visibly_empty':ok=False
        if item['interior']=='unclear' or (item['interior']!='not_visible' and item['expected_content']=='unclear'):
            uncertain=True;ok=False
        if not ok:
            detail=next(r for r in wanted if r['id']==item['id'])
            issues.append(item['id']+': '+item['observation'])
            retry.append(f"Show the established {detail['content']} inside the visible {detail['container']}, at its canonical size.")
    if not complete:issues.append('Contents inspection omitted or duplicated a relationship.')
    return {**raw,'accepted':not issues and not uncertain,'issues':issues,'retry_instructions':retry,'uncertain':uncertain}

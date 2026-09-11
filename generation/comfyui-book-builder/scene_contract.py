"""Private whole-story prop continuity and evidence-based QA.

The public story is never edited. The local prop plan is saved and
independently checked before it can influence rendering or visual approval.
Approved original page briefs are preserved.
"""
import json
from pathlib import Path
from .story import digest, object_schema as obj

VERSION = 12
TEXT = {'type': 'string', 'minLength': 1}
STRINGS = {'type': 'array', 'uniqueItems': True, 'items': TEXT}


def coverage_request(project, value, requirements):
    schema=obj({'coverage':{'type':'array','items':obj({
        'requirement_id':{'type':'string','enum':[r['id'] for r in requirements] or ['none']},
        'fact_ids':{'type':'array','uniqueItems':True,'items':{
            'type':'string','enum':[f['id'] for f in value['persistent_facts']] or ['none']}},
        'covered':{'type':'boolean'},'evidence':TEXT})}})
    prompt=('Check each independently extracted prose requirement against the candidate persistent facts. '
        'Return exactly one record per requirement ID. Only cite fact IDs that actually enforce that '
        'specific relationship and its necessary page range. A rule about an object being stuck to a '
        'support does NOT enforce contents inside it; do not assume unstated contents from the prose. '
        'An empty fact_ids list means covered=false. Similar object names alone do not establish coverage. '
        'Account for conditional visibility: facts may allow an object offscreen, while preserving its '
        'state IF shown.\n'+json.dumps({'required_by_prose':requirements,
            'candidate_facts':value['persistent_facts']},ensure_ascii=False))
    return prompt,schema


def coverage_issues(report, requirements, value):
    rows=report['coverage'];known={f['id'] for f in value['persistent_facts']}
    issues=[]
    if sorted(r['requirement_id'] for r in rows)!=sorted(r['id'] for r in requirements):
        issues.append('Coverage audit omitted or duplicated a required prose fact.')
    for row in rows:
        if not row['covered'] or not row['fact_ids'] or not set(row['fact_ids'])<=known:
            issues.append('Uncovered critical prose fact '+row['requirement_id']+': '+row['evidence'])
    return issues


def source_context(project):
    return {'story': project['story'], 'cast': project['book']['characters'],
            'costume_ledger': project.get('art_plan', {}).get('ledger', {})}


def catalogue_schema(project):
    return obj({'objects': {'type': 'array', 'maxItems': 12, 'items': obj({
        'id': {'type': 'string', 'pattern': '^[a-z][a-z0-9_]*$'}, 'name': TEXT,
        'appearance': TEXT
    })}, 'persistent_facts': {'type':'array', 'maxItems':8, 'items':obj({
        'id': {'type':'string','pattern':'^[a-z][a-z0-9_]*$'},
        'object_ids': STRINGS, 'requirement':TEXT,
        'from_page': {'type':'integer','minimum':1}, 'through_page':{'type':'integer','minimum':1},
        'source_pages': {'type':'array','minItems':1,'uniqueItems':True,'items':{'type':'integer','minimum':1}},
        'visibility': {'type':'string','enum':['conditional','absent']}
    })}})


def compile_contract(project, model, generate=None):
    from .quality import json_model
    from .storage import write_json
    import jsonschema
    generate = generate or json_model
    sampling=({'temperature':0.7,'top_p':0.8,'top_k':20,'min_p':0.0,
               'presence_penalty':1.5,'repeat_penalty':1.0} if 'qwen3.5' in model.lower() else {})
    raw_generate=generate
    if sampling:
        def generate(*args, **kwargs):
            return raw_generate(*args, **kwargs, sampling=sampling)
    context = source_context(project)
    key = digest([VERSION, context, model])
    root = Path(project['book_root']) / 'scene-continuity' / key[:16]
    root.mkdir(parents=True, exist_ok=True)
    approved = root / 'approved.json'
    if approved.exists():
        saved = json.loads(approved.read_text())
        if saved.get('source_hash') != key:
            raise ValueError('Saved scene continuity source changed.')
        return saved
    audit_schema = obj({'valid': {'type': 'boolean'}, 'uncertain': {'type': 'boolean'},
                        'issues': {'type': 'array', 'items': TEXT}, 'evidence': TEXT})
    # Observe necessary continuity before showing a candidate plan. Otherwise
    # a reviewer can rubber-stamp a plausible list that omits the central rule.
    requirements_path=root/'independent-prose-requirements.json'
    requirements_item=obj({
        'id':{'type':'string','pattern':'^[a-z][a-z0-9_]*$'},
        'requirement':TEXT,
        'source_pages':{'type':'array','minItems':1,'uniqueItems':True,
                        'items':{'type':'integer','enum':[p['pageNumber'] for p in project['story']['pages']]}}
    })
    requirements_schema=obj({'requirements':{'type':'array','maxItems':10,'items':requirements_item}})
    requirements_prompt=('Read only this complete prose and independently list the few essential '
        'PERSISTENT PROP relationships/states that illustrations must preserve across pages. Trace '
        'the problem object, contents trapped inside another object, damage/attachments, and the '
        'resolved ending. State the necessary page range in each requirement. Conditional visibility '
        'is allowed: an object may be offscreen while its state must remain correct IF depicted. '
        'Do not include clothing, body states or detached-garment states (a separate ledger handles '
        'ALL of those), incidental '
        'decorations, invented action, or one-off poses handled by individual page briefs. For a '
        'story with no such prop continuity, return an empty list. Cite actual prose pages.\n'
        +json.dumps([{'pageNumber':p['pageNumber'],'text':p['text']} for p in project['story']['pages']],ensure_ascii=False))
    requirements_prompt += ('\nScope this independent inventory to non-garment prop contents, damage, '
        'presence/disappearance and stable physical relationships. Do not restate the function of a '
        'tool/trap or demand causal explanations as visual constraints. Required current actions are '
        'already checked against each page\'s prose. The separate approved costume/garment ledger is: '
        +json.dumps(context['costume_ledger']))
    required=(json.loads(requirements_path.read_text()) if requirements_path.exists() else
        generate(project['config']['ollama_url'],model,requirements_prompt,requirements_schema))
    jsonschema.validate(required,requirements_schema)
    requirements=required['requirements']
    if len({r['id'] for r in requirements})!=len(requirements):
        raise ValueError('Independent prose inventory duplicated a requirement ID.')
    write_json(requirements_path,required)

    def compile_checked(label, prompt, schema, review_prompt, validator):
        feedback = ''
        for attempt in range(1, 4):
            target = root / f'{label}-{attempt:02d}.json'
            request = prompt + feedback
            write_json(root / f'{label}-{attempt:02d}-request.json', {'prompt': request, 'schema': schema, 'model': model})
            value = json.loads(target.read_text()) if target.exists() else generate(
                project['config']['ollama_url'], model, request, schema, seed=attempt-1)
            write_json(target, value)
            review_path = root / f'{label}-{attempt:02d}-review.json'
            try:
                jsonschema.validate(value, schema)
                validator(value)
            except (ValueError, jsonschema.ValidationError) as exc:
                review = {'valid': False, 'uncertain': False, 'issues': [str(exc)]}
            else:
                application = ({str(p['pageNumber']):[f for f in value['persistent_facts']
                    if f['from_page']<=p['pageNumber']<=f['through_page']]
                    for p in project['story']['pages']} if label=='catalogue' else None)
                review = json.loads(review_path.read_text()) if review_path.exists() else generate(
                    project['config']['ollama_url'], model,
                    review_prompt + '\nCandidate private plan: ' + json.dumps(value, ensure_ascii=False)
                    + ('\nCode-computed active prop facts on EACH page (only these facts apply on that page): '
                       +json.dumps(application) if application is not None else ''), audit_schema)
                if label=='catalogue' and requirements:
                    coverage_path=root/f'{label}-{attempt:02d}-coverage.json'
                    cp,cs=coverage_request(project,value,requirements)
                    coverage=(json.loads(coverage_path.read_text()) if coverage_path.exists() else
                              generate(project['config']['ollama_url'],model,cp,cs))
                    write_json(coverage_path,coverage)
                    missing=coverage_issues(coverage,requirements,value)
                    if missing:
                        review={**review,'valid':False,'issues':review.get('issues',[])+missing}
            write_json(review_path, review)
            if review.get('valid') is True and review.get('uncertain') is False and review.get('issues') == []:
                return value, review
            feedback = '\nCorrect the previous plan: ' + json.dumps(value) + '\nReview: ' + json.dumps(review)
        raise ValueError(f'Critical scene continuity planning failed for {label}. Saved all attempts in {root}. Last review: {review}')

    base = json.dumps(context, ensure_ascii=False)
    catalogue_prompt = (
        'Compile a small PRIVATE design catalogue of plot-critical inanimate props/landmarks in this whole story. '
        'Do not rewrite the story. Include objects whose identity, physical form, containment or change is needed '
        'to understand the problem and its solution. Exclude incidental background decorations and worn '
        'character costumes. A detached garment used as a plot prop may be referenced, but reuse its '
        'existing costume_ledger/source character design exactly, rather than inventing a second design. '
        'Give each object one concise reusable visual design: '
        'material, colour, silhouette, distinctive construction. Preserve every explicit story fact. You may '
        'choose compatible unspecified art-design details (e.g. shape of a statue) once so later images reuse '
        'the SAME object; these are illustration design choices, never new plot events. Describe intrinsic '
        'appearance here, not changing positions/ownership/contents. For a figurative statue, choose what '
        'it depicts and its whole figure/base construction once; a vague stone figure would allow unrelated '
        'human, animal or isolated head designs on successive pages. Avoid tiny finish or lighting specifications. '
        'A statue with a carved face is an inanimate '
        'prop unless it is actually one of the acting cast. At most twelve '
        'objects; keep all distinct tools needed by failed attempts as well as the final solution. '
        'Object designs have no required visibility list. Cite source_pages only on persistent state facts.\n' + base)
    catalogue_prompt += ('\nNames/IDs and appearance describe the permanent OBJECT, not a temporary state. '
        'Appearance contains only intrinsic material, colour, shape and distinctive construction. '
        'Do not put contents, ownership, worn/detached, soaked/clean, open/closed, broken/intact or '
        'attachment to another object into appearance: those belong exclusively in ranged persistent_facts. '
        'For example, describe a scarf as yellow knitted wool with tassels; describe honey-soaking and '
        'removal only in the relevant state facts. Describe a bubble\'s translucent sphere here, its '
        'trapped contents only in a ranged fact. This prevents a later state leaking onto earlier pages.')
    catalogue_prompt += ('\nAlso trace a few consequential PERSISTENT PROP FACTS through the complete prose. '
        'These apply automatically to EVERY page in the inclusive range, including pages where the local '
        'illustration prompt forgets them. Exclude costumes/body states because their separate ledger and '
        'audits already enforce them. Include ongoing containment, damage, attachment and explicit final '
        'absence. Use conditional for an object that may be offscreen; its requirement MUST start with '
        'the literal uppercase word IF and the visible subject: IF a bottle is shown, its trapped '
        'coin remains inside until the prose frees it. EVERY positive persistent state uses conditional '
        'visibility (even intact/unbroken or recovered/in someone\'s possession). Its requirement must '
        'start IF <the relevant object/actor/surface is visible>. Actual presence for a chosen event is '
        'handled by the individual scene checks, not this global list. Use absent ONLY for an explicit '
        'required absence (e.g. a vanished bubble stays gone), never for an intact object. State literal '
        'physical facts only, supported by the cited prose pages. Do not turn illustration-only decoration '
        'into a persistent requirement. Range boundaries must respect the chosen before/after event on '
        'each page. Objects may have different facts in nonoverlapping phases.')
    catalogue_prompt+='\nIndependent prose requirements to cover: '+json.dumps(requirements)
    catalogue_review = (
        'Audit this private prop catalogue against the whole original story. Reject contradictory object '
        'designs, missing problem/solution props, or invented plot events. Compatible unspecified visual design '
        'choices are allowed and are not unsupported story claims. Do not require every incidental object. '
        'Reject duplicate worn-costume/body-state requirements here. A detached garment used as a prop '
        'may appear in the catalogue, but its design must match the existing ledger/source character. '
        'source_pages are prose evidence CITATIONS ONLY, never required visibility on those pages. '
        'A statue cited on the final page may be offscreen; it does not imply that the popped bubble '
        'still exists. Persistent facts apply ONLY in their from_page..through_page range. The supplied '
        'code-computed per-page table is authoritative for which planned facts apply: never extend '
        'a fact to a later page merely because a catalogue object cites that page. '
        'Verify persistent prop facts and inclusive ranges against '
        'the actual story events, including omitted but necessary containment and the final resolved state. '
        'Conditional facts must allow the prop to be offscreen; all positive persistent states are '
        'conditional, never a demand to draw that object in every frame. visibility=absent is reserved '
        'for required absence after disappearance/removal. Frame-specific necessary presence/actions '
        'are handled by the later scene compiler.\n' + base)
    catalogue_review += ('\nCheck that appearance and object names are intrinsic designs only. Reject '
        'temporary contents, ownership, worn/detached, soaking/cleaning, damage/restoration or attachments '
        'encoded as permanent appearance. Those changing states belong in the ranged persistent facts '
        'so an earlier page cannot accidentally inherit a later state. Ordinary intrinsic texture '
        '(e.g. smooth rubber or knitted wool) and compatible art-design choices remain allowed.')
    def validate_objects(value):
        if len({o['id'] for o in value['objects']}) != len(value['objects']):
            raise ValueError('Duplicate critical object IDs.')
        known={o['id'] for o in value['objects']}
        pages={p['pageNumber'] for p in project['story']['pages']}
        facts=value['persistent_facts']
        if len({f['id'] for f in facts})!=len(facts):
            raise ValueError('Duplicate persistent fact IDs.')
        for fact in facts:
            if (not set(fact['object_ids']) <= known or not set(fact['source_pages']) <= pages
                    or not set(range(fact['from_page'],fact['through_page']+1)) <= pages
                    or fact['from_page']>fact['through_page']):
                raise ValueError('Invalid persistent prop range, object or evidence page.')
            if fact['visibility']=='conditional' and not fact['requirement'].startswith('IF '):
                raise ValueError('A conditional persistent fact must explicitly start IF <the relevant object/surface is visible>; its presence is optional.')
    catalogue, cat_review = compile_checked('catalogue', catalogue_prompt, catalogue_schema(project),
                                            catalogue_review, validate_objects)
    scenes = [{'asset_name': 'cover.png', **project['book']['cover']}] + [
        {'asset_name': f"pages/page-{p['page_number']:03d}.png", **p} for p in project['book']['pages']]
    # Existing page briefs already passed editorial/action review. Preserve
    # them: a second rewrite/audit introduced mandatory decorative stars,
    # invented pose carryover, and false room-to-garden continuity errors.
    # Add only independently approved whole-story facts and intrinsic designs;
    # the actual image still receives action, costume, cast and critical QA.
    all_scenes = bind_original_scenes(scenes, catalogue['objects'])
    reviews = []
    result = {'version': VERSION, 'source_hash': key, 'model': model, 'sampling':sampling,
              **catalogue, 'prose_requirements':requirements,
              'scenes': {s['asset_name']: s for s in all_scenes}, 'catalogue_review': cat_review, 'reviews': reviews}
    write_json(approved, result)
    return result


def mentioned_object_ids(text, objects, strict=False):
    import re
    # Use full names/IDs and an unambiguous final noun to recognise ordinary
    # references such as "statue" for "grey stone statue". Ambiguous nouns are
    # not used; persistent fact IDs also bind relevant objects independently.
    nouns={o['id']:o['id'].split('_')[-1] for o in objects}
    wanted=[]
    for o in objects:
        terms=[o['name'].lower(),o['id'].replace('_',' ')]
        shared_word = strict and any(other['id'] != o['id'] and
            re.search(r'\b'+re.escape(nouns[o['id']])+r'\b',
                      other['name'].lower()+' '+other['id'].replace('_',' ')) for other in objects)
        if list(nouns.values()).count(nouns[o['id']])==1 and not shared_word:
            terms.append(nouns[o['id']])
        if any(re.search(r'\b'+re.escape(term)+r'\b',text.lower()) for term in terms):
            wanted.append(o['id'])
    return wanted


def bind_original_scenes(scenes, objects):
    result=[]
    for scene in scenes:
        wanted=mentioned_object_ids(scene['scene_prompt'],objects)
        result.append({'asset_name':scene['asset_name'],'literal_prompt':scene['scene_prompt'],
                       'object_ids':wanted,'checks':[]})
    return result


def scene_record(project, scene):
    name = f"pages/page-{scene['page_number']:03d}.png" if 'page_number' in scene else 'cover.png'
    return effective_record(project, name)


def scene_page_number(project, name):
    if name.startswith('pages/page-'):
        return int(name.split('-')[-1].split('.')[0])
    if project.get('render_settings', {}).get('scene_context_policy', 0) >= 1:
        # The costume planner's cover moment selects character appearance. Its
        # page-1 default (when costumes never change) is not a plot timestamp.
        # Covers have their own brief; preserve intrinsic designs and explicit
        # cover checks without importing numbered-page event requirements.
        return None
    return project.get('art_plan', {}).get('cover_moment', {}).get('pageNumber')


def scene_context(project, name):
    number = scene_page_number(project, name)
    if number is None:
        return 'Book cover composition, not a numbered story page. Follow the cover brief.'
    return f'Story page {number} of {len(project["story"]["pages"])}. Apply time-dependent facts at this page only.'


def effective_record(project, name):
    contract=project.get('scene_contract', {})
    record=contract.get('scenes', {}).get(name)
    if record is None:
        return None
    number = scene_page_number(project, name)
    strict = project.get('render_settings', {}).get('scene_context_policy', 0) >= 2
    facts=[f for f in contract.get('persistent_facts',[]) if number is not None
           and f['from_page']<=number<=f['through_page']]
    prose_ids=[]
    if project.get('render_settings',{}).get('scene_contract_prompt_policy',0)>=1 and number is not None:
        prose=next((p['text'] for p in project['story']['pages'] if p['pageNumber']==number),'')
        prose_ids=mentioned_object_ids(prose,contract['objects'],strict=strict)
    # Old bound records may contain a noun-only false match. Rebind records
    # created by the literal-scene binder, retaining independently stated checks.
    base_ids = (mentioned_object_ids(record['literal_prompt'],contract['objects'],strict=True)
                if strict and not record['checks'] else record['object_ids'])
    return {**record, 'object_ids':list(dict.fromkeys(base_ids+
                prose_ids+[cid for f in facts for cid in f['object_ids']])),
            'absent_object_ids':list({cid for f in facts if f['visibility']=='absent' for cid in f['object_ids']}),
            'checks':record['checks']+[{**f,'id':'persistent_'+f['id'],
                'visibility':'required' if f['visibility']=='absent' else f['visibility']} for f in facts]}


def scene_render_details(project, scene):
    record = scene_record(project, scene)
    if record is None:
        return [], []
    checks=record['checks']
    wanted=record['object_ids']
    if project.get('render_settings',{}).get('scene_contract_prompt_policy',0)>=1:
        import re
        # QA retains every conditional/absence rule. Rendering must not describe
        # an absent object's attractive appearance, or encourage offscreen props
        # merely because their condition would matter IF they were visible.
        name = f"pages/page-{scene['page_number']:03d}.png" if 'page_number' in scene else 'cover.png'
        number=scene_page_number(project, name)
        prose=next((p['text'] for p in project['story']['pages'] if p['pageNumber']==number),'')
        clauses=re.split(r'[.;,!?]|\bbut\b',record['literal_prompt']+' '+prose)
        positive=' '.join(c for c in clauses if not re.search(r'\b(?:no|not|without|gone|vanished|absent|removed)\b',c,re.I))
        blocked=set(record['absent_object_ids'])
        strict = project.get('render_settings', {}).get('scene_context_policy', 0) >= 2
        wanted=set(mentioned_object_ids(positive,project['scene_contract']['objects'],strict=strict))-blocked
        if project.get('render_settings', {}).get('scene_context_policy',0) >= 3:
            # The approved library also resolves synonyms. Read its saved routes
            # directly: calling entries() here would recurse through this function.
            routed = {e['source_object_id'] for e in project.get('visual_library',{}).get('plan',{}).get('entries',[])
                      if name in e['scenes'] and not e.get('source_character_id')}
            wanted |= routed - blocked
        from .object_relations import active
        for relation in active(project,name):
            content,container=relation['content_id'],relation['container_id']
            objects_by_id={o['id']:o for o in project['scene_contract']['objects']}
            checks=checks+[{'id':'contents_'+relation['id'],'object_ids':[content,container],
                'visibility':'conditional','requirement':
                f"{objects_by_id[content]['name']} remains inside {objects_by_id[container]['name']} at this moment. "
                'Show the contents when that interior is visible; a genuinely occluded or cropped interior is allowed.'}]
        # Contents/attachments explicitly linked to a present subject remain
        # available (e.g. the ball inside a visible bubble).
        for _ in range(len(checks)+1):
            expanded=wanted|{cid for c in checks if wanted.intersection(c.get('object_ids',[]))
                             for cid in c.get('object_ids',[]) if cid not in blocked}
            if expanded==wanted:break
            wanted=expanded
        checks=[c for c in checks if c['visibility']=='required'
                or wanted.intersection(c.get('object_ids',[])) or not c.get('object_ids')]
    objects = [o for o in project['scene_contract']['objects'] if o['id'] in wanted]
    return objects, checks


def scene_brief(project, scene, normalize_staging=False):
    record = scene_record(project, scene)
    literal = record['literal_prompt'] if record else scene['scene_prompt']
    if normalize_staging:
        from .scene_staging import normalize
        literal = normalize(project, scene.get('text', ''), literal)
    if record is None:
        return literal
    objects, checks = scene_render_details(project, scene)
    name = f"pages/page-{scene['page_number']:03d}.png" if 'page_number' in scene else 'cover.png'
    context = (scene_context(project, name) + '\n'
               if project.get('render_settings', {}).get('scene_context_policy', 0) >= 1 else '')
    return (context + literal + '\nCritical visible story facts: '
            + json.dumps([{'requirement': c['requirement'], 'visibility': c['visibility']} for c in checks], ensure_ascii=False)
            + '\nStable prop designs (only depict them where this frame requires/allows): '
            + json.dumps(objects, ensure_ascii=False))


def review_scene_contract(project, spec, png, generate):
    record = effective_record(project, spec['name']) if spec['kind'] == 'scene' else None
    if record is None:
        return None
    objects = [o for o in project['scene_contract']['objects'] if o['id'] in record['object_ids']]
    # Intrinsic design is also checked, conditional on visibility. Do not require
    # every object in a close-up, or confuse that with a missing necessary action.
    checks = record['checks'] + [{'id': 'design_'+o['id'], 'requirement':
        f"IF {o['name']} is visible, it retains this design: {o['appearance']}", 'visibility': 'conditional'} for o in objects]
    if not checks:
        from .object_relations import inspect_contents
        return inspect_contents(project,spec,png,generate)
    schema = obj({'items': {'type': 'array', 'items': obj({
        'id': {'type': 'string', 'enum': [c['id'] for c in checks]},
        'observation': TEXT, 'matches': {'type': 'boolean'}, 'uncertain': {'type': 'boolean'}})}})
    context = ({'temporal_context': scene_context(project, spec['name'])}
               if project.get('render_settings', {}).get('scene_context_policy', 0) >= 1 else {})
    contents_policy = ('An established containment relation persists until the story removes the contents. '
        'Conditional visibility permits a cropped or genuinely occluded interior, not a visibly empty '
        'container/cavity whose contents should still be there. Judge actual visible interior space. '
        if project.get('render_settings',{}).get('scene_context_policy',0)>=3 else '')
    prompt = (contents_policy + 'Inspect ONLY this candidate image for the supplied plot-critical facts and recurring prop '
              'designs. First describe actual visible objects, contents, contacts and states, THEN decide '
              'each check. Do not infer a missing object from the expected story. A transparent container '
              'visibly empty is not proof its required contents are present. Conditional checks allow a '
              'prop to be completely offscreen, but IF shown its actual state must be correct. Required '
              'checks need visible evidence. Natural folds, small stylized proportions, exact incidental '
              'grips and perspective changes are allowed; losing the recognizable object, changing its '
              'material/construction, missing trapped contents, or restoring a vanished problem is not. '
              'A painted highlight on a rubber ball does NOT change its material or make a matte rubber '
              'ball the wrong object. Allow illumination, highlight and shading differences; judge actual '
              'shape/construction/identity, not pixel-level finish. A close-up may crop a larger prop: '
              'verify the visible part, without demanding its offscreen base in a close-up. '
              'A statue with a face remains an inanimate prop. Assess only these checks, not cast count '
              'or costume. Return one item per ID; uncertainty cannot approve.\n'
              + json.dumps({**context, 'scene': record['literal_prompt'], 'checks': checks}, ensure_ascii=False))
    report = generate(project['config']['ollama_url'], project['render_settings']['review_model'], prompt, schema, [png])
    complete = sorted(i['id'] for i in report['items']) == sorted(c['id'] for c in checks)
    issues = [i['id'] + ': ' + i['observation'] for i in report['items'] if not i['matches'] or i['uncertain']]
    if not complete:
        issues.append('Critical scene reviewer omitted or duplicated a check.')
    from .object_relations import inspect_contents
    contents=inspect_contents(project,spec,png,generate)
    return {**report, 'contents_inspection':contents,
            'accepted': complete and not issues and contents['accepted'], 'issues': issues+contents['issues'],
            'uncertain': not complete or any(i['uncertain'] for i in report['items']) or contents['uncertain'],
            'retry_instructions': [next(c['requirement'] for c in checks if c['id'] == i['id'])
                                   for i in report['items'] if not i['matches'] or i['uncertain']]+contents['retry_instructions']}

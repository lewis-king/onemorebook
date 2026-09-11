"""One draft per explicit request; no automatic quality scoring or retry loop."""
import hashlib
import io
import json
from pathlib import Path

from . import assisted_store as store
from .storage import write_exclusive, write_json
from .story import asset_seed, digest, writing_prompt
from .assisted_references import MAX_REFERENCE_IMAGES
from . import assisted_story
from . import assisted_prompt_context
from . import assisted_prompt_base


def directory(sid, stage_id, attempt):
    return store.stage_dir(sid, stage_id) / f'attempt-{attempt:04d}'


def selected(state, stage_id):
    stage = store.stage(state, stage_id)
    return next(c for c in stage['candidates'] if c['id'] == stage['selected'])


def approved(state, stage_id):
    stage = store.stage(state, stage_id)
    if stage['status'] != 'approved':
        raise ValueError(f'{stage["title"]} needs your approval first.')
    candidate = selected(state, stage_id)
    record = json.loads((store.root(state['id'])/'creator/decisions'/f"{stage['decision_id']}.json").read_text())
    if (record['action'] != 'approve' or record['candidate_id'] != candidate['id']
            or record['candidate_sha256'] != candidate['sha256']):
        raise ValueError('Saved approval does not match the selected candidate.')
    return store.candidate_path(state, candidate)


def package(state):
    return json.loads(approved(state, 'story').read_text())


def recover_candidate(state,intent):
    """Recover a completed atomic file if shutdown preceded the state update."""
    path=directory(state['id'],intent['stage_id'],intent['attempt'])
    if any(c['attempt']==intent['attempt'] for c in store.stage(state,intent['stage_id'])['candidates']):
        return True
    if (path/'candidate.png').exists() and (path/'generation.json').exists():
        from PIL import Image
        info=json.loads((path/'generation.json').read_text())
        expected=digest([state['id'],intent['stage_id'],intent['attempt'],info])
        with Image.open(path/'candidate.png') as im:
            if im.size!=(1024,1024) or json.loads(im.info.get('book_asset','{}')).get('signature')!=expected:
                raise ValueError('Interrupted candidate does not match its saved generation metadata.')
            im.verify()
        store.record_candidate(state['id'],intent['stage_id'],intent['attempt'],path/'candidate.png',info)
        return True
    if (path/'candidate.json').exists():
        value=json.loads((path/'candidate.json').read_text())
        request=json.loads((path/'request.json').read_text()) if (path/'request.json').exists() else {}
        store.record_candidate(state['id'],intent['stage_id'],intent['attempt'],path/'candidate.json',
                               {'content':value,'prompt':request.get('prompt',''),'model':request.get('model'),
                                'method':'recovered_text_candidate'})
        return True
    return False


def draft_json(state, stage_id, attempt, prompt, schema):
    from .assisted_writer import complete_json
    path = directory(state['id'], stage_id, attempt)
    seed = asset_seed(state['config']['seed'], stage_id+':'+str(attempt))
    tokens=16384 if stage_id in ('story','plan') and assisted_story.page_bounds(state['config'])[1]>8 else 8192
    if (path/'response.txt').exists():
        from .quality import parse_model_json
        return parse_model_json((path/'response.txt').read_text())
    import comfy.model_management as mm
    mm.unload_all_models()
    mm.soft_empty_cache()
    return complete_json(path,state['config'],prompt,schema,seed,tokens,mm.throw_exception_if_processing_interrupted)


def text_step(state, intent):
    from . import assisted_plan
    sid, stage_id, attempt = state['id'], intent['stage_id'], intent['attempt']
    current = store.stage(state, stage_id)
    if stage_id == 'story':
        prompt, schema = writing_prompt(state['config']), assisted_story.schema(state['config'])
        prompt += '\nIn private production metadata include numeric height_cm for every character. Keep the public story contract unchanged.'
    else:
        prompt, schema = assisted_plan.request(package(state), state['config'])
    if intent['feedback']:
        prompt += '\nHuman requested revisions: '+intent['feedback']
        if current['candidates']:
            prior = next((c for c in current['candidates'] if c['id']==intent.get('source_candidate')),current['candidates'][-1])
            prompt += '\nPrevious draft to revise, preserving successful parts:\n'+store.candidate_path(state,prior).read_text()
    value = draft_json(state, stage_id, attempt, prompt, schema)
    formatting_repairs=[]
    metadata_repairs=[]
    if stage_id=='story':
        value,formatting_repairs=normalize_generated_cast(value)
        value,metadata_repairs=normalize_generated_metadata(value)
    import jsonschema
    validation_error=None
    try:
        if stage_id == 'story':
            assisted_story.validate(value, state['config'])
        else:
            assisted_plan.validate(package(state), value)
    except (ValueError,KeyError,jsonschema.ValidationError) as exc:
        # A readable failed draft can be revised by its human editor. Approval
        # still repeats strict validation and cannot accept a broken contract.
        validation_error=str(exc)
    path = directory(sid, stage_id, attempt)/'candidate.json'
    write_json(path, value)
    craft_metadata = {}
    if stage_id == 'story' and state['config'].get('story_craft_version') and not validation_error:
        from .story_craft import review_guide
        guide = review_guide(value, state['config'])
        write_json(path.parent/'story-guide.json', guide)
        craft_metadata['story_guide'] = guide
    store.record_candidate(sid, stage_id, attempt, path, {'model': state['config']['ollama_model'], 'prompt': prompt,
                                                       'method': 'local_text_generation', 'content': value,
                                                       'validation_error':validation_error,
                                                       'formatting_repairs':formatting_repairs,
                                                       'metadata_repairs':metadata_repairs, **craft_metadata})


def normalize_generated_cast(value):
    """Resolve exact known-name serialization glitches; never infer a new actor."""
    import copy,re
    value=copy.deepcopy(value);repairs=[]
    story=value.get('story',{})
    names=story.get('metadata',{}).get('characters',[])
    if not isinstance(names,list) or not all(isinstance(n,str) for n in names):return value,repairs
    canonical={n.casefold():n for n in names}
    if len(canonical)!=len(names):return value,repairs
    for page in story.get('pages',[]):
        if not isinstance(page,dict) or not isinstance(page.get('charactersPresent'),list):continue
        for i,name in enumerate(page['charactersPresent']):
            if not isinstance(name,str):continue
            clean=re.sub(r'^characters/+', '',name.strip(),flags=re.I)
            target=canonical.get(clean.casefold())
            if target and target!=name:
                page['charactersPresent'][i]=target
                repairs.append({'page':page.get('pageNumber'),'field':'charactersPresent','from':name,'to':target})
    return value,repairs


def normalize_generated_metadata(value):
    """Fill the public main-character prompt from its private canonical design.

    The two documents deliberately carry the same design for different consumers.
    When a local writer omits this required public counterpart, copying the single
    approved production main character is deterministic and does not invent content.
    Other missing fields remain validation errors for human review.
    """
    import copy
    value=copy.deepcopy(value);repairs=[]
    story=value.get('story',{}) if isinstance(value,dict) else {}
    metadata=story.get('metadata',{}) if isinstance(story,dict) else {}
    production=value.get('production',{}) if isinstance(value,dict) else {}
    characters=production.get('characters',[]) if isinstance(production,dict) else []
    mains=[c for c in characters if isinstance(c,dict) and c.get('role')=='main'
           and isinstance(c.get('appearance'),str) and c['appearance'].strip()]
    if (isinstance(metadata,dict) and not str(metadata.get('mainCharacterDescriptivePrompt','')).strip()
            and len(mains)==1):
        metadata['mainCharacterDescriptivePrompt']=mains[0]['appearance'].strip()
        repairs.append({'field':'metadata.mainCharacterDescriptivePrompt','source':'production.characters[role=main].appearance'})
    return value,repairs


def cast_board(state, current, path):
    """Reuse the proven guide's crop/scale layout, with only this frame's approved cast."""
    from .story import make_render_plan
    from .scale import make_scale_guide, cast_height
    from PIL import Image
    book = make_render_plan(**package(state))
    names = current['cast_refs']
    if len(names) == 1:
        return approved(state, names[0])
    # The scale helper expects canonical files under a rendition. A private staging
    # directory points to exact approved bytes, including a current costume variant.
    staging = path/'cast-sources'
    chars = []
    for cid, name in zip(current['cast_ids'], names):
        char = next(c for c in book['characters'] if c['id']==cid)
        if cast_height(char) is None:
            raise ValueError(f"{char['name']} needs height_cm in the story production plan for the cast guide.")
        chars.append(char)
        write_exclusive(staging/'characters'/f'{cid}.png', approved(state,name).read_bytes())
    minimal = {**book, 'characters': chars, 'cover': {'character_ids': current['cast_ids'], 'scene_prompt': current['brief']}}
    project = {'book':minimal, 'render_root':str(staging)}
    image = make_scale_guide(project, {'kind':'scene','name':'cover.png'})
    data=io.BytesIO(); image.save(data,format='PNG')
    target = path/'cast-reference.png'; write_exclusive(target,data.getvalue())
    return target


def image_inputs(state, current, intent):
    path = directory(state['id'],current['id'],intent['attempt'])
    references=[]; hashes={}
    for name in current['references']:
        hashes[name]=hashlib.sha256(approved(state,name).read_bytes()).hexdigest()
    if intent.get('mode') == 'edit':
        source=next(c for c in current['candidates'] if c['id']==intent['source_candidate'])
        references=[{'path':str(store.candidate_path(state,source)),'label':'Selected illustration to edit','sha256':source['sha256']}]
        prompt='Edit Image 1. '+intent['feedback']+' Preserve the unaffected composition, character identities, gaze relationships, object designs and illustration style.'
    else:
        cast_refs=current.get('cast_refs',[])
        if cast_refs:
            image=cast_board(state,current,path)
            references.append({'path':str(image),'label':'Cast: '+', '.join(store.stage(state,n)['title'] for n in cast_refs)})
        for name in current['references']:
            if name not in cast_refs:
                references.append({'path':str(approved(state,name)), 'label':store.stage(state,name)['title']})
        if current['kind']=='scene' and not references:
            references.append({'path':str(approved(state,'style.png')),'label':'Art style'})
            hashes['style.png']=hashlib.sha256(approved(state,'style.png').read_bytes()).hexdigest()
        style = package(state)['production']['visual_bible']['style'] if current['kind']=='scene' else ''
        prompt=(style+' ' if current['kind']=='scene' else '')+current['brief']
        if references:
            prompt += ' '+ '; '.join(f"Image {i+1}: {r['label']}" for i,r in enumerate(references))+'.'
        if current['kind']=='character_state':
            prompt+=' Keep the identity of the character in Image 1 with the described current appearance.'
        if current['kind']=='prop_state' and not current.get('source_scene'):
            prompt+=' Use the referenced props as the parts of this single result, preserving their materials, colours and shapes in the described arrangement.'
    if len(references)>MAX_REFERENCE_IMAGES:
        raise ValueError(f'This scene has {len(references)} input images, exceeding the '
                         f'{MAX_REFERENCE_IMAGES}-image budget; revise the plan rather than dropping a reference.')
    for ref in references:
        ref['sha256']=hashlib.sha256(Path(ref['path']).read_bytes()).hexdigest()
        ref['path']=Path(ref['path']).relative_to(store.root(state['id'])).as_posix()
    managed = (current['kind']=='scene' and intent.get('mode','fresh')=='fresh'
               and intent.get('scene_prompt_version')==assisted_prompt_base.VERSION)
    base = None
    if managed:
        context_hash = assisted_prompt_base.signature(state,current,hashes)
        if intent.get('prompt_base'):
            pinned=assisted_prompt_base.verify(state,current['id'],intent['prompt_base'])
            if pinned['context_sha256']==context_hash:
                base=pinned
                prompt=base['prompt']
    if intent.get('prompt_override'):
        prompt=intent['prompt_override']
    elif intent['feedback'] or managed and base is None:
        request=assisted_prompt_context.revision_request(current,intent,prompt,references,
                                                        {s['id']:s for s in state['stages']},
                                                        preparing=managed and not intent['feedback'])
        result=draft_json(state,current['id'],intent['attempt'],request,assisted_prompt_context.PROMPT_SCHEMA)
        if set(result)!= {'prompt'} or not isinstance(result['prompt'],str) or not 1<=len(result['prompt'])<=5000:
            raise ValueError('The prompt rewrite must return one nonempty prompt, at most 5,000 characters.')
        prompt=result['prompt']
    if managed:
        if base is None or prompt!=base['prompt']:
            base=assisted_prompt_base.install(state,current['id'],prompt,context_hash,
                reason=intent['feedback'] or ('Explicit full-scene prompt' if intent.get('prompt_override')
                                               else 'Prepared from approved page prose and reference designs'),
                source={'kind':'prompt_override' if intent.get('prompt_override') else 'local_gemma'},
                attempt=intent['attempt'])
        write_json(path/'prompt-base.json',base)
    return prompt,references,hashes


def image_graph(state,intent):
    from comfy_execution.graph_utils import GraphBuilder
    from .render import FLUX_MODELS, FLUX_TURBO_LORA
    from .generation_info import from_graph
    import folder_paths
    current=store.stage(state,intent['stage_id']); sid=state['id']; attempt=intent['attempt']
    for category,name in [('diffusion_models',FLUX_MODELS['flux_model']),('text_encoders',FLUX_MODELS['flux_encoder']),
                          ('vae',FLUX_MODELS['flux_vae']),('loras',FLUX_TURBO_LORA)]:
        if not folder_paths.get_full_path(category,name):
            raise ValueError(f'Missing local model: {name}')
    prompt,refs,hashes=image_inputs(state,current,intent)
    seed=asset_seed(state['config']['seed'],current['id']+':'+str(attempt))
    graph=GraphBuilder()
    model=graph.node('UNETLoader',unet_name=FLUX_MODELS['flux_model'],weight_dtype='default')
    model=graph.node('LoraLoaderModelOnly',model=model.out(0),lora_name=FLUX_TURBO_LORA,strength_model=1.0)
    clip=graph.node('CLIPLoader',clip_name=FLUX_MODELS['flux_encoder'],type='flux2',device='default')
    vae=graph.node('VAELoader',vae_name=FLUX_MODELS['flux_vae'])
    text=graph.node('CLIPTextEncode',clip=clip.out(0),text=prompt)
    cond=graph.node('FluxGuidance',conditioning=text.out(0),guidance=2.5).out(0)
    for ref in refs:
        pixels=graph.node('BookAssistedReference',session_id=sid,path=ref['path'],sha256=ref['sha256'])
        latent=graph.node('VAEEncode',pixels=pixels.out(0),vae=vae.out(0))
        cond=graph.node('ReferenceLatent',conditioning=cond,latent=latent.out(0)).out(0)
    guider=graph.node('BasicGuider',model=model.out(0),conditioning=cond)
    sample=graph.node('SamplerCustomAdvanced',guider=guider.out(0),
        noise=graph.node('RandomNoise',noise_seed=seed).out(0),
        sampler=graph.node('KSamplerSelect',sampler_name='euler').out(0),
        sigmas=graph.node('Flux2Scheduler',steps=8,width=1024,height=1024).out(0),
        latent_image=graph.node('EmptyFlux2LatentImage',width=1024,height=1024,batch_size=1).out(0))
    decoded=graph.node('VAEDecode',samples=sample.out(0),vae=vae.out(0))
    method='image_edit' if intent.get('mode')=='edit' or current.get('source_scene') else 'reference_generation' if refs else 'text_to_image'
    info={**from_graph(graph.finalize(),method),'prompt':prompt,'seed':str(seed),
          'reference_images':refs,'approved_reference_sha256':hashes}
    base_file=directory(sid,current['id'],attempt)/'prompt-base.json'
    if base_file.exists():
        info['prompt_base']=json.loads(base_file.read_text())
    if intent.get('feedback') and not intent.get('prompt_override'):
        info['revision_context_version']=assisted_prompt_context.VERSION
    final=graph.node('BookAssistedSaveCandidate',images=decoded.out(0),session_id=sid,
                     stage_id=current['id'],attempt=attempt,metadata=json.dumps(info))
    write_json(directory(sid,current['id'],attempt)/'native.api.json',graph.finalize())
    write_json(directory(sid,current['id'],attempt)/'generation.json',info)
    with store.LOCK:
        latest=store.read(sid)
        if latest['job'] and latest['job']['attempt']==attempt and latest['current_stage']==current['id']:
            latest['job']['generation']=info;store.save(latest)
    return {'result':(final.out(0),),'expand':graph.finalize()}


def save_image(sid,stage_id,attempt,images,metadata,prompt=None):
    from .storage import image_bytes
    state=store.read(sid); info=json.loads(metadata)
    spec={'name':stage_id,'signature':digest([sid,stage_id,attempt,info])}
    data=image_bytes(spec,images,prompt,None)
    path=directory(sid,stage_id,attempt)/'candidate.png'
    write_exclusive(path,data)
    store.record_candidate(sid,stage_id,attempt,path,info)
    return path


def advance(state,candidate,record):
    """Persist approval before advancing; replaying the same decision is safe."""
    from . import assisted_plan
    current=store.stage(state)
    path=store.candidate_path(state,candidate)
    if current['id']=='story':
        value=json.loads(path.read_text());assisted_story.validate(value,state['config'])
        from .scale import cast_height
        if any(cast_height(c) is None for c in value['production']['characters']):
            raise ValueError('Add height_cm for each character in the private production draft before approving.')
        state['title']=value['story']['metadata']['title']
        state['approved_page_count']=len(value['story']['pages'])
    elif current['id']=='plan':
        value=json.loads(path.read_text());new=assisted_plan.stages(package(state),value)
        state['stages']=state['stages'][:2]+new
    else:
        if current.get('reference_revision') and set(candidate['metadata']['approved_reference_sha256'])!=set(current['references']):
            raise ValueError('This attempt uses the earlier reference set. Regenerate with the updated references before approving.')
        for name,expected in candidate['metadata']['approved_reference_sha256'].items():
            if hashlib.sha256(approved(state,name).read_bytes()).hexdigest()!=expected:
                raise ValueError('A source reference changed. This image needs a fresh review.')
    current.update(status='approved',selected=candidate['id'],decision_id=record['id'])
    index=next(i for i,s in enumerate(state['stages']) if s['id']==current['id'])
    state.update(job=None,error=None)
    if state.get('page_revision'):
        from .assisted_revision import finish
        finish(state)
    elif index+1<len(state['stages']):
        state['current_stage']=state['stages'][index+1]['id'];state['status']='ready'
    else:
        # A replacement of a previously published page creates a new immutable
        # export and therefore needs an explicit publication of that revision.
        state['status']='exporting';state.pop('publication',None)
    state['revision']+=1;store.save(state)
    return state


def export_session(state):
    import html
    book=package(state); assisted_story.validate(book,state['config'])
    relative=Path('exports')/state['export_revision'] if state.get('export_revision') else Path('export')
    target=store.root(state['id'])/relative
    for stage in state['stages'][2:]:
        write_exclusive(target/stage['id'],approved(state,stage['id']).read_bytes())
    story=book['story'];title=story['metadata']['title']
    write_json(target/'story.json',story)
    write_json(target/'production.json',book['production'])
    from .assisted_reference_updates import effective_plan
    write_json(target/'illustration-plan.json',effective_plan(state))
    if state.get('reference_updates'):
        write_json(target/'reference-updates.json',state['reference_updates'])
    sections=[f'<section><img src="cover.png" alt="Cover"><h1>{html.escape(title)}</h1></section>']
    for page in story['pages']:
        n=page['pageNumber'];text=html.escape(page['text']).replace('\n','<br>')
        sections.append(f'<section><img src="pages/page-{n:03d}.png" alt="Page {n}"><p>{text}</p><footer>{n}</footer></section>')
    document='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>'''+html.escape(title)+'''</title><style>body{margin:0;background:#eee8dd;color:#292720;font-family:Georgia,serif}
main{max-width:860px;margin:40px auto}section{background:#fffaf1;margin:32px 12px;padding:28px;break-after:page}
img{width:100%;height:auto}p{font-size:26px;line-height:1.65}h1,footer{text-align:center}a{color:#305747}
@media print{main{margin:0}section{margin:0}p{font-size:20pt}}</style><main>'''+''.join(sections)+'</main></html>'
    write_exclusive(target/'book.html',document.encode())
    write_exclusive(target/'IMPORT.txt',b'Paste story.json into onemorebook. Import cover.png and pages/page-NNN.png in page order. Private production and illustration-plan files are not app-facing story JSON.\n')
    manifest={'status':'complete','approval_mode':'human','session_id':state['id'],'title':title,
              'story_sha256':hashlib.sha256((target/'story.json').read_bytes()).hexdigest(),
              'approvals':[{'stage':s['id'],'decision_id':s['decision_id'],'candidate':selected(state,s['id'])['id'],
                            'sha256':selected(state,s['id'])['sha256']} for s in state['stages']]}
    write_json(target/'manifest.json',manifest)
    from PIL import Image, ImageDraw
    from .export import font
    images=[('Cover','cover.png')]+[(f'Page {p["pageNumber"]}',f'pages/page-{p["pageNumber"]:03d}.png') for p in story['pages']]
    sheet=Image.new('RGB',(960,280*((len(images)+3)//4)),'#fffaf1')
    draw=ImageDraw.Draw(sheet)
    for i,(label,name) in enumerate(images):
        with Image.open(target/name) as im:
            sheet.paste(im.convert('RGB').resize((220,220)),((i%4)*240+10,(i//4)*280+10))
        draw.text(((i%4)*240+10,(i//4)*280+240),label,font=font(16),fill='#29392f')
    data=io.BytesIO();sheet.save(data,format='PNG');write_exclusive(target/'contact-sheet.png',data.getvalue())
    book_url=f"/book-builder/books/{state['id']}/{relative.as_posix()}/book.html"
    history=state.setdefault('exports',[])
    if state.get('book_url') and not any(item['book_url']==state['book_url'] for item in history):
        history.append({'book_url':state['book_url']})
    if not any(item['book_url']==book_url for item in history):
        history.append({'book_url':book_url,'created_at':store.now(),'approvals':manifest['approvals']})
    state.update(status='complete',book_url=book_url)
    state['revision']+=1;store.save(state)
    return state

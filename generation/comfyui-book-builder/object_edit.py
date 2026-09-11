"""One bounded extra-object removal, with explicit complete-object inventory."""
import hashlib,json
from .story import object_schema as obj
VERSION=1
TEXT={'type':'string','minLength':1}
BOOL={'type':'boolean'}
INSTANCE=obj({'location':TEXT,'character_contacts':TEXT,'contained_objects':{'type':'array','items':TEXT}})
CHECKS=('extra_copy_identified','original_and_contents_retained','existing_story_action_readable',
        'survivor_preserves_actor_interaction','removal_alone_sufficient')
PRESERVATION=('duplicate_cluster_removed','original_objects_and_contents_preserved','character_pose_and_identity_preserved',
              'contacts_and_action_preserved','background_repaired','composition_and_style_preserved')


def eligible(report,expected_ids):
    r=report.get('review',{});cast={c['id']:c for c in r.get('characters',[])}
    return (not report.get('accepted') and not r.get('uncertain') and set(cast)==set(expected_ids)
        and r.get('unexpected_character_count')==0
        and all(c.get('count')==1 and all(c.get(k) is True for k in ('identity_matches','appearance_matches','scale_matches')) for c in cast.values())
        and all(r.get('checks',{}).get(k) is True for k in ('style_matches','anatomy_sound','no_unwanted_text','reference_background_ok')))


def plan_edit(project,spec,png,report,generate=None):
    from .quality import expected_scene,json_model
    from .flux_prompt import scene_source
    from .visual_library import entries,asset_name
    from .storage import valid_asset,asset_path
    from .story import asset_specs
    generate=generate or json_model
    if not eligible(report,expected_scene(project,spec)[0]):
        return {'decision':'redraw','reason':'Cast or global image defects prevent an isolated object removal.'}
    props=[e for e in entries(project,spec) if e['kind']=='prop']
    if not props or len(props)>5:
        return {'decision':'redraw','reason':'No bounded canonical object comparison available.'}
    images=[png];designs=[];by_name={s['name']:s for s in asset_specs(project)}
    for p in props:
        name=asset_name(p)
        if not valid_asset(project,by_name[name]):
            return {'decision':'uncertain','reason':'Canonical object image not approved.'}
        images.append(asset_path(project,name).read_bytes())
        designs.append({'id':p['id'],'name':p['name'],'appearance':p['appearance'],'reference_image':len(images)})
    ids={p['id'] for p in props}
    schema=obj({'objects':obj({p['id']:{'type':'array','items':INSTANCE} for p in props}),
        'decision':{'enum':['remove_extra_object_cluster','redraw','uncertain']},
        'target_id':{'type':'string'},'keep':TEXT,'remove':TEXT,
        'removed_object_ids':{'type':'array','items':TEXT},
        'preserve':{'type':'array','items':TEXT,'minItems':1},'fill':TEXT,'reason':TEXT,
        'checks':obj({k:BOOL for k in CHECKS}),
        'remaining_defects_after_removal':{'type':'array','items':TEXT}})
    context=scene_source(project,spec);context.pop('illustration_brief',None)
    prompt=('Image 1 is the failed illustration. The remaining images each show ONE complete canonical object design. '
        'First inventory every separate occurrence of each design in Image 1, including the position, actor contacts '
        'and contained objects. Count complete designs, not their individual components. Then decide whether ONE '
        'spatially distinct extra object or object cluster can be removed. Use the published prose for the required '
        'action and object count; canonical images describe design, not a demand to place an absent object. '
        'Do not remove intentional multiples or natural background scenery. Check the whole cluster: if a duplicate '
        'container also holds duplicate contents, remove both together, retaining the original container AND original '
        'contents at the actor’s interaction. Do not merely empty a duplicated container and leave the container. '
        'The intended original may be partly occluded. Preserve the actor’s already-readable pose, gaze, support, '
        'contacts, clothing and identity. Optional staging must not become a stricter action than the page prose. '
        'List any remaining concrete story defects AFTER the proposed removal. A false removal_alone_sufficient '
        'must cite such a remaining defect; do not treat removing an object and its contained duplicate as '
        'multiple unrelated repairs. Filling the revealed background is part of that one removal. '
        'Use redraw if the desired story action still needs changing, multiple unrelated repairs are needed, or '
        'removal would break an interaction. Return uncertain when copies or required counts cannot be established. '
        'Keep/remove descriptions must identify the entire surviving/removal cluster by location. Fill describes '
        'the exposed surrounding scenery. Preserve lists the specific things that must remain unchanged. '
        'Render instructions will receive ONLY Image 1; never refer to the diagnostic reference images in these fields.\n'
        +json.dumps({'scene':context,'canonical_objects':designs, 'blind_scene_observation':report.get('inventory',{}).get('description','')},ensure_ascii=False))
    plan=generate(project['config']['ollama_url'],project['render_settings']['review_model'],prompt,schema,
                  images=images,think=False,num_predict=4000)
    import jsonschema
    jsonschema.validate(plan,schema)
    if plan['decision']=='remove_extra_object_cluster':
        target=plan['target_id'];removed=plan['removed_object_ids']
        if (target not in ids or len(plan['objects'].get(target,[]))<2 or target not in removed
                or not set(removed)<=ids or not all(plan['checks'].values()) or plan['remaining_defects_after_removal']
                or plan['keep'].strip().casefold()==plan['remove'].strip().casefold()):
            plan['decision']='uncertain'
    return plan


def edit_prompt(plan):
    if plan['decision']!='remove_extra_object_cluster':raise ValueError('A confirmed extra-object removal is required.')
    return ('Edit Image 1. Remove '+plan['remove'].rstrip('.')+'. Fill the revealed area with '
            +plan['fill'].rstrip('.')+'. Keep '+plan['keep'].rstrip('.')+' unchanged. '
            +' '.join('Preserve '+p.rstrip('.')+'.' for p in plan['preserve'])
            +' Keep the position, shape and size of everything retained, and preserve the framing, lighting and painted style.')


def prepare_edit(project,spec,source_attempt,attempt,report,generate=None):
    from .storage import review_directory,write_json
    d=review_directory(project,spec)
    for path in d.glob('attempt-*-strategy.json'):
        strategy=json.loads(path.read_text());number=int(path.name.split('-')[1])
        if number<attempt and strategy.get('signature')==spec['signature'] and strategy.get('strategy')=='object_removal':return None
    source=d/f'attempt-{source_attempt:02d}.png'
    if not source.exists():return None
    png=source.read_bytes();sha=hashlib.sha256(png).hexdigest()
    if report.get('signature')!=spec['signature'] or report.get('png_sha256')!=sha:return None
    identity={'version':VERSION,'signature':spec['signature'],'source_attempt':source_attempt,'source_sha256':sha}
    path=d/f'attempt-{attempt:02d}-object-plan.json'
    if path.exists():
        record=json.loads(path.read_text())
        if any(record.get(k)!=v for k,v in identity.items()):raise ValueError('Object removal source changed.')
    else:
        plan=plan_edit(project,spec,png,report,generate);record={**identity,'plan':plan,'selection_source':'local_model'}
        if plan['decision']=='remove_extra_object_cluster':record['prompt']=edit_prompt(plan)
        write_json(path,record)
    return record if record['plan']['decision']=='remove_extra_object_cluster' else None


def expand_edit(project,spec,attempt,record):
    from comfy_execution.graph_utils import GraphBuilder
    from .storage import review_directory
    from .story import asset_seed
    from .render import flux_recipe
    from .generation_info import from_graph
    source=review_directory(project,spec)/f"attempt-{record['source_attempt']:02d}.png"
    if record['signature']!=spec['signature'] or hashlib.sha256(source.read_bytes()).hexdigest()!=record['source_sha256']:
        raise ValueError('Object removal graph source changed.')
    g=GraphBuilder();s=project['render_settings'];recipe=flux_recipe(s,spec,fresh=False)
    pixels=g.node('BookV2LoadCandidate',project=project,spec=spec,attempt=record['source_attempt']).out(0)
    model=g.node('UNETLoader',unet_name=s['flux_model'],weight_dtype='default').out(0)
    clip=g.node('CLIPLoader',clip_name=s['flux_encoder'],type='flux2',device='default').out(0)
    vae=g.node('VAELoader',vae_name=s['flux_vae']).out(0)
    prompt=edit_prompt(record['plan'])
    pos=g.node('CLIPTextEncode',clip=clip,text=prompt).out(0)
    cond=g.node('FluxGuidance',conditioning=pos,guidance=recipe['guidance']).out(0)
    cond=g.node('ReferenceLatent',conditioning=cond,latent=g.node('VAEEncode',pixels=pixels,vae=vae).out(0)).out(0)
    seed=asset_seed(spec['seed'],f'retry-{attempt}')
    sampled=g.node('SamplerCustomAdvanced',guider=g.node('BasicGuider',model=model,conditioning=cond).out(0),
        noise=g.node('RandomNoise',noise_seed=seed).out(0),sampler=g.node('KSamplerSelect',sampler_name='euler').out(0),
        sigmas=g.node('Flux2Scheduler',steps=recipe['steps'],width=1024,height=1024).out(0),
        latent_image=g.node('EmptyFlux2LatentImage',width=1024,height=1024,batch_size=1).out(0))
    decoded=g.node('VAEDecode',samples=sampled.out(0),vae=vae)
    info=from_graph(g.finalize(),'image_edit')
    reviewed=g.node('BookV2ReviewAsset',project=project,spec=spec,images=decoded.out(0),attempt=attempt,
                    actual_seed=seed,actual_prompt=prompt,generation_info=json.dumps(info))
    return {'result':(reviewed.out(0),),'expand':g.finalize()}


def apply_edit_review(project,spec,attempt,png,report,generate=None):
    from .storage import review_directory
    from .quality import json_model
    d=review_directory(project,spec);path=d/f'attempt-{attempt:02d}-strategy.json'
    if not path.exists() or json.loads(path.read_text()).get('strategy')!='object_removal':return report
    record=json.loads((d/f'attempt-{attempt:02d}-object-plan.json').read_text())
    source=(d/f"attempt-{record['source_attempt']:02d}.png").read_bytes()
    if record['signature']!=spec['signature'] or hashlib.sha256(source).hexdigest()!=record['source_sha256']:
        raise ValueError('Object removal preservation source changed.')
    schema=obj({'checks':obj({k:BOOL for k in PRESERVATION}),'uncertain':BOOL,'evidence':TEXT,'issues':{'type':'array','items':TEXT}})
    prompt=('Compare Image 1 before with Image 2 after this extra-object removal. Check the ENTIRE duplicate cluster '
            'was removed, including duplicate contents. The original object AND its contents must remain in their '
            'original location. Preserve character identities, poses, gaze, support and contacts, and the story action. '
            'Allow background fill only where removal reveals scenery and minor painted texture differences. '
            'Reject changed original objects, lost contents, altered character interactions or unresolved duplicates.\n'
            +json.dumps(record['plan'],ensure_ascii=False))
    result=(generate or json_model)(project['config']['ollama_url'],project['render_settings']['review_model'],
                                    prompt,schema,images=[source,png],think=False,num_predict=3000)
    import jsonschema
    jsonschema.validate(result,schema)
    result['accepted']=all(result['checks'].values()) and not result['uncertain'] and not result['issues']
    report['object_removal_review']=result
    if not result['accepted']:
        report['accepted']=False;report['review']['checks']['scene_matches']=False
        report['review']['issues'].extend(result['issues'] or ['Object removal did not preserve the original scene.'])
    return report

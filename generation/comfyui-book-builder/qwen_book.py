"""A saved-book Qwen edition, using verified canonical art and fresh scene renders."""
import copy
import hashlib
import json
from pathlib import Path

from .story import asset_specs, asset_seed, digest
from .storage import asset_path, checked_root, write_json, write_exclusive

RECIPE = 'edit2511_lightning8'
MODELS = {'edit_model':'qwen_image_edit_2511_fp8mixed.safetensors',
          'text_encoder':'qwen_2.5_vl_7b_fp8_scaled.safetensors', 'vae':'qwen_image_vae.safetensors',
          'edit_lora':'Qwen-Image-Edit-2511-Lightning-8steps-V1.0-bf16.safetensors'}


def enabled(project):
    return project.get('render_settings',{}).get('qwen_scene_recipe') == RECIPE


def read_source(filename):
    from .storage import books_root
    path = Path(filename).resolve()
    allowed = (books_root().resolve(), (books_root().parent/'codex/books').resolve())
    if not any(path.is_relative_to(base) for base in allowed):
        raise ValueError('Source project must be inside the existing book output directories.')
    project = json.loads(path.read_text())
    checked_root(project)
    return path, project


def valid_adopted_reference(project, spec):
    """Reuse approval only for byte-identical canonical assets of this exact book."""
    from .storage import valid_asset
    record = project.get('reference_adoptions',{}).get(spec['name'])
    if record is None or spec['kind']=='scene':
        return None
    path, source = read_source(record['project_file'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=record['project_sha256']:
        raise ValueError('Adopted reference source project changed.')
    if source.get('reference_adoptions'):
        raise ValueError('Chained reference adoption is unsupported; use the original reference project.')
    if any(source[key]!=project[key] for key in ('book','story','production')):
        raise ValueError('Adopted references belong to another book/design contract.')
    old = next(s for s in asset_specs(source) if s['name']==spec['name'])
    if old['kind']=='scene' or old['signature']!=record['source_signature'] or not valid_asset(source,old):
        raise ValueError('The original canonical reference lacks its matching approval.')
    expected = record['png_sha256']
    if any(hashlib.sha256(p.read_bytes()).hexdigest()!=expected for p in
           (asset_path(source,old['name']),asset_path(project,spec['name']))):
        raise ValueError('Adopted reference pixels/metadata changed.')
    return True


def prepare_edition(source_file, art_attempts=3):
    import folder_paths
    from .storage import approval_path, valid_asset
    from .story import validate_package
    from .preview import refresh_review_draft
    source_path, source = read_source(source_file)
    validate_package({'story':source['story'],'production':source['production']},
                     source['config']['page_count'],source['config']['max_characters'])
    if source.get('reference_adoptions'):
        raise ValueError('Use the original saved reference project, not a derived edition.')
    project = copy.deepcopy(source)
    source_hash=hashlib.sha256(source_path.read_bytes()).hexdigest()
    settings = {**source['render_settings'], **MODELS, 'renderer':'qwen',
        'qwen_scene_recipe':RECIPE, 'qwen_prompt_policy':4, 'reference_source_hash':source_hash,
        'edit_steps':8, 'edit_cfg':1.0,
        'scene_quality_policy':'concise_v1', 'independent_scene_review':1,
        'review_session_policy':1, 'scene_edit_version':6, 'art_attempts':art_attempts,
        'qa_version':'1.38-qwen-preview', 'quality_required':True}
    inventory={}
    for key, category in [('edit_model','diffusion_models'),('text_encoder','text_encoders'),
                          ('vae','vae'),('edit_lora','loras')]:
        path=folder_paths.get_full_path(category,settings[key])
        if not path or not Path(path).is_file(): raise ValueError('Missing local model: '+settings[key])
        stat=Path(path).stat();inventory[key]={'filename':settings[key],'size':stat.st_size,'mtime_ns':stat.st_mtime_ns}
    settings['model_files']=inventory
    project['render_settings']=settings
    root=Path(project['book_root'])/'renders'/digest(settings)[:12]
    project['render_root']=str(root)
    checked_root(project)
    project['reference_adoptions']={}
    old_specs=asset_specs(source)
    for spec in old_specs:
        if spec['kind']=='scene':continue
        if not valid_asset(source,spec):raise ValueError('Missing approved source reference: '+spec['name'])
        png=asset_path(source,spec['name']).read_bytes()
        project['reference_adoptions'][spec['name']]={'project_file':str(source_path),
            'project_sha256':source_hash,'source_signature':spec['signature'],
            'png_sha256':hashlib.sha256(png).hexdigest(),'kind':spec['kind']}
    # Only canonical references are copied. Their original provenance and
    # approvals remain intact; no scene pixels or approvals enter the new run.
    for spec in old_specs:
        if spec['kind']=='scene':continue
        write_exclusive(asset_path(project,spec['name']),asset_path(source,spec['name']).read_bytes())
        write_exclusive(approval_path(project,spec),approval_path(source,spec).read_bytes())
    for relative in ('visual-state',):
        base=checked_root(source)/relative
        if base.exists():
            for file in base.rglob('*'):
                if file.is_file():write_exclusive(root/relative/file.relative_to(base),file.read_bytes())
    write_json(root/'render-settings.json',settings)
    write_json(root/'story.json',project['story'])
    write_json(root/'project.json',project)
    write_json(root/'prepared-state-project.json',project)
    write_json(root/'asset-plan.json',asset_specs(project))
    write_json(root/'reference-adoptions.json',project['reference_adoptions'])
    refresh_review_draft(project)
    return project


def source_prompt(project, spec, reference_roles):
    from .render import cast_sheet_prompt
    from .state_ledger import state_brief
    from .garment_reference import garment_design
    scene = project['book']['cover'] if spec['name']=='cover.png' else next(
        p for p in project['book']['pages'] if spec['name']==f"pages/page-{p['page_number']:03d}.png")
    prompt=cast_sheet_prompt(project,spec) if spec.get('reference_layout')=='cast_guide' else spec['prompt']
    state=state_brief(project,scene)
    if state and state not in prompt:prompt+='\n'+state
    for prop in spec.get('props',[]):
        prompt+=f"\nDetached object: {prop['description']}. Design: {garment_design(project,prop)}. Depict one continuous object in its current location."
    return prompt+'\n'+'\n'.join(reference_roles)


def expand_scene(project, spec, attempt, feedback=''):
    from comfy_execution.graph_utils import GraphBuilder
    from .visual_library import entries, reference_instruction
    from .compact_prompt import compile_prompt
    graph=GraphBuilder();settings=project['render_settings']
    if spec['kind']!='scene':raise ValueError('Qwen scene recipe requires a scene asset.')
    clip=graph.node('CLIPLoader',clip_name=settings['text_encoder'],type='qwen_image',device='default')
    vae=graph.node('VAELoader',vae_name=settings['vae'])
    if spec.get('reference_layout')=='cast_guide':
        refs=[graph.node('BookV2ScaleGuide',project=project,spec=spec).out(0)]
    else:
        refs=[graph.node('BookV2LoadReference',project=project,asset_name=name,after='').out(0) for name in spec['references']]
    roles=[]
    for kind in ('prop','location'):
        if not any(entry['kind']==kind for entry in entries(project,spec)):continue
        refs.append(graph.node('BookV2VisualReferenceSheet',project=project,spec=spec,kind=kind).out(0))
        roles.append(reference_instruction(project,spec,kind,len(refs)))
    if not 1<=len(refs)<=3:raise ValueError('Qwen supports three image references; no reference was silently discarded.')
    prompt=source_prompt(project,spec,roles)
    if feedback:prompt+='\nRequired corrections for this fresh rendering: '+feedback[:2200]
    from .quality import expected_scene
    if expected_scene(project,spec)[0]:
        prompt=compile_prompt(project,spec,prompt,len(refs))
    seed=spec['seed'] if attempt==1 else asset_seed(spec['seed'],f'retry-{attempt}')
    unet=graph.node('UNETLoader',unet_name=settings['edit_model'],weight_dtype='default')
    lora=graph.node('LoraLoaderModelOnly',model=unet.out(0),lora_name=settings['edit_lora'],strength_model=1.0)
    model=graph.node('ModelSamplingAuraFlow',model=lora.out(0),shift=3.0)
    positive=graph.node('TextEncodeQwenImageEditPlus',clip=clip.out(0),vae=vae.out(0),prompt=prompt,
                        **{f'image{i+1}':ref for i,ref in enumerate(refs)})
    negative=graph.node('ConditioningZeroOut',conditioning=positive.out(0))
    latent=graph.node('VAEEncode',pixels=refs[0],vae=vae.out(0))
    sampler=graph.node('KSampler',model=model.out(0),positive=positive.out(0),negative=negative.out(0),
        latent_image=latent.out(0),seed=seed,steps=8,cfg=1.0,sampler_name='euler',scheduler='simple',denoise=1.0)
    decoded=graph.node('VAEDecode',samples=sampler.out(0),vae=vae.out(0))
    reviewed=graph.node('BookV2ReviewAsset',project=project,spec=spec,images=decoded.out(0),attempt=attempt,
                        actual_seed=seed,actual_prompt=prompt)
    return {'result':(reviewed.out(0),),'expand':graph.finalize()}


class BookV2QwenEdition:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'source_project':('STRING',), 'art_attempts':('INT',{'default':3,'min':1,'max':5})},
                'hidden':{'prompt':'PROMPT','extra_pnginfo':'EXTRA_PNGINFO'}}
    RETURN_TYPES=('BOOK_PROJECT',)
    RETURN_NAMES=('illustrated_book',)
    FUNCTION='run'
    CATEGORY='book builder/v2'
    DESCRIPTION='Reillustrate this saved story with Qwen Edit2511 Lightning8, retaining verified references and all review attempts.'
    @classmethod
    def IS_CHANGED(cls,**kwargs):return float('nan')
    def run(self,source_project,art_attempts,prompt=None,extra_pnginfo=None):
        from .render import expand_assets
        from .storage import save_workflow_checkpoint
        project=prepare_edition(source_project,art_attempts)
        save_workflow_checkpoint(checked_root(project),prompt,extra_pnginfo)
        return expand_assets(project,{'scene'})

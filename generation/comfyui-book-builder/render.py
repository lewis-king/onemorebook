"""Expand book stages into ordinary, sequential native ComfyUI operations."""
import copy

from .story import VERSION, asset_specs, digest
from .storage import asset_path, checked_root, valid_asset, write_json

DEFAULT_MODELS = {
    "image_model": "qwen_image_fp8_e4m3fn.safetensors",
    "edit_model": "qwen_image_edit_2509_fp8_e4m3fn.safetensors",
    "text_encoder": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
    "vae": "qwen_image_vae.safetensors",
    "image_lora": "Qwen-Image-Lightning-8steps-V1.0.safetensors",
}
FLUX_MODELS = {"flux_model": "flux2_dev_fp8mixed.safetensors",
               "flux_encoder": "mistral_3_small_flux2_bf16.safetensors", "flux_vae": "flux2-vae.safetensors"}
FLUX_TURBO_LORA = 'Flux_2-Turbo-LoRA_comfyui.safetensors'


def flux_recipe(settings, spec, *, fresh=True):
    if fresh and spec['kind']=='scene' and settings.get('flux_scene_recipe')=='turbo8_native':
        return {'steps':8,'guidance':2.5,'lora':settings.get('flux_turbo_lora',FLUX_TURBO_LORA)}
    return {'steps':settings['flux_steps'],'guidance':settings['flux_guidance'],'lora':None}


def configure_render(project, settings):
    import folder_paths
    from pathlib import Path
    project = copy.deepcopy(project)
    if settings.get('flux_scene_recipe')=='standard':
        settings={key:value for key,value in settings.items() if key!='flux_scene_recipe'}
    # The reference stage has its own immutable project; completed edit recipes
    # are reattached by the state-preparation stage from verified saved files.
    project.pop('state_edits',None)
    settings = {"builder_version": VERSION, "portrait_prompt_version": 2, "style_prompt_version": 2, "pose_guide_version": 3,
                "scene_edit_version": 6, "scale_repair_policy": 5, "candidate_recovery_policy": 1,
                "scene_reference_policy": 2, "scene_style_policy": 1, "scene_contract_prompt_policy": 1,
                "scene_context_policy": 3, **settings}
    if settings.get('renderer') == 'flux2' and settings.get('compact_prompt_policy', 0) >= 11:
        settings['positive_flux_prompts'] = 1
        settings.setdefault('duplicate_edit_policy', 1)
        settings.setdefault('object_edit_policy', 1)
        settings.setdefault('visual_reference_input_policy', 1)
    if project.get('art_plan'):
        settings['state_plan_version'] = project['art_plan']['version']
        settings['state_plan_hash'] = digest(project['art_plan'])
        settings['state_edit_policy'] = 2
        settings['state_scene_policy'] = 5
        settings['garment_reference_policy'] = 2
    if project.get('scene_contract'):
        settings['scene_contract_version'] = project['scene_contract']['version']
        settings['scene_contract_hash'] = digest(project['scene_contract'])
    if project.get('object_relations'):
        settings['object_relations_version'] = project['object_relations']['version']
        settings['object_relations_hash'] = digest(project['object_relations'])
    if project.get('visual_library'):
        if settings.get('renderer') != 'flux2':
            raise ValueError('Visual-library preview currently requires the installed Flux2.dev renderer.')
        settings['visual_library_version'] = project['visual_library']['version']
        settings['visual_library_hash'] = digest(project['visual_library'])
        settings['visual_reference_prompt_policy'] = 1
    if project.get('prop_groups'):
        settings['prop_group_policy'] = 1
        settings['prop_group_composition'] = 1
        settings['prop_group_hash'] = digest(project['prop_groups'])
    inventory = {}
    models = (("flux_model", "diffusion_models"), ("flux_encoder", "text_encoders"), ("flux_vae", "vae")) if settings.get("renderer") == "flux2" else (
        ("image_model", "diffusion_models"), ("edit_model", "diffusion_models"),
        ("text_encoder", "text_encoders"), ("vae", "vae"), ("image_lora", "loras"))
    if settings.get('renderer')=='flux2' and settings.get('flux_scene_recipe')=='turbo8_native':
        settings.setdefault('flux_turbo_lora',FLUX_TURBO_LORA)
        models += (('flux_turbo_lora','loras'),)
    for key, category in models:
        path = folder_paths.get_full_path(category, settings[key])
        if not path or not Path(path).is_file():
            raise ValueError(f"Missing {category} model: {settings[key]}. Install it or select an existing model.")
        stat = Path(path).stat()
        inventory[key] = {"filename": settings[key], "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    models_dir=getattr(folder_paths,'models_dir',None)
    if models_dir and settings.get('quality_required'):
        for label,relative in [('object_detector','grounding-dino-tiny/model.safetensors'),('segmentation','sams/sam_vit_b_01ec64.pth')]:
            path=Path(models_dir)/relative
            if path.is_file():
                stat=path.stat()
                inventory[label]={'filename':relative,'size':stat.st_size,'mtime_ns':stat.st_mtime_ns}
    settings["model_files"] = inventory
    project["render_settings"] = settings
    project["render_root"] = str(Path(project["book_root"]) / "renders" / digest(settings)[:12])
    root = checked_root(project)
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / "render-settings.json", settings)
    write_json(root / "story.json", project["story"])
    write_json(root / "asset-plan.json", asset_specs(project))
    write_json(root / "project.json", project)
    if project.get('art_plan'):
        write_json(root / 'visual-state-plan.json', project['art_plan'])
    if project.get('scene_contract'):
        write_json(root / 'scene-continuity.json', project['scene_contract'])
    if project.get('object_relations'):
        write_json(root / 'object-relations.json',project['object_relations'])
    if project.get('visual_library'):
        write_json(root / 'visual-library.json', project['visual_library'])
    if project.get('prop_groups'):
        write_json(root / 'prop-groups.json', project['prop_groups'])
    from .preview import refresh_review_draft
    refresh_review_draft(project)
    return project


def expand_assets(project, kinds):
    from comfy_execution.graph_utils import GraphBuilder
    graph = GraphBuilder()
    settings = project["render_settings"]
    specs = [s for s in asset_specs(project) if s["kind"] in kinds]
    pending = [s for s in specs if not valid_asset(project, s)]
    if not pending:
        return {"result": (project,), "expand": {}}

    if settings.get("quality_required"):
        # Each controller expands one native render and review. A rejected image
        # expands another controller; subsequent assets depend on final approval.
        after = ""
        for spec in pending:
            node = graph.node("BookV2RenderAsset", project=project, spec=spec, after=after)
            after = node.out(0)
        final = graph.node("BookV2StageComplete", project=project, after=after)
        return {"result": (final.out(0),), "expand": graph.finalize()}

    clip = graph.node("CLIPLoader", clip_name=settings["text_encoder"], type="qwen_image", device="default")
    vae = graph.node("VAELoader", vae_name=settings["vae"])
    models = {}
    if any(s["kind"] == "style" for s in pending):
        unet = graph.node("UNETLoader", unet_name=settings["image_model"], weight_dtype="default")
        lora = graph.node("LoraLoaderModelOnly", model=unet.out(0), lora_name=settings["image_lora"], strength_model=1.0)
        models["style"] = graph.node("ModelSamplingAuraFlow", model=lora.out(0), shift=3.1).out(0)
    if any(s["kind"] != "style" for s in pending):
        unet = graph.node("UNETLoader", unet_name=settings["edit_model"], weight_dtype="default")
        shifted = graph.node("ModelSamplingAuraFlow", model=unet.out(0), shift=3.0)
        models["edit"] = graph.node("CFGNorm", model=shifted.out(0), strength=1.0).out(0)

    after = ""
    for spec in specs:
        if valid_asset(project, spec):
            continue
        text = graph.node("BookV2Prompt", prompt=spec["prompt"], after=after)
        if spec["kind"] == "style":
            pos = graph.node("CLIPTextEncode", clip=clip.out(0), text=text.out(0))
            neg = graph.node("CLIPTextEncode", clip=clip.out(0), text="people, animals, faces, characters, text, lettering, watermark, photograph, 3d render")
            latent = graph.node("EmptySD3LatentImage", width=1024, height=1024, batch_size=1)
            model, steps, cfg = models["style"], settings["image_steps"], 1.0
        else:
            refs = {}
            for i, name in enumerate(spec["references"], 1):
                loaded = graph.node("BookV2LoadReference", project=project, asset_name=name, after=after)
                refs[f"image{i}"] = loaded.out(0)
            pos = graph.node("TextEncodeQwenImageEditPlus", clip=clip.out(0), vae=vae.out(0), prompt=text.out(0), **refs)
            neg = graph.node("TextEncodeQwenImageEditPlus", clip=clip.out(0), vae=vae.out(0), prompt="", **refs)
            # Every reference is exactly 1024-square, so both encoder and sampler
            # see matching geometry. Seed the sampler from the first reference.
            latent = graph.node("VAEEncode", pixels=refs["image1"], vae=vae.out(0))
            model, steps, cfg = models["edit"], settings["edit_steps"], settings["edit_cfg"]
        sample = graph.node("KSampler", model=model, positive=pos.out(0), negative=neg.out(0), latent_image=latent.out(0),
                            seed=spec["seed"], steps=steps, cfg=cfg, sampler_name="euler", scheduler="simple", denoise=1.0)
        decoded = graph.node("VAEDecode", samples=sample.out(0), vae=vae.out(0))
        saved = graph.node("BookV2SaveAsset", project=project, spec=spec, images=decoded.out(0))
        after = saved.out(0)
    final = graph.node("BookV2StageComplete", project=project, after=after)
    return {"result": (final.out(0),), "expand": graph.finalize()}


def cast_sheet_prompt(project, spec):
    """Keep identities separate from scene placement; the sheet is not a layout."""
    import re
    from .quality import expected_scene
    from .scale import cast_height
    from .story import scene_style_text
    from .state_ledger import scene_character_description
    ids,scene,_ = expected_scene(project,spec)
    scene_record = (project['book']['cover'] if spec['name']=='cover.png' else next(
        p for p in project['book']['pages'] if spec['name']==f"pages/page-{p['page_number']:03d}.png"))
    by_id={c['id']:c for c in project['book']['characters']}
    cast=[by_id[cid] for cid in ids]
    tallest=max(cast,key=cast_height)
    parts=[f"Create a complete children's picture-book illustration using the {len(cast)} characters in Image 1. "
           "The reference shows their canonical identities AND physical proportions on one common scale. Preserve both."]
    for c in cast:
        appearance=re.sub(r'\b\d+(?:\.\d+)?\s*cm\s*tall\b[.,;]?\s*','',
                          scene_character_description(project, scene_record, c),flags=re.I)
        parts.append(f"{c['name']}: {appearance}")
    ratios='; '.join(f"{tallest['name']} is about {cast_height(tallest)/cast_height(c):.1f} times as tall as {c['name']}"
                    for c in cast if c['id']!=tallest['id'])
    parts.append("When standing, including ears, "+ratios+". Keep those physical sizes even when they kneel, sit or jump; "
                 f"do not enlarge the smaller characters to match {tallest['name']}'s face level.")
    scene=re.sub(r'\s*\(\d+(?:\.\d+)?\s*cm\)','',scene,flags=re.I)
    parts.append("Scene: "+scene)
    if re.search(r'point\w*[^.!?]*\b(?:pebbles|stones)\b[^.!?]*\bon the ground\b',scene,re.I):
        parts.append("The pointing paw must aim DOWN toward those stones on the ground, not at another character's face.")
    parts.append("Use expressive natural poses and make each gesture aim at its stated target. Exactly these characters, each once. "
                 "Place them as this scene requires; the reference's positions are not scene instructions. "
                 "Replace its pale backdrop completely; no reference card rectangles or lineup. "
                 "No lettering, labels, panels, extra characters or extra limbs. "+scene_style_text(project))
    return '\n'.join(parts)


def expand_attempt(project, spec, attempt, feedback="", correction_attempt=None, scale_repair=False, pose_guide=False, duplicate_plan=None):
    if project['render_settings'].get('qwen_scene_recipe') == 'edit2511_lightning8' and spec['kind'] == 'scene':
        from .qwen_book import expand_scene
        return expand_scene(project, spec, attempt, feedback)
    from comfy_execution.graph_utils import GraphBuilder
    from .story import asset_seed
    graph = GraphBuilder()
    settings = project["render_settings"]
    seed = spec["seed"] if attempt == 1 else asset_seed(spec["seed"], f"retry-{attempt}")
    flux = settings["renderer"] == "flux2"
    if spec['kind'] == 'prop_group' and attempt == 1 and settings.get('prop_group_composition'):
        from .prop_groups import assemble_reference
        assembly = assemble_reference(project, spec)
        if assembly is not None:
            image = graph.node('BookV2LoadGroupAssembly', project=project, spec=spec)
            reviewed = graph.node('BookV2ReviewAsset', project=project, spec=spec, images=image.out(0),
                attempt=attempt, actual_seed=seed, actual_prompt='Measured source-image assembly. ' + spec['prompt'])
            return {'result': (reviewed.out(0),), 'expand': graph.finalize()}
    prompt = cast_sheet_prompt(project,spec) if flux and spec.get('reference_layout')=='cast_guide' else spec['prompt']
    correction_attempt = correction_attempt if flux and not scale_repair and spec['kind'] != 'state' else None
    scene_edit = correction_attempt is not None and (spec.get('reference_layout')=='cast_guide' or duplicate_plan is not None)
    size_edit = False
    source_review = {}
    if scene_edit and settings.get('scene_edit_version', 1) >= 4 and not pose_guide and not duplicate_plan:
        import json
        from .storage import review_directory
        from .retry_scope import scale_only_targets
        report_path = review_directory(project, spec) / f'attempt-{correction_attempt:02d}-review.json'
        if report_path.exists():
            source_review = json.loads(report_path.read_text())
            size_edit = bool(scale_only_targets(source_review))
    if scene_edit:
        from .quality import expected_scene
        ids,scene,prose=expected_scene(project,spec)
        count=len(ids)
        prompt=(f"Edit Image 1, the existing picture-book illustration. Preserve its {count} separate character "
                "identities, faces, clothing, illustration style and all features unaffected by the requested changes. "
                "Keep the existing composition and setting. Apply these specific changes: "+feedback[:2500])
        if size_edit:
            from .retry_scope import measured_scale_instructions
            prompt=(f"Edit Image 1, the existing illustration with exactly {count} characters. "
                    "Change only the specified character sizes and the immediate background revealed by that change. "
                    "Preserve all faces, expressions, outfits, body poses, props, setting and painted style. "
                    "Image 2 is the approved reference sheet for these SAME characters: use it to retain their "
                    "exact facial anatomy, current costumes and relative physical sizes. Keep each character once. "
                    "The reference sheet's positions are not a replacement scene layout. "
                    + measured_scale_instructions(project, source_review)
                    + " Keep every unaffected part of Image 1 unchanged. Artwork only, no lettering or labels.")
        elif settings.get('scene_edit_version',1)>=5:
            prompt=(f"Edit Image 1, the existing picture-book illustration with {count} separate characters. "
                    "Apply only the specific corrections below. Preserve each character's identity, face, "
                    "outfit and physical size, and preserve the existing painted style, setting and composition. "
                    "Keep every already-correct pose, prop and interaction unchanged. Change a pose or move "
                    "an object only where the correction requires it to depict the story action correctly. "
                    "Keep each character once. Artwork only: no lettering, captions, speech balloons or written words. "
                    "\nSpecific corrections: "+feedback[:2500]+
                    "\nStory action to preserve or repair where necessary: "+scene+
                    "\nRetain the original actor roles and required props. Preserve all unaffected parts of Image 1.")
        elif settings.get('scene_edit_version',1)>=2:
            prompt=(f"Edit Image 1 into the required picture-book moment below. Preserve exactly its {count} "
                    "separate character identities, faces, clothes and illustration style. Reposition the "
                    "characters and props and change their poses as required by the original action. "
                    "The original scene determines actor roles and props; correction suggestions "
                    "must not turn a required participant into a spectator or remove the shared object. "
                    "Keep natural anatomy and each character once. Artwork only: no lettering, captions, "
                    "speech balloons or written words.\nCorrection suggestions: "+feedback[:2500]+
                    "\nAuthoritative original scene: "+scene)
        if pose_guide:
            prompt=(f"Edit the picture-book illustration in Image 1, preserving its {count} separate characters, "
                    "exact faces, identifying clothes, physical sizes and painted illustration style. "
                    "Image 2 is ONLY an authored pose diagram for these SAME characters, not extra figures "
                    "or an art-style reference. Match its body poses and the explicit hand-to-object action. "
                    "Reposition the relevant prop and bend the actor as needed to make that action clear. "
                    "Render natural anatomy and expressive faces from Image 1; the geometric shapes of "
                    "Image 2 are structural instructions only. Keep the established scene and correct props. "
                    "The finished illustration must show: "+feedback[:2500])
            if settings.get('scene_edit_version',1)>=2:
                prompt += ("\nArtwork only: no lettering, captions, speech balloons or written words. "
                           "The original action controls the actor roles and required props, even if the "
                           "diagram or correction suggestions omit them. Original scene: "+scene+
                           "\nPreserve the established painted style.")
    elif correction_attempt is not None:
        import re
        prompt = re.sub(r"\b(Image|Picture)\s*(\d+)\b",
                        lambda m: f"{m[1]} {int(m[2])+1}", prompt, flags=re.IGNORECASE)
        reference_roles = ("The other images are approved object, garment-source or style references, "
                           "according to their roles in the original brief. They do not add subjects.\n"
                           if spec['kind'] in ('prop', 'location', 'prop_group') else
                           "The other images are canonical references for the SAME characters, not additional figures.\n")
        preserve = ("object designs, materials, colours, background and painted style" if spec['kind'] in
                    ('prop', 'location', 'prop_group') else "composition, identities, outfits and art style")
        prompt = ("Edit image 1, the previous illustration. Preserve its " + preserve +
                  " except for these required corrections: " + feedback[:2500] + "\n"
                  + reference_roles +
                  "The corrected result must fulfil this original brief:\n" + prompt)
    elif feedback:
        prompt += "\nApply these requested details: " + feedback[:2500]
    from .actor_labels import qualify_action_clause
    if not scale_repair:
        prompt = qualify_action_clause(project, spec, prompt)
    clip = graph.node("CLIPLoader", clip_name=settings["flux_encoder"] if flux else settings["text_encoder"],
                      type="flux2" if flux else "qwen_image", device="default")
    vae = graph.node("VAELoader", vae_name=settings["flux_vae"] if flux else settings["vae"])
    shared = flux and spec.get('reference_layout') == 'cast_guide' and not scale_repair
    if size_edit:
        refs = [graph.node("BookV2ScaleGuide", project=project, spec=spec).out(0)]
    elif scene_edit:
        refs = []
    elif shared:
        refs = [graph.node("BookV2ScaleGuide", project=project, spec=spec).out(0)]
    else:
        refs = [graph.node("BookV2LoadReference", project=project, asset_name=name, after="").out(0) for name in spec["references"]]
    if correction_attempt is not None:
        previous = graph.node("BookV2LoadCandidate", project=project, spec=spec, attempt=correction_attempt)
        refs.insert(0, previous.out(0))
    if pose_guide:
        if not scene_edit:
            raise ValueError('Pose guidance requires an existing shared-cast scene to edit.')
        refs.append(graph.node('BookV2LoadPoseGuide',project=project,spec=spec,attempt=attempt).out(0))
    from .scale import guide_cast
    if flux and not shared and not scale_repair and settings.get("scale_guide", False) and guide_cast(project, spec):
        guide = graph.node("BookV2ScaleGuide", project=project, spec=spec)
        refs.append(guide.out(0))
        prompt += (f"\nImage {len(refs)} is a SIZE GUIDE showing these same characters together at their exact relative heights. "
                   "Match those physical proportions in the final scene. It does not add any characters. "
                   "Use the individual portraits for fine identity details; use the size guide for scale only, not its pose or background.")
    prepared = None
    reference_roles = {}
    if scale_repair:
        prepared=graph.node('BookV2LoadRepair',project=project,spec=spec,attempt=attempt)
        refs=[prepared.out(0)]
        prompt=('Repair only the masked background in this picture-book illustration. Continue the existing '
                'painted surroundings seamlessly through the blurred area, following the scenery immediately '
                'outside each masked region: continue sky into sky, foliage into foliage and ground into ground. '
                'Complete the matching surfaces of any existing partially visible objects at mask edges. '
                'Preserve every character, their exact sizes, positions, faces, colours and clothing. '
                'Do not invent extra figures, faces, new objects or lettering. '
                'Match the surrounding brush texture, palette and lighting. '+project['book']['visual_bible']['style'])
    if spec['kind'] == 'state' and spec.get('edit_mode') != 'clothing_addition':
        prepared = graph.node('BookV2LoadStateEdit', project=project, spec=spec)
        refs = [prepared.out(2)]
        if spec.get('edits'):
            from .state_edit import edit_prompt
            prompt = edit_prompt(spec)
    if spec['kind'] == 'scene' and project.get('art_plan') and not duplicate_plan:
        from .state_ledger import state_brief
        from .state_assets import prop_reference
        scene = project['book']['cover'] if spec['name'] == 'cover.png' else next(
            p for p in project['book']['pages'] if spec['name'] == f"pages/page-{p['page_number']:03d}.png")
        current_state = state_brief(project, scene)
        if current_state and settings.get('state_scene_policy',0)>=4 and not scale_repair:
            # The actual desired surface comes before secondary detail. Keep a
            # single copy, including when the saved scene brief already has it.
            prompt = current_state.strip()+'\n'+prompt.replace(current_state,'')
        elif current_state and current_state not in prompt:
            prompt += current_state
        for prop in spec.get('props', []):
            from .state_ledger import is_addition
            change=next(c for c in project['art_plan']['ledger']['changes'] if c['id']==prop['source_change_id'])
            if (settings.get('garment_reference_policy',0)>=2
                    or (is_addition(change) and settings.get('garment_reference_policy',0)>=1)):
                from .garment_reference import garment_design
                detail=garment_design(project,prop)
                prompt += (f"\nDetached object: {prop['description']}. Approved garment design: {detail}. "
                           "Draw this single garment at its natural size in its required detached location. "
                           "It may drape naturally over that support. Its former wearer follows the current "
                           "character reference and clothing state above.")
                continue
            _, detail = prop_reference(project, prop)
            refs.append(graph.node('BookV2LoadPropDetail', project=project, prop=prop).out(0))
            role = 'worn garment portrait reference' if is_addition(change) else 'magnified DETAIL REFERENCE'
            reference_roles[len(refs)] = f"{role} for {prop['description']}. Actual source design: {detail}."
            prompt += (f"\nImage {len(refs)} is a {role} for {prop['description']}, "
                       f"the same detached costume item in this scene. Actual source design: {detail}. "
                       "Match its design at the object's natural scale. "
                       "Surrounding fabric is reference context only, not part of the detached prop.")
        if len(refs) > (6 if flux else 3):
            raise ValueError('This scene exceeds the selected model reference budget; no reference was silently dropped.')
    if spec['kind'] == 'scene' and spec.get('visual_references') and not scale_repair and not duplicate_plan:
        from .visual_library import entries, reference_instruction
        from .visual_library import separate_reference_inputs
        separate = separate_reference_inputs(project, spec, len(refs))
        if separate:
            for item in separate:
                refs.append(graph.node('BookV2LoadReference', project=project, asset_name=item['asset_name'], after='').out(0))
                reference_roles[len(refs)] = item['role']
                prompt += f'\nImage {len(refs)}: '+item['role']
        else:
            for kind in ('prop', 'location'):
                if not any(e['kind'] == kind for e in entries(project, spec)):
                    continue
                refs.append(graph.node('BookV2VisualReferenceSheet', project=project, spec=spec, kind=kind).out(0))
                instruction=reference_instruction(project, spec, kind, len(refs))
                reference_roles[len(refs)]=instruction.removeprefix(f'Image {len(refs)} is ')
                prompt += '\n' + instruction
        if len(refs) > 6:
            raise ValueError('Visual references exceed the Flux2 preview budget; no reference was dropped.')
    if flux:
        if duplicate_plan is not None:
            from .duplicate_edit import edit_prompt
            from .storage import review_directory
            import hashlib
            source = review_directory(project, spec)/f'attempt-{correction_attempt:02d}.png'
            if (duplicate_plan['signature'] != spec['signature']
                    or duplicate_plan['source_attempt'] != correction_attempt
                    or hashlib.sha256(source.read_bytes()).hexdigest() != duplicate_plan['source_sha256']):
                raise ValueError('Duplicate-removal graph does not match its saved source.')
            character = next(c for c in project['book']['characters']
                             if c['id'] == duplicate_plan['plan']['character_id'])
            prompt = duplicate_plan.get('prompt') or edit_prompt(duplicate_plan['plan'], character)
            # The existing illustration contains all designs and interactions.
            # Supplying the cast sheet again can reintroduce the removed copy.
            refs = [previous.out(0)]
        if settings.get('positive_flux_prompts'):
            # These are fixed renderer boilerplate, never arbitrary story text.
            prompt = prompt.replace('Artwork only, no lettering or labels.', 'Unmarked artwork surfaces.')
            prompt = prompt.replace('Artwork only: no lettering, captions, speech balloons or written words.',
                                    'Unmarked artwork surfaces.')
            prompt = prompt.replace('Do not invent extra figures, faces, new objects or lettering.',
                                    'Fill each exposed region with its surrounding scenery and surface texture.')
        if (settings.get('compact_prompt_policy',0)>=1 and spec['kind']=='scene'
                and (spec.get('reference_layout')=='cast_guide' or
                     (settings.get('compact_prompt_policy',0)>=7 and len(spec['references'])==1))
                and not scene_edit and not scale_repair and not pose_guide):
            from .flux_prompt import compile_prompt
            prompt=compile_prompt(project,spec,prompt,len(refs),reference_roles=reference_roles,feedback=feedback)
        model = graph.node("UNETLoader", unet_name=settings["flux_model"], weight_dtype="default")
        recipe=flux_recipe(settings,spec,fresh=not scene_edit and not scale_repair and not pose_guide)
        if recipe['lora']:
            model=graph.node('LoraLoaderModelOnly',model=model.out(0),lora_name=recipe['lora'],strength_model=1.0)
        pos = graph.node("CLIPTextEncode", clip=clip.out(0), text=prompt)
        cond = graph.node("FluxGuidance", conditioning=pos.out(0), guidance=recipe['guidance']).out(0)
        for pixels in refs:
            encoded = graph.node("VAEEncode", pixels=pixels, vae=vae.out(0))
            cond = graph.node("ReferenceLatent", conditioning=cond, latent=encoded.out(0)).out(0)
        guider = graph.node("BasicGuider", model=model.out(0), conditioning=cond)
        if prepared is not None:
            encoded=graph.node('VAEEncode',pixels=prepared.out(2) if spec['kind']=='state' else prepared.out(0),vae=vae.out(0))
            latent=graph.node('SetLatentNoiseMask',samples=encoded.out(0),mask=prepared.out(1)).out(0)
        else:
            latent=graph.node('EmptyFlux2LatentImage',width=1024,height=1024,batch_size=1).out(0)
        sample = graph.node("SamplerCustomAdvanced", guider=guider.out(0),
            noise=graph.node("RandomNoise", noise_seed=seed).out(0),
            sampler=graph.node("KSamplerSelect", sampler_name="euler").out(0),
            sigmas=graph.node("Flux2Scheduler", steps=recipe['steps'], width=1024, height=1024).out(0),
            latent_image=latent)
    else:
        is_style = spec["kind"] == "style"
        model = graph.node("UNETLoader", unet_name=settings["image_model"] if is_style else settings["edit_model"], weight_dtype="default")
        if is_style:
            model = graph.node("LoraLoaderModelOnly", model=model.out(0), lora_name=settings["image_lora"], strength_model=1.0)
        model = graph.node("ModelSamplingAuraFlow", model=model.out(0), shift=3.1 if is_style else 3.0)
        if is_style:
            pos = graph.node("CLIPTextEncode", clip=clip.out(0), text=prompt)
            neg = graph.node("CLIPTextEncode", clip=clip.out(0), text="people, animals, faces, text, lettering")
            latent = graph.node("EmptySD3LatentImage", width=1024, height=1024, batch_size=1)
        else:
            model = graph.node("CFGNorm", model=model.out(0), strength=1.0)
            rr = {f"image{i+1}": image for i, image in enumerate(refs)}
            pos = graph.node("TextEncodeQwenImageEditPlus", clip=clip.out(0), vae=vae.out(0), prompt=prompt, **rr)
            neg = graph.node("TextEncodeQwenImageEditPlus", clip=clip.out(0), vae=vae.out(0), prompt="", **rr)
            latent = graph.node("VAEEncode", pixels=refs[0], vae=vae.out(0))
            if prepared is not None:
                latent = graph.node('SetLatentNoiseMask', samples=latent.out(0), mask=prepared.out(1))
        sample = graph.node("KSampler", model=model.out(0), positive=pos.out(0), negative=neg.out(0), latent_image=latent.out(0),
            seed=seed, steps=settings["image_steps"] if is_style else settings["edit_steps"],
            cfg=1.0 if is_style else settings["edit_cfg"], sampler_name="euler", scheduler="simple", denoise=1.0)
    decoded = graph.node("VAEDecode", samples=sample.out(0), vae=vae.out(0))
    if prepared is not None:
        decoded=graph.node('ImageCompositeMasked',destination=prepared.out(0),source=decoded.out(0),
                           x=0,y=0,resize_source=False,mask=prepared.out(1))
    from .generation_info import from_graph
    import json
    method = ('image_edit' if scene_edit or scale_repair or pose_guide or spec['kind'] == 'state'
              else 'reference_generation' if refs else 'text_to_image')
    generation_info = from_graph(graph.finalize(), method)
    reference_images = []
    for ref in refs:
        node = graph.finalize().get(ref[0], {})
        if node.get('class_type') == 'BookV2LoadReference':
            name = node['inputs']['asset_name']
            reference_images.append({'path':name, 'label':name})
        elif node.get('class_type') == 'BookV2ScaleGuide':
            from .storage import review_directory
            name = (review_directory(project,spec)/'size-guide.png').relative_to(checked_root(project)).as_posix()
            reference_images.append({'path':name, 'label':'Character identity and relative size reference'})
        else:
            break
    if len(reference_images) == len(refs):
        generation_info['reference_images'] = reference_images
    reviewed = graph.node("BookV2ReviewAsset", project=project, spec=spec, images=decoded.out(0),
                          attempt=attempt, actual_seed=seed, actual_prompt=prompt,
                          generation_info=json.dumps(generation_info))
    return {"result": (reviewed.out(0),), "expand": graph.finalize()}

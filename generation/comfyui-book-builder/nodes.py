import copy
import json
import logging
import hashlib
from pathlib import Path
import urllib.error
import urllib.request

from .story import (VERSION, DEFAULT_STYLE, DEFAULT_IDEA, asset_specs, book_schema, digest,
                    validate_story, validate_package, make_render_plan, production_schema, writing_prompt)
from .storage import (asset_path, books_root, image_record, save_asset, valid_asset, write_json,
                      write_exclusive, image_bytes, review_directory, publish_reviewed_asset)
from .render import DEFAULT_MODELS, FLUX_MODELS, configure_render, expand_assets, expand_attempt
from .quality import QA_VERSION, STORY_QA_VERSION, DEFAULT_REVIEW_MODEL, review_story, review_art, parse_model_json
from .planning import DEFAULT_WRITER_MODEL, outline_schema, outline_prompt, review_outline
from .reasoning import story_reasoning_options
from .export import export_book

CATEGORY = "Children's Book v2"


def ollama_generate(url, model, prompt, schema, seed):
    for attempt in range(3):
        try:
            return _ollama_generate_once(url,model,prompt,schema,seed)
        except (urllib.error.URLError,TimeoutError,ConnectionError,RuntimeError) as exc:
            if attempt==2:
                raise
            logging.warning('Book v2: local writer request failed; retrying (%s/3): %s',attempt+1,exc)


def _ollama_generate_once(url, model, prompt, schema, seed):
    import comfy.model_management as mm
    payload = {
        "model": model, "messages": [
            {'role':'system','content':"You are a children's picture-book author and art director. Plan causality, continuity and page actions carefully, then return only the requested valid JSON."},
            {'role':'user','content':prompt+'\nJSON schema for your complete answer (fill every field with real content, never placeholders):\n'+json.dumps(schema)}],
        "format": schema, "stream": True, "think": story_reasoning_options(model).get('think', False), "keep_alive": 0,
        "options": {"seed": seed % (2 ** 31), "temperature": 0.7, "num_ctx": 32768, "num_predict": 24576},
    }
    request = urllib.request.Request(url.rstrip("/") + "/api/chat", json.dumps(payload).encode(), {"Content-Type": "application/json"})
    chunks = []
    complete = False
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            for line in response:
                mm.throw_exception_if_processing_interrupted()
                if not line.strip():
                    continue
                part = json.loads(line)
                if part.get("error"):
                    raise RuntimeError(part["error"])
                chunks.append(part.get("message", {}).get("content", ""))
                if sum(map(len, chunks)) > 200_000:
                    raise ValueError("Story response exceeds the maximum size.")
                if part.get("done"):
                    complete = True
                    if part.get("done_reason") == "length":
                        logging.warning("Book v2: writer reached its token limit; checking the response and retrying if incomplete.")
        if not complete:
            raise RuntimeError("Ollama disconnected before finishing the story.")
        return "".join(chunks)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Ollama returned HTTP {exc.code}: {exc.read(2000).decode(errors='replace')}") from exc
    finally:
        # Also release the model if generation was interrupted or malformed.
        unload = urllib.request.Request(url.rstrip("/") + "/api/generate",
            json.dumps({"model": model, "keep_alive": 0}).encode(), {"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(unload, timeout=15).close()
        except (OSError, urllib.error.URLError):
            logging.warning("Book v2: could not confirm Ollama unload; check its running models before retrying.")


def story_draft(root, attempt, config, prompt, schema, seed):
    path = root / "quality/story" / f"attempt-{attempt+1:02d}-draft.txt"
    if path.exists():
        return path.read_text()
    raw = ollama_generate(config["ollama_url"], config["ollama_model"], prompt, schema, seed)
    write_exclusive(path, raw.encode())
    return raw


def story_state_preflight(root, package, config):
    """Compile consequential visual changes before accepting a generated draft."""
    if not config.get('visual_state_preflight'):
        return None
    from .state_ledger import compile_plan
    project = {'book_root': str(root), 'config': config, 'story': package['story'],
               'book': validate_package(package, config['page_count'], config['max_characters'])}
    return compile_plan(project, config['review_model'])


def editorial_gate(root, attempt, package, config):
    from .scale import cast_height
    if any(cast_height(c) is None for c in package["production"]["characters"]):
        raise ValueError("Every production character needs height_cm (normal full-body height in centimetres) for the cast size guide.")
    path = root / "quality/story" / f"attempt-{attempt+1:02d}.json"
    if path.exists():
        record = json.loads(path.read_text())
        if record["package"] != package:
            raise ValueError("Saved editorial draft differs; choose a fresh seed.")
        approval = record["approval"]
    else:
        approval = review_story(package, config)
        write_json(path, {"package": package, "approval": approval})
    if not approval["accepted"]:
        raise ValueError("Editorial review failed: " + json.dumps(approval["review"]))
    story_state_preflight(root, package, config)
    return approval


def narrative_outline(root, config):
    import jsonschema
    from .planning import outline_retry_prompt
    path = root / "outline.json"
    if path.exists():
        return json.loads(path.read_text())
    schema = outline_schema(config["page_count"])
    directory = root / "quality/outline/policy-2"
    previous = None
    feedback = ""
    # A completed legacy failure is evidence for a new approach, not permission
    # to overwrite its drafts or silently increase this policy's retry budget.
    old = root / "quality/outline" / f"attempt-{config['story_attempts']:02d}.txt"
    old_review = old.with_name(old.stem + '-review.json')
    if old.exists() and old_review.exists():
        report = json.loads(old_review.read_text())
        if report.get('accepted') is False:
            try:
                previous = parse_model_json(old.read_text())
            except ValueError:
                previous = None
            feedback = json.dumps(report.get('review', {}))
    for attempt in range(config["story_attempts"]):
        reset = attempt % 2 == 0
        prompt = outline_retry_prompt(config, previous, feedback, reset=reset)
        request = {'policy': 2, 'strategy': 'new_approach' if reset else 'revise',
                   'prompt': prompt, 'schema': schema, 'seed': config['seed'] + attempt,
                   'writer': config['ollama_model'], 'reviewer': config['review_model']}
        prefix = directory / f"attempt-{attempt+1:02d}"
        request_path = prefix.with_name(prefix.name + '-request.json')
        if request_path.exists():
            saved = json.loads(request_path.read_text())
            # A newer editor can reconsider saved prose without pretending it
            # was generated from today's feedback. Keep its original request.
            same_settings = all(saved.get(k) == value for k, value in request.items() if k != 'prompt')
            if not same_settings or not saved.get('prompt', '').startswith(outline_prompt(config)):
                raise ValueError('Saved outline request differs; preserve it and use a new seed.')
            request = saved
            prompt = saved['prompt']
        else:
            write_json(request_path, request)
        draft_path = prefix.with_suffix('.txt')
        if draft_path.exists():
            raw = draft_path.read_text()
        else:
            raw = ollama_generate(config["ollama_url"], config["ollama_model"], prompt, schema, request['seed'])
            write_exclusive(draft_path, raw.encode())
        try:
            outline = parse_model_json(raw)
            jsonschema.validate(outline, schema)
            if [b["page"] for b in outline["beats"]] != list(range(1, config["page_count"] + 1)):
                raise ValueError('Outline beats must be consecutively numbered.')
            previous = outline
            review_path = prefix.with_name(prefix.name + '-review-v2.json')
            if review_path.exists():
                review = json.loads(review_path.read_text())
            else:
                review = review_outline(outline, config)
                write_json(review_path, review)
            if not review['accepted']:
                raise ValueError('Outline editor: ' + json.dumps(review['review']))
            write_json(path, outline)
            return outline
        except (ValueError, jsonschema.ValidationError) as exc:
            feedback = str(exc)
            logging.warning('Book v2: outline %s rejected (%s): %s', attempt + 1, request['strategy'], exc)
    raise ValueError(f'Could not plan a valid narrative outline. Drafts: {directory}')


def story_review_sources(config):
    """Saved failed drafts can also be rechecked after an editorial bug fix."""
    records = []
    for directory in books_root().glob(f"book-{config['seed']}-*"):
        plan = directory/'plan.json'
        if plan.exists():
            records.append((plan,json.loads(plan.read_text())))
            continue
        drafts = sorted((directory/'quality/story').glob('attempt-*.json'),reverse=True)
        if not drafts:
            continue
        source = drafts[0]
        record = json.loads(source.read_text())
        if record.get('approval',{}).get('package_hash') != digest(record.get('package')):
            continue
        settings = directory/'story-config.json'
        if settings.exists():
            previous = json.loads(settings.read_text())
        else:
            # Legacy failed runs saved the exact API graph but no standalone
            # config. Reconstruct ONLY a QA-version change and require its full
            # digest to match the directory; never guess unrelated settings.
            previous = {**config,'qa_version':record['approval'].get('qa_version')}
        if directory.name != f"book-{previous['seed']}-{digest(previous)[:10]}":
            continue
        records.append((source,{'config':previous,'package':record['package']}))
    return sorted(records,key=lambda pair:pair[0].stat().st_mtime,reverse=True)


def reuse_story_after_review_change(root, config):
    """Recheck the same saved story when only the editorial rules have changed."""
    def comparable(value):
        return {k:v for k,v in value.items() if k not in ('qa_version','prose_format','max_ensemble_pages')}
    for source,record in story_review_sources(config):
        if source.is_relative_to(root) or comparable(record['config'])!=comparable(config):
            continue
        package=record['package']
        original_hash=digest(package)
        if config.get('prose_format') in ('plain-v1','plain-v2') and not config.get('story_override_hash'):
            from .story import plain_generated_prose
            package=plain_generated_prose(package)
            if config['prose_format']=='plain-v2':
                from .prose import punctuate_generated_prose
                package=punctuate_generated_prose(package,config,root)
        validate_package(package,config['page_count'],config['max_characters'])
        review_path=root/'quality/story-reuse'/f"{digest(package)[:16]}.json"
        if review_path.exists():
            approval=json.loads(review_path.read_text())
        else:
            approval=review_story(package,config)
            write_json(review_path,approval)
        if approval.get('package_hash')!=digest(package) or approval.get('qa_version')!=config['qa_version']:
            raise ValueError('Saved story recheck does not match this package or editorial version.')
        state_error = None
        if approval.get('accepted'):
            from .state_ledger import StatePlanningError
            try:
                story_state_preflight(root, package, config)
            except StatePlanningError as exc:
                state_error = str(exc)
        if approval.get('accepted') and not state_error:
            write_json(root/'story-quality.json',approval)
            write_json(root/'plan.json',{'config':config,'package':package})
            write_json(root/'story-reused-from.json',{'source':str(source),'source_package_hash':original_hash,
                                                    'package_hash':digest(package),'prose_format':config.get('prose_format')})
            logging.info('Book v2: preserved saved story after passing the updated editorial checks.')
            return True
        revision = {'source':str(source),'package':package,'review':approval}
        if state_error:
            revision['visual_state_failure'] = state_error
        write_json(root/'story-revision-source.json',revision)
        logging.info('Book v2: previous story needs revision under updated editorial checks; preserving it and revising the flagged defects.')
        return False
    return False


class BookV2Story:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "story_idea": ("STRING", {"multiline": True, "default": DEFAULT_IDEA, "tooltip": "Your premise, themes and special requests. Leave blank for a completely invented idea."}),
            "age_range": ("STRING", {"default": "4–6"}),
            "page_count": ("INT", {"default": 12, "min": 2, "max": 24}),
            "max_characters": ("INT", {"default": 4, "min": 1, "max": 6, "tooltip": "Maximum total named cast. A scene can show at most three characters."}),
            "art_style": ("STRING", {"multiline": True, "default": DEFAULT_STYLE}),
            "seed": ("INT", {"default": 20260907, "min": 0, "max": 2 ** 53 - 1, "control_after_generate": True, "tooltip": "Randomize for a new book. Fixed seed and unchanged settings resume an interrupted book."}),
            "ollama_url": ("STRING", {"default": "http://127.0.0.1:11434"}),
            "ollama_model": ("STRING", {"default": DEFAULT_WRITER_MODEL}),
        }, "optional": {"story_json": ("STRING", {"multiline": True, "default": "", "tooltip": "Optional edited story.json from a previous v2 book. Blank writes a new story with Ollama."}),
                        "review_model": ("STRING", {"default": DEFAULT_REVIEW_MODEL}),
                        "story_attempts": ("INT", {"default": 5, "min": 1, "max": 5}),
                        "plan_visual_state": ("BOOLEAN", {"default": False,
                            "tooltip": "Development preview: check visual-state planning before accepting the story; generated drafts automatically retry on unresolved changes."}),
                        "max_ensemble_pages": ("INT", {"default": -1, "min": -1, "max": 24,
                            "tooltip": "Maximum pages showing three characters together. Use 2 for varied framing in a 12-page book; -1 leaves this unrestricted."})},
                "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"}}

    RETURN_TYPES = ("BOOK_PROJECT", "STRING")
    RETURN_NAMES = ("book_project", "story_json")
    FUNCTION = "write"
    CATEGORY = CATEGORY
    DESCRIPTION = "Write and validate the complete story before any rendering. Saved stories resume with a fixed seed."

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def write(self, story_idea, age_range, page_count, max_characters, art_style, seed, ollama_url, ollama_model, story_json="", review_model=DEFAULT_REVIEW_MODEL, story_attempts=5, prompt=None, extra_pnginfo=None, max_ensemble_pages=-1, plan_visual_state=False):
        import comfy.model_management as mm
        config = {"version": VERSION, "story_idea": story_idea, "age_range": age_range,
                  "page_count": page_count, "max_characters": max_characters, "art_style": art_style,
                  "seed": seed, "ollama_url": ollama_url, "ollama_model": ollama_model,
                  "story_override_hash": digest(story_json) if story_json.strip() else None,
                  "review_model": review_model, "story_attempts": story_attempts, "qa_version": STORY_QA_VERSION,
                  "prose_format": None if story_json.strip() else "plain-v2"}
        if plan_visual_state:
            from .state_ledger import STATE_VERSION
            config['visual_state_preflight'] = STATE_VERSION
        if max_ensemble_pages >= 0:
            config['max_ensemble_pages'] = max_ensemble_pages
        root = books_root() / f"book-{seed}-{digest(config)[:10]}"
        write_json(root/'story-config.json',config)
        from .storage import save_workflow_checkpoint
        save_workflow_checkpoint(root, prompt, extra_pnginfo)
        plan_file = root / "plan.json"
        if not plan_file.exists():
            reuse_story_after_review_change(root,config)
        if plan_file.exists():
            record = json.loads(plan_file.read_text())
            if record["config"] != config:
                raise ValueError("Saved book settings mismatch; choose a new seed.")
            book = validate_package(record["package"], page_count, max_characters)
            package = record["package"]
            approval = json.loads((root / "story-quality.json").read_text())
            if approval.get("accepted") is not True or approval.get("package_hash") != digest(package):
                raise ValueError("Saved story has no matching editorial approval.")
            logging.info("Book v2: resuming saved story %s", book["title"])
        elif story_json.strip():
            canonical = validate_story(json.loads(story_json), page_count, max_characters)
            mm.unload_all_models()
            mm.soft_empty_cache()
            prompt = ("Create private production data for this existing children's book. Preserve all story text, "
                      "character names and appearance. Use exactly the metadata.characters cast, stable lowercase IDs, "
                      "exactly one main character, detailed immutable appearances matching the story, and an empty "
                      "character-free style_reference_prompt. cover_character_ids lists at most three IDs. "
                      "Each production character also needs a numeric height_cm for its normal full-body height, matching its appearance. "
                      "The main character must match isMainCharacterPresent and mainCharacterDescriptivePrompt.\n" + story_json)
            for attempt in range(story_attempts):
                raw = story_draft(root, attempt, config, prompt, production_schema(page_count, max_characters), seed + attempt)
                try:
                    package = {"story": canonical, "production": parse_model_json(raw)}
                    book = validate_package(package, page_count, max_characters)
                    approval = editorial_gate(root, attempt, package, config)
                    break
                except ValueError as exc:
                    from .state_ledger import StatePlanningError
                    if isinstance(exc, StatePlanningError):
                        # An explicitly supplied story is immutable. Rewriting
                        # its private cast cannot resolve ambiguous prose.
                        raise
                    logging.warning("Book v2: production validation failed (attempt %s/%s): %s", attempt + 1, story_attempts, exc)
                    prompt += f"\nPrevious attempt failed: {exc}. Correct it without changing the story."
            else:
                raise ValueError("Could not create a valid production plan for the supplied story.")
            write_json(root / "story-quality.json", approval)
            write_json(plan_file, {"config": config, "package": package})
        else:
            mm.unload_all_models()
            mm.soft_empty_cache()
            revision_file = root/'story-revision-source.json'
            if revision_file.exists():
                revision = json.loads(revision_file.read_text())
                base_prompt = (writing_prompt(config) + "\nRevise this saved book to correct the editor's specific defects. "
                    "Preserve its cast, canonical designs and successful prose/events wherever possible. Return the entire "
                    "corrected story and production envelope.\n" + json.dumps(revision,ensure_ascii=False))
            else:
                outline = narrative_outline(root, config)
                base_prompt = writing_prompt(config) + "\nDevelop this private narrative outline into the complete book, refining it if needed:\n" + json.dumps(outline,ensure_ascii=False)
            prompt = base_prompt
            error = ""
            for attempt in range(story_attempts):
                mm.throw_exception_if_processing_interrupted()
                logging.info("Book v2: writing story (attempt %s/%s)", attempt + 1, story_attempts)
                raw = story_draft(root, attempt, config, prompt, book_schema(page_count, max_characters), seed + attempt)
                try:
                    from .story import plain_generated_prose
                    package = plain_generated_prose(parse_model_json(raw))
                    book = validate_package(package, page_count, max_characters)
                    from .prose import punctuate_generated_prose
                    package = punctuate_generated_prose(package,config,root)
                    book = validate_package(package, page_count, max_characters)
                    package["story"]["id"] = f"story_{seed}_{digest(config)[:10]}"
                    approval = editorial_gate(root, attempt, package, config)
                    break
                except (ValueError, json.JSONDecodeError) as exc:
                    error = str(exc)
                    logging.warning("Book v2: story validation failed (attempt %s/%s): %s", attempt + 1, story_attempts, error)
                    prompt = base_prompt + f"\nYour previous response failed validation: {error}\nCorrect the following JSON and return the entire valid book:\n{raw[:50000]}"
            else:
                raise ValueError(f"Story failed validation after {story_attempts} attempts: {error}. Drafts: {root / 'quality/story'}")
            write_json(root / "story-quality.json", approval)
            write_json(plan_file, {"config": config, "package": package})
        write_json(root / "story.json", package["story"])
        project = {"book_root": str(root), "config": config, "book": book,
                   "story": package["story"], "production": package["production"], "story_quality": approval}
        art_plan = story_state_preflight(root, package, config)
        if art_plan is not None:
            project['art_plan'] = art_plan
        return project, json.dumps(package["story"], ensure_ascii=False, indent=2)


class BookV2References:
    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        inputs = {"book_project": ("BOOK_PROJECT",)}
        for key, category in (("image_model", "diffusion_models"), ("edit_model", "diffusion_models"),
                              ("text_encoder", "text_encoders"), ("vae", "vae"), ("image_lora", "loras")):
            inputs[key] = (folder_paths.get_filename_list(category), {"default": DEFAULT_MODELS[key]})
        inputs.update({
            "image_steps": ("INT", {"default": 8, "min": 1, "max": 50, "tooltip": "Style reference steps, with the selected Qwen Image Lightning LoRA."}),
            "edit_steps": ("INT", {"default": 40, "min": 1, "max": 80, "tooltip": "Character and scene steps. Default 40 uses the base Edit-2509 model without a mismatched LoRA."}),
            "edit_cfg": ("FLOAT", {"default": 4.0, "min": 1.0, "max": 10.0, "step": 0.1}),
        })
        optional = {
            "renderer": (["flux2", "qwen"], {"default": "flux2"}),
            "flux_steps": ("INT", {"default": 28, "min": 1, "max": 80}),
            "flux_guidance": ("FLOAT", {"default": 4.0, "min": 1.0, "max": 10.0}),
            "review_model": ("STRING", {"default": DEFAULT_REVIEW_MODEL}),
            "art_attempts": ("INT", {"default": 5, "min": 1, "max": 5, "tooltip": "Maximum attempts per asset, including repairs. Stops on unresolved failures and saves all candidates/reasons."}),
            "scale_guide": ("BOOLEAN", {"default": False}),
            "reference_strategy": (["cast_guide", "portraits"], {"default": "cast_guide", "tooltip": "Flux scenes use one shared cast sheet to preserve relative sizes. Individual portraits remain the identity references for quality review."}),
            "track_story_state": ("BOOLEAN", {"default": False, "tooltip": "Development preview: plan temporary costume states and protected reference edits. Enable only in the state-calibration workflow until validated."}),
        }
        for key, category in (("flux_model", "diffusion_models"), ("flux_encoder", "text_encoders"), ("flux_vae", "vae")):
            optional[key] = (folder_paths.get_filename_list(category), {"default": FLUX_MODELS[key]})
        optional['planning_model'] = ('STRING', {'default':'hf.co/unsloth/Qwen3.5-27B-GGUF:Q6_K',
            'tooltip':'Local model for private critical-prop planning. Story writing and visual review keep their separate selected models.'})
        optional['visual_library'] = ('BOOLEAN', {'default': False,
            'tooltip': 'Preview: build and verify canonical recurring prop/location images before pages, then check scene continuity against them. Flux2.dev only.'})
        optional['actor_labels'] = ('BOOLEAN', {'default': True,
            'tooltip': 'Preview: qualify character names with checked current species/clothing inside scene action sentences.'})
        optional['flux_scene_recipe'] = (['standard','turbo8_native'], {'default':'standard',
            'tooltip':'Turbo8 uses eight steps for fresh scenes. References and bounded duplicate-removal edits use the base settings; other retries redraw from canonical references.'})
        optional['concise_prompts'] = ('BOOLEAN', {'default':False,
            'tooltip':'Compile fresh shared-cast scenes into concise, locally checked prompts with fixed current appearance and reference roles.'})
        return {"required": inputs, "optional": optional}

    RETURN_TYPES = ("BOOK_PROJECT",)
    RETURN_NAMES = ("book_with_references",)
    FUNCTION = "render"
    CATEGORY = CATEGORY
    DESCRIPTION = "Create one common style reference and all character portraits. Reuses verified completed assets."

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def render(self, book_project, **settings):
        track_story_state = settings.pop('track_story_state', False)
        use_visual_library = settings.pop('visual_library', False)
        use_actor_labels = settings.pop('actor_labels', True)
        concise_prompts = settings.pop('concise_prompts', False)
        planning_model = settings.pop('planning_model', 'hf.co/unsloth/Qwen3.5-27B-GGUF:Q6_K')
        settings = {"renderer": "flux2", **FLUX_MODELS, "flux_steps": 28, "flux_guidance": 4.0,
                    "review_model": DEFAULT_REVIEW_MODEL, "art_attempts": 5, "scale_guide": False, "reference_strategy": "cast_guide", **settings,
                    "quality_required": True, "qa_version": QA_VERSION}
        if not book_project.get("story_quality", {}).get("accepted"):
            raise ValueError("The story must pass editorial review before rendering.")
        if track_story_state:
            from .state_ledger import compile_plan
            book_project = {**book_project, 'art_plan': compile_plan(book_project, settings['review_model'])}
        from .scene_contract import compile_contract
        book_project = {**book_project, 'scene_contract': compile_contract(book_project, planning_model)}
        if use_visual_library:
            if settings['renderer'] != 'flux2':
                raise ValueError('Visual-library preview requires Flux2.dev.')
            from .visual_library import compile_library
            book_project = {**book_project, 'visual_library': compile_library(book_project, settings['review_model'])}
        if use_visual_library:
            from .prop_groups import compile_groups
            book_project = {**book_project, 'prop_groups': compile_groups(book_project, settings['review_model'])}
        if use_actor_labels:
            settings['actor_label_policy'] = 1
        if concise_prompts:
            settings['compact_prompt_policy'] = 11
        from .object_relations import compile_relations
        book_project = {**book_project, 'object_relations':compile_relations(book_project,settings['review_model'])}
        return expand_assets(configure_render(book_project, settings), {"style", "character", "prop", "location", "prop_group"})


class BookV2Illustrations:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"book_project": ("BOOK_PROJECT",)}}

    RETURN_TYPES = ("BOOK_PROJECT",)
    RETURN_NAMES = ("illustrated_book",)
    FUNCTION = "render"
    CATEGORY = CATEGORY
    DESCRIPTION = "Render the cover and every page in order, automatically selecting each scene's canonical references."

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def render(self, book_project):
        for spec in asset_specs(book_project):
            if spec["kind"] in {"style", "character", "prop", "location", "prop_group"} and not valid_asset(book_project, spec):
                raise ValueError(f"Missing reference {spec['name']}; connect the character reference stage first.")
        if book_project.get('art_plan'):
            from .state_assets import prepare_details
            book_project = prepare_details(book_project)
        return expand_assets(book_project, {"state", "scene"})


class BookV2StateReferences:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'book_project': ('BOOK_PROJECT',)}}
    RETURN_TYPES = ('BOOK_PROJECT',)
    FUNCTION = 'render'
    CATEGORY = CATEGORY + '/internal'

    def render(self, book_project):
        from .state_assets import prepare_details
        book_project = prepare_details(book_project)
        return expand_assets(book_project, {'state'})


class BookV2Export:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"book_project": ("BOOK_PROJECT",), "export_pdf": ("BOOLEAN", {"default": False})}}

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("contact_sheet", "summary", "output_folder")
    FUNCTION = "export"
    CATEGORY = CATEGORY
    OUTPUT_NODE = True
    DESCRIPTION = "Save the complete asset manifest, readable HTML book, story text, contact sheet and optional typeset PDF."

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def export(self, book_project, export_pdf):
        result = export_book(book_project, export_pdf)
        return {"ui": {"text": [result[1]]}, "result": result}


class BookV2Prompt:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING",), "after": ("STRING",)}}
    RETURN_TYPES = ("STRING",)
    FUNCTION = "run"
    CATEGORY = CATEGORY + "/internal"

    def run(self, prompt, after):
        return (prompt,)


class BookV2LoadReference:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"project": ("BOOK_PROJECT",), "asset_name": ("STRING",), "after": ("STRING",)}}
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "load"
    CATEGORY = CATEGORY + "/internal"

    def load(self, project, asset_name, after):
        import numpy as np
        import torch
        from PIL import Image
        spec = next(s for s in asset_specs(project) if s["name"] == asset_name)
        if not valid_asset(project, spec):
            raise ValueError(f"Reference {asset_name} has not been generated yet.")
        with Image.open(asset_path(project, asset_name)) as image:
            result = torch.from_numpy(np.array(image.convert("RGB")).astype(np.float32) / 255.0).unsqueeze(0)
        return (result,)


class BookV2LoadGroupAssembly:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'project': ('BOOK_PROJECT',), 'spec': ('BOOK_ASSET',)}}
    RETURN_TYPES = ('IMAGE',)
    FUNCTION = 'load'
    CATEGORY = CATEGORY + '/internal'

    def load(self, project, spec):
        from .prop_groups import assemble_reference
        from PIL import Image
        import numpy as np
        import torch
        record = assemble_reference(project, spec)
        if record is None:
            raise ValueError('Prepared containment reference is unavailable.')
        image = Image.open(record['path']).convert('RGB')
        return (torch.from_numpy(np.array(image).astype(np.float32)/255.0)[None],)


class BookV2VisualReferenceSheet:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'project': ('BOOK_PROJECT',), 'spec': ('BOOK_ASSET',),
                             'kind': (['prop', 'location'],)}}
    RETURN_TYPES = ('IMAGE',)
    FUNCTION = 'load'
    CATEGORY = CATEGORY + '/internal'

    def load(self, project, spec, kind):
        from .visual_library import reference_sheet
        import numpy as np
        import torch
        return (torch.from_numpy(np.array(reference_sheet(project, spec, kind)).astype(np.float32)/255.0)[None],)


class BookV2SaveAsset:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"project": ("BOOK_PROJECT",), "spec": ("BOOK_ASSET",), "images": ("IMAGE",)},
                "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"}}
    RETURN_TYPES = ("STRING",)
    FUNCTION = "save"
    CATEGORY = CATEGORY + "/internal"

    def save(self, project, spec, images, prompt=None, extra_pnginfo=None):
        save_asset(project, spec, images, prompt, extra_pnginfo)
        logging.info("Book v2: saved %s", asset_path(project, spec["name"]))
        return {"ui": {"images": [image_record(project, spec["name"])]}, "result": (str(asset_path(project, spec["name"])),)}


class BookV2StageComplete:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"project": ("BOOK_PROJECT",), "after": ("STRING",)}}
    RETURN_TYPES = ("BOOK_PROJECT",)
    FUNCTION = "run"
    CATEGORY = CATEGORY + "/internal"

    def run(self, project, after):
        return (project,)


class BookV2SelectAsset:
    """Select a test/retry asset from the flowing native project, retaining exact integers."""
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'project': ('BOOK_PROJECT',), 'asset_name': ('STRING',)}}
    RETURN_TYPES = ('BOOK_ASSET',)
    FUNCTION = 'select'
    CATEGORY = CATEGORY + '/internal'

    def select(self, project, asset_name):
        spec = next((s for s in asset_specs(project) if s['name'] == asset_name), None)
        if spec is None:
            raise ValueError('Unknown book asset: ' + asset_name)
        return (spec,)


class BookV2LoadAssetProject:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'project_file':('STRING',),'asset_name':('STRING',)}}
    RETURN_TYPES=('BOOK_PROJECT','BOOK_ASSET')
    FUNCTION='load'
    CATEGORY=CATEGORY+'/internal'

    def load(self,project_file,asset_name):
        from .storage import checked_root
        path=Path(project_file).resolve()
        allowed=(books_root().resolve(),(books_root().parent/'codex/books').resolve())
        if not any(path.is_relative_to(base) for base in allowed):
            raise ValueError('Saved book projects must be under the book output directory.')
        project=json.loads(path.read_text())
        checked_root(project)
        validate_package({'story':project['story'],'production':project['production']},
                         project['config']['page_count'],project['config']['max_characters'])
        spec=next((s for s in asset_specs(project) if s['name']==asset_name),None)
        if spec is None:raise ValueError('Unknown saved book asset.')
        return project,spec


class BookV2RenderAsset:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"project": ("BOOK_PROJECT",), "spec": ("BOOK_ASSET",), "after": ("STRING",)},
                "optional": {"start_attempt": ("INT", {"default": 1})}}
    RETURN_TYPES = ("STRING",)
    FUNCTION = "run"
    CATEGORY = CATEGORY + "/internal"

    def run(self, project, spec, after, start_attempt=1):
        from .scene_staging import ScenePromptError
        try:
            return self._run(project, spec, after, start_attempt)
        except ScenePromptError as exc:
            if spec['kind'] != 'scene':
                raise
            directory = review_directory(project, spec)
            from .storage import record_asset_failure
            record_asset_failure(directory, {'status': 'planning_failed',
                       'signature': spec['signature'], 'asset': spec['name'], 'reason': str(exc)})
            from .draft_selection import try_select_review_candidate
            from .preview import refresh_review_draft
            try_select_review_candidate(project, spec)
            refresh_review_draft(project)
            logging.error('Book v2: planning failed for %s: %s. Continuing remaining scenes.', spec['name'], exc)
            return ('UNAPPROVED: '+spec['name'],)

    def _run(self, project, spec, after, start_attempt=1):
        if valid_asset(project, spec):
            return (str(asset_path(project, spec["name"])),)
        directory = review_directory(project, spec)
        from .storage import reuse_candidate_pixels
        if reuse_candidate_pixels(project,spec):
            logging.info('Book v2: rechecking saved pixels for %s under the updated quality rules.',spec['name'])
        feedback = ""
        correction_attempt = None
        last_report = None
        last_attempt = None
        failed_reports = []
        for attempt in range(1, project["render_settings"]["art_attempts"] + 1):
            report_path = directory / f"attempt-{attempt:02d}-review.json"
            png_path = directory / f"attempt-{attempt:02d}.png"
            if report_path.exists():
                report = json.loads(report_path.read_text())
                if report["signature"] != spec["signature"]:
                    raise ValueError("Review signature mismatch; use a new rendition.")
                # Only recheck failed pixels affected by the shared staging fix.
                # Preserve the old evidence; approved pages keep their approval.
                from .quality import QA_VERSION, expected_scene
                from .scene_contract import scene_brief
                scene = project['book']['cover'] if spec['name']=='cover.png' else next(
                    (p for p in project['book']['pages'] if spec['name']==f"pages/page-{p['page_number']:03d}.png"), None)
                if (not report['accepted'] and spec['kind']=='scene' and scene is not None
                        and report.get('qa_version') != QA_VERSION
                        and scene_brief(project, scene) != expected_scene(project, spec)[1]):
                    previous = report_path.read_bytes()
                    archive = directory/f"attempt-{attempt:02d}-review-before-staging-{hashlib.sha256(previous).hexdigest()[:12]}.json"
                    write_exclusive(archive, previous)
                    # The evidence is safely archived. Free only its active
                    # filename so the normal exclusive writer can save the new
                    # review; a crash here resumes from the existing PNG.
                    if archive.read_bytes() != previous or report_path.read_bytes() != previous:
                        raise ValueError('Review changed while archiving for recheck.')
                    report_path.unlink()
                    meta = json.loads((directory/f'attempt-{attempt:02d}-render.json').read_text())
                    return BookV2ReviewAsset().review(project, spec, None, attempt, meta['seed'], meta['prompt'])
                if report["accepted"]:
                    publish_reviewed_asset(project, spec, png_path.read_bytes(), report)
                    return (str(asset_path(project, spec["name"])),)
                # Failure descriptions such as "Pip points at Mia instead of the
                # stones" repeatedly reproduced that bad pose in Flux. Keep the
                # diagnosis in the report; render from affirmative instructions.
                review = report["review"]
                feedback = " ".join(review.get("retry_instructions", []))
                if (review.get("checks", {}).get("scene_matches") is False and review.get("retry_scene")
                        and (project['render_settings'].get('scene_edit_version',1) < 5 or not feedback)):
                    feedback = review["retry_scene"] + "\n" + feedback
                last_report, last_attempt = report, attempt
                failed_reports.append((attempt, report))
                # Preserve a good cast/composition while correcting a local defect.
                # Do not carry a merged or missing character into the next attempt.
                # The last allowed attempt starts afresh from canonical references.
                if (project["render_settings"].get("renderer") == "flux2"
                        and attempt + 1 < project["render_settings"]["art_attempts"]
                        and review.get("unexpected_character_count") == 0
                        and all(c["count"] == 1 and c["identity_matches"] and c["appearance_matches"]
                                for c in review.get("characters", []))):
                    correction_attempt = attempt
                else:
                    correction_attempt = None
                continue
            if png_path.exists():
                # A crash/reviewer outage does not discard a costly render.
                meta = json.loads((directory / f"attempt-{attempt:02d}-render.json").read_text())
                return BookV2ReviewAsset().review(project, spec, None, attempt, meta["seed"], meta["prompt"])
            logging.info("Book v2: render %s, attempt %d/%d", spec["name"], attempt, project["render_settings"]["art_attempts"])
            recovered_from_regression = None
            if (project['render_settings'].get('candidate_recovery_policy', 0) >= 1
                    and project['render_settings'].get('renderer') == 'flux2'
                    and spec['kind'] == 'scene' and correction_attempt is None
                    and attempt < project['render_settings']['art_attempts']):
                from .candidate_ranking import can_correct_cast, rank_candidate
                from .quality import expected_scene
                ids = expected_scene(project, spec)[0]
                eligible = [(n, r) for n, r in failed_reports if can_correct_cast(r, ids)]
                if eligible:
                    chosen_attempt, chosen = min(eligible, key=lambda item: rank_candidate(item[1], ids))
                    if chosen_attempt != last_attempt:
                        recovered_from_regression = {'latest_attempt':last_attempt, 'chosen_attempt':chosen_attempt}
                        correction_attempt = last_attempt = chosen_attempt
                        last_report = chosen
                        feedback = ' '.join(chosen['review'].get('retry_instructions', []))
                        if not feedback:
                            feedback = chosen['review'].get('retry_scene', '')
            restart_reason = None
            retry_decision = None
            latest_saved_strategy = {}
            if (correction_attempt is not None and attempt >= 3
                    and project['render_settings'].get('scene_edit_version', 1) >= 4):
                from .retry_scope import scale_edit_stalled
                prior_path = directory / f'attempt-{last_attempt-1:02d}-review.json'
                if prior_path.exists() and scale_edit_stalled(json.loads(prior_path.read_text()), last_report):
                    correction_attempt = None
                    restart_reason = 'The measured size error did not improve; redraw from approved canonical references.'
            if (project['render_settings'].get('scene_edit_version', 1) >= 6
                    and project['render_settings'].get('renderer') == 'flux2' and spec['kind'] == 'scene'):
                from .retry_scope import scene_edit_restart
                from .quality import expected_scene
                strategies = {}
                for number, saved_report in failed_reports:
                    path = directory / f'attempt-{number:02d}-strategy.json'
                    if path.exists():
                        saved_strategy = json.loads(path.read_text())
                        if saved_strategy.get('signature') == spec['signature']:
                            strategies[number] = saved_strategy
                if failed_reports:
                    latest_saved_strategy = strategies.get(failed_reports[-1][0], {})
                retry_decision = scene_edit_restart(failed_reports, strategies, expected_scene(project, spec)[0])
                if retry_decision:
                    # Recovery from an older candidate must not resume a failed
                    # edit chain after this policy has explicitly chosen fresh.
                    correction_attempt = None
                    recovered_from_regression = None
                    last_attempt, last_report = failed_reports[-1]
                    feedback = ' '.join(last_report['review'].get('retry_instructions', []))
                    if not feedback:
                        feedback = last_report['review'].get('retry_scene', '')
                    restart_reason = retry_decision['reason']
            # The fast scene recipe was validated as a fresh render. Keep its
            # retries on canonical references; the measured cutout path has a
            # known neighbouring-tail ownership failure and is not validated here.
            turbo_redraw = (spec['kind'] == 'scene' and
                            project['render_settings'].get('flux_scene_recipe') == 'turbo8_native')
            if turbo_redraw:
                correction_attempt = None
                recovered_from_regression = None
                restart_reason = 'Turbo8 scene retries redraw from canonical references.' if attempt > 1 else None
            duplicate_plan = None
            if (project['render_settings'].get('duplicate_edit_policy',
                    project.get('runtime_retry_policy', {}).get('duplicate_edit_policy', 0)) >= 1
                    and project['render_settings'].get('renderer') == 'flux2'
                    and spec['kind'] == 'scene' and last_report is not None):
                from .duplicate_edit import eligible, prepare_edit
                from .quality import expected_scene
                if eligible(last_report, expected_scene(project, spec)[0]):
                    from .review_session import phase
                    with phase(project, directory/f'attempt-{attempt:02d}-duplicate-calls'):
                        duplicate_plan = prepare_edit(project, spec, last_attempt, attempt, last_report)
                    if duplicate_plan:
                        correction_attempt = last_attempt
                        restart_reason = 'One local removal chosen to preserve existing gaze, contacts and story interaction.'
            object_plan = None
            if (not duplicate_plan and last_report is not None and spec['kind'] == 'scene'
                    and project['render_settings'].get('renderer') == 'flux2'
                    and project['render_settings'].get('object_edit_policy',
                        project.get('runtime_retry_policy', {}).get('object_edit_policy', 0)) >= 1):
                from .object_edit import eligible as object_eligible, prepare_edit as prepare_object_edit
                from .quality import expected_scene
                if object_eligible(last_report, expected_scene(project, spec)[0]):
                    from .review_session import phase
                    with phase(project, directory/f'attempt-{attempt:02d}-object-calls'):
                        object_plan = prepare_object_edit(project, spec, last_attempt, attempt, last_report)
                    if object_plan:
                        correction_attempt = last_attempt
                        restart_reason = 'One extra-object removal preserves the original object, contents and actor interaction.'
            repair = False
            if (not turbo_redraw and not duplicate_plan and not object_plan and (not restart_reason or project['render_settings'].get('scene_edit_version', 1) >= 6)
                    and not (restart_reason and latest_saved_strategy.get('strategy') == 'masked_size_repair')
                    and last_report is not None and spec['kind'] == 'scene' and project['render_settings'].get('renderer') == 'flux2'):
                from .repair import try_scale_repair
                repair = try_scale_repair(project,spec,last_attempt,attempt,last_report)
                if repair and project['render_settings'].get('scene_edit_version', 1) >= 6:
                    restart_reason = None
                    correction_attempt = None
                    if retry_decision:
                        retry_decision = {**retry_decision, 'decision': 'masked_size_repair',
                                          'reason': 'A verified target and held-prop size repair was prepared; use it before a full redraw.'}
            prepared_pose = False
            if (not repair and not duplicate_plan and not object_plan and correction_attempt is not None and attempt >= 3
                    and spec.get('reference_layout')=='cast_guide'
                    and project['render_settings'].get('pose_guide_version',0) >= 1
                    and (last_report.get('layout_review') or {}).get('story_event_visible') is not True
                    and last_report['review'].get('checks',{}).get('scene_matches') is False):
                from .pose import try_pose_guide
                prepared_pose = try_pose_guide(project,spec,last_attempt,attempt,last_report)
            if (project['render_settings'].get('scene_edit_version', 1) >= 4
                    and (not prepared_pose or project['render_settings'].get('scene_edit_version', 1) >= 6)):
                write_json(directory / f'attempt-{attempt:02d}-strategy.json', {
                    'signature': spec['signature'], 'source_attempt': correction_attempt,
                    'strategy': 'object_removal' if object_plan else 'duplicate_removal' if duplicate_plan else 'masked_size_repair' if repair else 'scene_edit' if correction_attempt is not None else 'canonical_redraw',
                    'reason': restart_reason,
                    'recovered_from_regression': recovered_from_regression,
                    'retry_policy': retry_decision,
                    'pose_guide': prepared_pose,
                })
            if prepared_pose:
                return expand_attempt(project,spec,attempt,feedback,correction_attempt,pose_guide=True)
            if duplicate_plan:
                return expand_attempt(project, spec, attempt, correction_attempt=correction_attempt, duplicate_plan=duplicate_plan)
            if object_plan:
                from .object_edit import expand_edit
                return expand_edit(project, spec, attempt, object_plan)
            return expand_attempt(project, spec, attempt, feedback, correction_attempt, scale_repair=repair)
        failure = (f"Visual quality failed after {project['render_settings']['art_attempts']} attempts for {spec['name']}. "
                   f"Review draft: {Path(project['render_root'])/'review-draft.html'}. Candidates and reasons: {directory}")
        from .draft_selection import try_select_review_candidate
        try_select_review_candidate(project, spec)
        if spec['kind'] == 'scene':
            # Pages depend on approved canonical references, not on one another.
            # Retain this rejection while allowing the remaining pages to run.
            # Export independently requires valid approval for EVERY asset.
            from .storage import record_asset_failure
            record_asset_failure(directory, {'status':'unapproved', 'signature':spec['signature'],
                       'asset':spec['name'], 'attempts':project['render_settings']['art_attempts'], 'reason':failure})
            from .preview import refresh_review_draft
            refresh_review_draft(project)
            logging.error('Book v2: %s Continuing the remaining scenes.',failure)
            return ('UNAPPROVED: '+spec['name'],)
        from .preview import refresh_review_draft
        refresh_review_draft(project)
        raise ValueError(failure)


class BookV2ReviewAsset:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"project": ("BOOK_PROJECT",), "spec": ("BOOK_ASSET",), "images": ("IMAGE",),
                "attempt": ("INT",), "actual_seed": ("INT",), "actual_prompt": ("STRING",)},
                "optional": {"generation_info": ("STRING", {"default": ""})},
                "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"}}
    RETURN_TYPES = ("STRING",)
    FUNCTION = "review"
    CATEGORY = CATEGORY + "/internal"

    def review(self, project, spec, images, attempt, actual_seed, actual_prompt, prompt=None, extra_pnginfo=None, generation_info=""):
        directory = review_directory(project, spec)
        path = directory / f"attempt-{attempt:02d}.png"
        if not path.exists():
            provenance = {"generation_info": json.loads(generation_info)} if generation_info else {}
            write_json(directory / f"attempt-{attempt:02d}-render.json", {"seed": actual_seed, "prompt": actual_prompt, "signature": spec["signature"], **provenance})
            write_exclusive(path, image_bytes(spec, images, prompt, extra_pnginfo))
        png = path.read_bytes()
        from .preview import refresh_review_draft
        refresh_review_draft(project)
        logging.info("Book v2: reviewing %s, attempt %d", spec["name"], attempt)
        from .review_session import phase
        reviewer=review_art
        if project['render_settings'].get('scene_quality_policy') == 'concise_v1':
            from .quality_preview import review_art as reviewer
        with phase(project, directory/f'attempt-{attempt:02d}-calls'):
            report = reviewer(project, spec, png, attempt=attempt)
            from .duplicate_edit import apply_edit_review
            report = apply_edit_review(project, spec, attempt, png, report)
            from .object_edit import apply_edit_review as apply_object_edit_review
            report = apply_object_edit_review(project, spec, attempt, png, report)
        report.update(attempt=attempt, seed=actual_seed, prompt=actual_prompt,
                      png_sha256=hashlib.sha256(png).hexdigest())
        write_json(directory / f"attempt-{attempt:02d}-review.json", report)
        if report["accepted"]:
            publish_reviewed_asset(project, spec, png, report)
            refresh_review_draft(project)
            logging.info("Book v2: visually approved %s", spec["name"])
            return {"ui": {"images": [image_record(project, spec["name"])]}, "result": (str(asset_path(project, spec["name"])),)}
        logging.warning("Book v2: rejected %s: %s", spec["name"], json.dumps(report["review"], ensure_ascii=False))
        refresh_review_draft(project)
        from comfy_execution.graph_utils import GraphBuilder
        graph = GraphBuilder()
        retry = graph.node("BookV2RenderAsset", project=project, spec=spec, after="", start_attempt=attempt + 1)
        return {"result": (retry.out(0),), "expand": graph.finalize()}


class BookV2LoadCandidate:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"project": ("BOOK_PROJECT",), "spec": ("BOOK_ASSET",), "attempt": ("INT", {"min":1,"max":5})}}
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "load"
    CATEGORY = CATEGORY + "/internal"

    def load(self, project, spec, attempt):
        import numpy as np
        import torch
        from PIL import Image
        directory = review_directory(project, spec)
        path = directory / f"attempt-{attempt:02d}.png"
        record = json.loads((directory / f"attempt-{attempt:02d}-review.json").read_text())
        if record.get("signature") != spec["signature"] or record.get("png_sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError("Correction source differs from its reviewed candidate.")
        with Image.open(path) as image:
            result = torch.from_numpy(np.array(image.convert("RGB")).astype(np.float32)/255.0).unsqueeze(0)
        return (result,)


class BookV2ScaleGuide:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"project": ("BOOK_PROJECT",), "spec": ("BOOK_ASSET",)}}
    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "make"
    CATEGORY = CATEGORY + "/internal"

    def make(self, project, spec):
        import io
        import numpy as np
        import torch
        from .scale import make_scale_guide
        guide = make_scale_guide(project,spec)
        data=io.BytesIO();guide.save(data,format="PNG")
        write_exclusive(review_directory(project,spec)/"size-guide.png",data.getvalue())
        return (torch.from_numpy(np.array(guide).astype(np.float32)/255.0).unsqueeze(0),)


class BookV2LoadPoseGuide:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'project':('BOOK_PROJECT',),'spec':('BOOK_ASSET',),'attempt':('INT',)}}
    RETURN_TYPES = ('IMAGE',)
    FUNCTION = 'load'
    CATEGORY = CATEGORY + '/internal'

    def load(self,project,spec,attempt):
        import numpy as np
        import torch
        from PIL import Image
        directory=review_directory(project,spec)
        record=json.loads((directory/f'attempt-{attempt:02d}-pose.json').read_text())
        path=directory/f'attempt-{attempt:02d}-pose.png'
        if record['signature']!=spec['signature'] or hashlib.sha256(path.read_bytes()).hexdigest()!=record['image_sha256']:
            raise ValueError('Pose guide does not match its saved plan.')
        source=directory/f"attempt-{record['source_attempt']:02d}.png"
        if hashlib.sha256(source.read_bytes()).hexdigest()!=record['source_sha256']:
            raise ValueError('Pose correction source changed.')
        with Image.open(path) as image:
            return (torch.from_numpy(np.array(image.convert('RGB')).astype(np.float32)/255.0).unsqueeze(0),)


class BookV2LoadStateEdit:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'project': ('BOOK_PROJECT',), 'spec': ('BOOK_ASSET',)}}
    RETURN_TYPES = ('IMAGE', 'MASK', 'IMAGE')
    FUNCTION = 'load'
    CATEGORY = CATEGORY + '/internal'

    def load(self, project, spec):
        import numpy as np
        import torch
        from .state_assets import variant_inputs, detail_directory, png_bytes
        from .state_edit import restore_cloth_before_edit
        from .storage import write_exclusive
        from PIL import Image
        import math
        original, mask = variant_inputs(project,spec)
        pixels, mask_tensor = (torch.from_numpy(np.array(im).astype(np.float32)/255.0).unsqueeze(0)
                               for im in (original,mask))
        conditioning = pixels
        if spec.get('edits'):
            core = np.zeros((original.height,original.width),dtype=np.float32)
            for change in spec['changes']:
                if not restore_cloth_before_edit(change):
                    continue
                record = json.loads((detail_directory(project,change)/'measurement.json').read_text())
                for part in record['selected']:
                    x0,y0,x1,y1 = part['bbox']
                    core[max(0,math.floor(y0)-4):min(original.height,math.ceil(y1)+4),
                         max(0,math.floor(x0)-4):min(original.width,math.ceil(x1)+4)] = 1
            if core.any():
                conditioning = BookV2RestoreLocalSurface().restore(pixels,torch.from_numpy(core).unsqueeze(0))[0]
            directory = review_directory(project,spec)
            prepared = Image.fromarray((conditioning[0].numpy()*255).round().clip(0,255).astype(np.uint8),'RGB')
            write_exclusive(directory/'conditioning-source.png',png_bytes(prepared))
        return pixels,mask_tensor,conditioning


class BookV2RestoreLocalSurface:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'image': ('IMAGE',), 'mask': ('MASK',)}}
    RETURN_TYPES = ('IMAGE',)
    FUNCTION = 'restore'
    CATEGORY = CATEGORY + '/internal'

    def restore(self, image, mask):
        import cv2
        import numpy as np
        import torch
        if image.shape[0] != 1 or mask.shape[0] != 1 or tuple(image.shape[1:3]) != tuple(mask.shape[1:3]):
            raise ValueError('Local surface restoration requires one aligned image and mask.')
        pixels = (image[0].cpu().numpy()*255).round().clip(0,255).astype(np.uint8)
        selected = (mask[0].cpu().numpy() > .5).astype(np.uint8)*255
        if not np.any(selected) or np.count_nonzero(selected) > selected.size*.02:
            raise ValueError('This operation is limited to a small measured surface region.')
        restored = cv2.inpaint(pixels, selected, 3, cv2.INPAINT_TELEA)
        # Enforce protection explicitly, independent of OpenCV implementation.
        restored[selected == 0] = pixels[selected == 0]
        return (torch.from_numpy(restored.astype(np.float32)/255).unsqueeze(0),)


class BookV2RestoreLocalSurfaceWithSupport:
    """Experimental conditioning: fill from the measured material, not adjacent fur."""
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'image': ('IMAGE',), 'mask': ('MASK',), 'support_mask': ('MASK',)}}
    RETURN_TYPES = ('IMAGE',)
    FUNCTION = 'restore'
    CATEGORY = CATEGORY + '/internal'

    def restore(self, image, mask, support_mask):
        import cv2
        import numpy as np
        import torch
        from scipy.ndimage import distance_transform_edt
        if (image.ndim != 4 or image.shape[0] != 1 or image.shape[-1] != 3
                or any(m.ndim != 3 or m.shape[0] != 1 or tuple(m.shape[1:]) != tuple(image.shape[1:3])
                       for m in (mask, support_mask))):
            raise ValueError('Supported surface restoration requires one aligned RGB image and two masks.')
        if not all(torch.isfinite(t).all().item() for t in (image, mask, support_mask)):
            raise ValueError('Surface restoration inputs must be finite.')
        pixels = (image[0].cpu().numpy()*255).round().clip(0,255).astype(np.uint8)
        selected = mask[0].cpu().numpy() > .5
        support = support_mask[0].cpu().numpy() > .5
        if not selected.any() or np.count_nonzero(selected) > selected.size*.02:
            raise ValueError('This operation is limited to a small measured surface region.')
        if np.any(selected & ~support):
            raise ValueError('The selected region must lie on the measured supporting surface.')
        valid = support & ~selected
        if not valid.any():
            raise ValueError('The measured surface has no unaffected material to sample.')
        # Extend known material temporarily so the inpaint boundary cannot pull
        # cream fur/background through a neckline. Only the selected result is
        # returned; extension pixels are never a published image modification.
        nearest = distance_transform_edt(~valid, return_distances=False, return_indices=True)
        conditioning = pixels[tuple(nearest)]
        restored = cv2.inpaint(conditioning, selected.astype(np.uint8)*255, 3, cv2.INPAINT_TELEA)
        restored[~selected] = pixels[~selected]
        return (torch.from_numpy(restored.astype(np.float32)/255).unsqueeze(0),)


class BookV2LoadPropDetail:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'project': ('BOOK_PROJECT',), 'prop': ('BOOK_PROP',)}}
    RETURN_TYPES = ('IMAGE',)
    FUNCTION = 'load'
    CATEGORY = CATEGORY + '/internal'

    def load(self, project, prop):
        import io
        import numpy as np
        import torch
        from PIL import Image
        from .state_assets import prop_reference
        image = Image.open(io.BytesIO(prop_reference(project, prop)[0])).convert('RGB')
        # Qwen Edit's reference geometry matches the fixed output geometry.
        image = image.resize((1024, 1024), Image.Resampling.LANCZOS) if image.width == image.height else image
        if image.size != (1024, 1024):
            image.thumbnail((900,900), Image.Resampling.LANCZOS)
            board = Image.new('RGB',(1024,1024),(250,247,235))
            board.paste(image,((1024-image.width)//2,(1024-image.height)//2));image=board
        return (torch.from_numpy(np.array(image).astype(np.float32)/255.0).unsqueeze(0),)


class BookV2LoadRepair:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'project':('BOOK_PROJECT',),'spec':('BOOK_ASSET',),'attempt':('INT',)}}
    RETURN_TYPES = ('IMAGE','MASK')
    FUNCTION = 'load'
    CATEGORY = CATEGORY + '/internal'

    def load(self,project,spec,attempt):
        import numpy as np
        import torch
        from PIL import Image
        directory=review_directory(project,spec)
        record=json.loads((directory/f'attempt-{attempt:02d}-repair.json').read_text())
        if not record['prepared'] or record['signature']!=spec['signature']:
            raise ValueError('Scale repair has no matching preparation record.')
        outputs=[]
        for label,mode in [('image','RGB'),('mask','L')]:
            path=directory/f'attempt-{attempt:02d}-repair-{label}.png'
            if hashlib.sha256(path.read_bytes()).hexdigest()!=record[label+'_sha256']:
                raise ValueError('Scale repair pixels differ from the preparation record.')
            with Image.open(path) as im:
                outputs.append(torch.from_numpy(np.array(im.convert(mode)).astype(np.float32)/255.0).unsqueeze(0))
        return tuple(outputs)


from .qwen_book import BookV2QwenEdition

NODE_CLASS_MAPPINGS = {cls.__name__: cls for cls in (BookV2QwenEdition, BookV2Story, BookV2References, BookV2Illustrations, BookV2Export,
                     BookV2Prompt, BookV2LoadReference, BookV2SaveAsset, BookV2StageComplete,
                     BookV2RenderAsset, BookV2ReviewAsset, BookV2LoadCandidate, BookV2ScaleGuide, BookV2LoadRepair,
                     BookV2LoadAssetProject, BookV2SelectAsset, BookV2LoadPoseGuide, BookV2LoadStateEdit, BookV2LoadPropDetail,
                     BookV2StateReferences, BookV2RestoreLocalSurface, BookV2RestoreLocalSurfaceWithSupport,
                     BookV2VisualReferenceSheet, BookV2LoadGroupAssembly)}
NODE_DISPLAY_NAME_MAPPINGS = {
    "BookV2QwenEdition": "Reillustrate saved book · Qwen Edit2511 Lightning8",
    "BookV2Story": "1 · Write the story",
    "BookV2References": "2 · Create style and character references",
    "BookV2Illustrations": "3 · Illustrate cover and every page",
    "BookV2Export": "4 · Save the complete book",
}

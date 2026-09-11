"""Isolated book outputs, atomic writes and provenance-checked asset reuse."""
import json
import os
from pathlib import Path
import tempfile
import hashlib

from .story import safe_asset_name


def books_root():
    import folder_paths
    return (Path(folder_paths.get_output_directory()) / "books").resolve()


def checked_root(project):
    root = Path(project["render_root"]).resolve()
    # Existing books keep their paths; all new projects use books_root().
    allowed = (books_root().resolve(), (books_root().parent / "codex/books").resolve())
    if not any(root.is_relative_to(base) for base in allowed):
        raise ValueError("Book output must stay inside the books directory (or its existing legacy books directory).")
    return root


def asset_path(project, name):
    root = checked_root(project)
    path = (root / safe_asset_name(name)).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Book asset path escapes its book directory.")
    return path


def write_exclusive(path, data):
    """Publish a complete file without ever replacing a pre-existing file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".book-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        try:
            os.link(tmp, path)
        except FileExistsError:
            if path.read_bytes() != data:
                raise FileExistsError(f"Refusing to overwrite {path}. Choose a new book seed or rendition.")
    finally:
        Path(tmp).unlink(missing_ok=True)


def write_json(path, data):
    write_exclusive(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode())


def record_asset_failure(directory, record):
    """Keep immutable failure history and update only the current status view."""
    from .preview import atomic_view
    directory = Path(directory)
    current = directory/'failed.json'
    data = (json.dumps(record, ensure_ascii=False, indent=2)+'\n').encode()
    for value in ([current.read_bytes()] if current.exists() else []) + [data]:
        write_exclusive(directory/'failure-history'/f'{hashlib.sha256(value).hexdigest()}.json', value)
    atomic_view(current, data)


def save_workflow_checkpoint(root, prompt, extra_pnginfo=None):
    """Keep the submitted graph before costly work, independently of browser history."""
    if not isinstance(prompt, dict) or not prompt:
        return
    import copy
    from .story import digest
    directory = Path(root) / "checkpoints"
    key = digest(prompt)[:16]
    write_json(directory / f"{key}.api.json", prompt)
    canvas = (extra_pnginfo or {}).get("workflow")
    if isinstance(canvas, dict) and isinstance(canvas.get("nodes"), list):
        canvas = copy.deepcopy(canvas)
        for node in canvas["nodes"]:
            submitted = prompt.get(str(node.get("id")), {})
            if node.get("type") != "BookV2Story" or submitted.get("class_type") != "BookV2Story":
                continue
            values = node.get("widgets_values")
            seed = submitted.get("inputs", {}).get("seed")
            # The seed widget follows the five premise/style widgets. Its frontend
            # control would otherwise randomize the restored book on the next run.
            if isinstance(values, list) and len(values) > 6 and isinstance(seed, int):
                values[5], values[6] = seed, "fixed"
        write_json(directory / f"{key}-{digest(canvas)[:8]}.workflow.json", canvas)
    write_exclusive(directory / "README.txt", (
        "Saved before generation: exact API graph and, when supplied, editable ComfyUI canvas.\n"
        "Open a .workflow.json in ComfyUI and Run to resume. Its story seed is fixed.\n"
        "API clients can enqueue the matching .api.json with no seed changes.\n"
        "Approved stages are reused with the same installed builder and settings.\n"
        "An interrupted sampler restarts its current image; saved images/reviews remain.\n"
        "Changing models or builder/quality versions can create a separate rendition.\n"
    ).encode())


def valid_asset(project, spec):
    from PIL import Image
    path = asset_path(project, spec["name"])
    if not path.exists():
        return False
    if spec['kind'] != 'scene' and spec['name'] in project.get('reference_adoptions', {}):
        from .qwen_book import valid_adopted_reference
        return valid_adopted_reference(project, spec)
    try:
        with Image.open(path) as img:
            record = json.loads(img.info.get("book_asset", "{}"))
            if record.get("signature") != spec["signature"] or img.size != (1024, 1024):
                raise ValueError("signature or dimensions do not match")
            img.verify()
        if project.get("render_settings", {}).get("quality_required"):
            approval = json.loads(approval_path(project, spec).read_text())
            from .quality import passed, expected_scene
            if (approval.get("accepted") is not True or approval.get("signature") != spec["signature"]
                    or approval.get("png_sha256") != hashlib.sha256(path.read_bytes()).hexdigest()
                    or not passed(approval["review"], expected_scene(project, spec)[0])):
                raise ValueError("visual approval is absent or does not match this image")
    except Exception as exc:
        raise ValueError(f"Existing asset {path} is invalid or belongs to different settings. Preserve it and use a new seed/rendition. ({exc})") from exc
    return True


def reuse_candidate_pixels(project, spec):
    """Reuse compatible pixels across QA revisions, always requiring a new review."""
    import io
    from PIL import Image, PngImagePlugin
    from .story import asset_specs
    from .quality import expected_scene
    from .candidate_ranking import rank_candidate
    expected_ids = expected_scene(project, spec)[0]
    directory=review_directory(project,spec)
    if directory.exists() and any(directory.iterdir()):
        return False
    if not project.get('book_root'):
        return False
    def generation_settings(settings):
        # Retry/prompt-policy changes may reuse old pixels only when the original
        # brief, models, seed and reference pixels match; NEW review is mandatory.
        ignored = {'qa_version', 'style_prompt_version', 'scene_edit_version', 'scale_repair_policy',
                   'scene_contract_prompt_policy', 'candidate_recovery_policy'}
        # Prop prompt policy is already checked by exact effective scene-prompt
        # equality below; changed descriptions cannot reuse those old pixels.
        if spec['kind'] not in ('scene', 'prop_group'):
            ignored.update(('prop_group_policy', 'prop_group_hash', 'prop_group_composition'))
        if spec['kind'] == 'style':
            ignored.add('portrait_prompt_version')
        if spec['kind'] != 'scene':
            ignored.add('scene_context_policy')
            ignored.add('compact_prompt_policy')
            ignored.update(('object_relations_version','object_relations_hash'))
            ignored.update(('scene_contract_version', 'scene_contract_hash'))
            ignored.update(('scene_reference_policy', 'scene_style_policy'))
            # Scene reference routing cannot change a style or portrait render.
            ignored.update(('reference_strategy', 'scale_guide', 'pose_guide_version', 'scene_edit_version'))
            ignored.add('state_scene_policy')
            ignored.add('garment_reference_policy')
            ignored.add('actor_label_policy')
        if spec['kind'] in ('style', 'character', 'state'):
            ignored.update(('visual_library_version', 'visual_library_hash'))
            ignored.add('visual_reference_prompt_policy')
        if spec['kind']=='scene' and not spec.get('props'):
            ignored.add('garment_reference_policy')
        if spec['kind'] in ('style', 'character'):
            ignored.update(('state_plan_version', 'state_plan_hash', 'state_edit_policy'))
            ignored.update(('visual_library_version', 'visual_library_hash'))
            ignored.add('actor_label_policy')
        if (spec['kind']=='scene' and not spec.get('props') and not spec.get('state_edit_hashes')
                and not any(name.startswith('states/') for name in spec['references'])):
            # A state change elsewhere in the book cannot affect this scene.
            # Exact book/brief/seed and every actual reference pixel still have
            # to match below, and an old approval is never carried forward.
            ignored.update(('state_plan_version','state_plan_hash','state_edit_policy','state_scene_policy'))
        return {k:v for k,v in settings.items() if k not in ignored}
    def pixels(path):
        with Image.open(path) as image:
            if image.size!=(1024,1024):raise ValueError('Wrong saved image dimensions.')
            return hashlib.sha256(image.convert('RGB').tobytes()).hexdigest()
    source_paths=set((Path(project['book_root'])/'renders').glob('*/project.json'))
    # Revisions can keep the entire book unchanged (e.g. adopting a plain-text
    # formatter for prose that was already plain). Scenes still require exact
    # book equality below; canonical art additionally requires matching briefs.
    source_paths.update(books_root().glob(f"book-{project['config']['seed']}-*/renders/*/project.json"))
    sources=sorted(source_paths,key=lambda p:p.stat().st_mtime,reverse=True)
    all_options = []
    for source_file in sources:
        try:
            old=json.loads(source_file.read_text())
            prepared_file=source_file.with_name('prepared-state-project.json')
            if prepared_file.exists():
                prepared=json.loads(prepared_file.read_text())
                if any(prepared[k]!=old[k] for k in ('book','config','render_settings','render_root')):
                    continue
                old=prepared
            oldroot=checked_root(old)
            if oldroot==checked_root(project) or (spec['kind']=='scene' and old['book']!=project['book']):
                continue
            if generation_settings(old['render_settings'])!=generation_settings(project['render_settings']):
                continue
            oldspecs={s['name']:s for s in asset_specs(old)}
            previous=oldspecs[spec['name']]
            if any(previous[k]!=spec[k] for k in ('name','kind','prompt','references','seed')):
                continue
            # Actual state rendering uses the compiled recipe, not only the
            # ledger's original prompt. Provenance hashes can change after QA,
            # but the effective paint instructions and prop routes must match.
            if ([e['plan'] for e in previous.get('edits',[])] != [e['plan'] for e in spec.get('edits',[])]
                    or previous.get('props',[]) != spec.get('props',[])):
                continue
            if any(not valid_asset(old,oldspecs[name]) or pixels(asset_path(old,name))!=pixels(asset_path(project,name))
                   for name in spec['references']):
                continue
            options=[]
            if valid_asset(old,previous):
                report=json.loads(approval_path(old,previous).read_text())
                options.append((rank_candidate(report, expected_ids, approved=True),asset_path(old,spec['name']),report))
            else:
                from .draft_selection import selected_draft_candidate
                choice = selected_draft_candidate(old, previous)
                for report_file in sorted(review_directory(old,previous).glob('attempt-*-review.json')):
                    report=json.loads(report_file.read_text())
                    candidate=report_file.with_name(report_file.name.replace('-review.json','.png'))
                    compared = bool(choice and str(candidate) == choice['path'])
                    options.append((rank_candidate(report, expected_ids, compared_choice=compared),candidate,report))
            if (project['render_settings'].get('scale_repair_policy',1) >= 2
                    and old['render_settings'].get('scale_repair_policy',1) < 2):
                # The old cutout policy could preserve pixels but break another
                # actor's pointing/gaze target. Reuse unrepaired candidates only.
                options=[o for o in options if not o[2].get('preserved_geometry')]
            all_options.extend((rank,candidate,report,previous) for rank,candidate,report in options)
        except (OSError,ValueError,KeyError):
            continue
    # Inspect every compatible rendition. A newer failed run must not hide an
    # older candidate with an intact cast. Check bytes BEFORE accepting a source;
    # one corrupt/missing candidate does not discard all other saved attempts.
    for rank,candidate,report,previous in sorted(all_options,key=lambda o:o[0]):
        try:
            data=candidate.read_bytes()
            if report.get('signature')!=previous['signature'] or report.get('png_sha256')!=hashlib.sha256(data).hexdigest():
                continue
            with Image.open(io.BytesIO(data)) as image:
                if image.size!=(1024,1024) or json.loads(image.info.get('book_asset','{}')).get('signature')!=previous['signature']:
                    continue
                info=PngImagePlugin.PngInfo()
                for key,value in image.info.items():
                    if isinstance(value,str) and key not in ('book_asset','book_source'):
                        info.add_text(key,value)
                source={'path':str(candidate),'png_sha256':hashlib.sha256(data).hexdigest(),'signature':previous['signature'],
                        'selection_rank':list(rank),'compatible_candidates_considered':len(all_options)}
                info.add_text('book_asset',json.dumps(spec,ensure_ascii=False))
                info.add_text('book_source',json.dumps(source))
                output=io.BytesIO();image.convert('RGB').save(output,format='PNG',pnginfo=info)
        except (OSError,ValueError,KeyError):
            continue
        write_json(directory/'attempt-01-render.json',{'seed':report['seed'],'prompt':report['prompt'],
                                                      'signature':spec['signature'],'reused_from':source})
        write_exclusive(directory/'attempt-01.png',output.getvalue())
        return True
    return False


def image_record(project, name):
    path = asset_path(project, name)
    return output_image_record(path)


def output_image_record(path):
    """Comfy's /view uses its output aliases, even when data lives in generation/."""
    import folder_paths
    path = Path(path).resolve()
    output = Path(folder_paths.get_output_directory()).resolve()
    for alias in ('books', 'codex/books', ''):
        base = (output / alias).resolve()
        if path.is_relative_to(base):
            relative = Path(alias) / path.relative_to(base)
            return {'filename': relative.name, 'subfolder': relative.parent.as_posix(), 'type': 'output'}
    raise ValueError('Image is outside the configured Comfy output aliases.')


def image_bytes(spec, images, prompt=None, extra_pnginfo=None):
    import io
    import numpy as np
    from PIL import Image, PngImagePlugin
    if images.shape[0] != 1:
        raise ValueError("Each book asset must contain exactly one image.")
    pixels = images[0].detach().cpu().numpy()
    if not np.isfinite(pixels).all() or float(pixels.std()) < 0.0001:
        raise ValueError(f"Render {spec['name']} contains invalid or uniform pixels; refusing to mark it complete.")
    if pixels.shape[:2] != (1024, 1024):
        raise ValueError(f"Expected a 1024-square book asset, got {pixels.shape}.")
    image = Image.fromarray(np.clip(pixels * 255, 0, 255).astype(np.uint8)).convert("RGB")
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("book_asset", json.dumps(spec, ensure_ascii=False))
    if prompt is not None:
        metadata.add_text("prompt", json.dumps(prompt, ensure_ascii=False))
    if extra_pnginfo and "workflow" in extra_pnginfo:
        metadata.add_text("workflow", json.dumps(extra_pnginfo["workflow"], ensure_ascii=False))
    data = io.BytesIO()
    image.save(data, format="PNG", pnginfo=metadata)
    return data.getvalue()


def save_asset(project, spec, images, prompt=None, extra_pnginfo=None):
    if valid_asset(project, spec):
        return
    if project.get("render_settings", {}).get("quality_required"):
        raise ValueError("This rendition requires visual approval before publishing an asset.")
    write_exclusive(asset_path(project, spec["name"]), image_bytes(spec, images, prompt, extra_pnginfo))


def review_directory(project, spec):
    # safe_asset_name rejects traversal before creating QA paths as well.
    name = safe_asset_name(spec["name"])
    path = checked_root(project) / "quality" / name[:-4]
    if not path.resolve().is_relative_to(checked_root(project)):
        raise ValueError("Quality report directory escapes the book.")
    return path


def approval_path(project, spec):
    return review_directory(project, spec) / "accepted.json"


def publish_reviewed_asset(project, spec, png, report):
    from .quality import passed, expected_scene
    if report.get("accepted") is not True or report.get("signature") != spec["signature"] or not passed(report["review"], expected_scene(project, spec)[0]):
        raise ValueError("Refusing to publish an unapproved book image.")
    if report.get("png_sha256") != hashlib.sha256(png).hexdigest():
        raise ValueError("Candidate image bytes differ from the reviewed image.")
    report = dict(report, png_sha256=hashlib.sha256(png).hexdigest())
    write_json(approval_path(project, spec), report)
    write_exclusive(asset_path(project, spec["name"]), png)
    return report

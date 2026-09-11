"""Derived review views: expose saved attempts without approving or changing them."""
import hashlib
import html
import json
import logging
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import quote

from .storage import checked_root, review_directory, valid_asset, write_json
from .story import asset_specs, digest


def atomic_view(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.preview-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def read_record(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def write_review_draft(project):
    root = checked_root(project)
    story = project['story']
    records = {}
    for spec in asset_specs(project):
        directory = review_directory(project, spec)
        attempts = []
        for path in sorted(directory.glob('attempt-*.png')):
            if not re.fullmatch(r'attempt-\d+\.png', path.name):
                continue
            report = read_record(path.with_name(path.stem + '-review.json'))
            image_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            matches = (report.get('signature') == spec['signature']
                       and report.get('png_sha256') == image_hash)
            rendered = read_record(path.with_name(path.stem + '-render.json'))
            # A finished review authenticates both the candidate and its actual
            # prompt. Pending candidates carry the same signature in PNG metadata.
            if not matches and rendered.get('signature') == spec['signature']:
                from PIL import Image
                try:
                    with Image.open(path) as img:
                        render_matches = json.loads(img.info.get('book_asset', '{}')).get('signature') == spec['signature']
                except (OSError, ValueError):
                    render_matches = False
            else:
                render_matches = matches
            actual = (report if matches and 'prompt' in report else
                      rendered if render_matches and rendered.get('signature') == spec['signature'] else {})
            strategy = read_record(path.with_name(path.stem + '-strategy.json'))
            if strategy.get('signature') != spec['signature']:
                strategy = {}
            generation = ({'prompt': actual['prompt'], 'seed': str(actual.get('seed', 'unknown')),
                           'record': path.with_name(path.stem + ('-review.json' if actual is report else '-render.json')).relative_to(root).as_posix(),
                           'strategy': strategy.get('strategy', 'not recorded')}
                          if 'prompt' in actual else None)
            if generation:
                from .generation_info import legacy
                saved_info = rendered.get('generation_info') if render_matches and rendered.get('signature') == spec['signature'] else None
                generation['info'] = saved_info or legacy(project, spec, generation['strategy'])
            if generation and generation['strategy'] in ('duplicate_removal', 'object_removal'):
                plan_suffix = '-duplicate-plan.json' if generation['strategy'] == 'duplicate_removal' else '-object-plan.json'
                plan = read_record(path.with_name(path.stem+plan_suffix))
                number = plan.get('source_attempt')
                if type(number) is int and number > 0 and plan.get('signature') == spec['signature']:
                    source = directory/f'attempt-{number:02d}.png'
                    if source.exists() and hashlib.sha256(source.read_bytes()).hexdigest() == plan.get('source_sha256'):
                        generation['source_image'] = source.relative_to(root).as_posix()
            attempts.append({'path': path.relative_to(root).as_posix(), 'sha256': image_hash,
                             'review_matches': matches,
                             'approved': matches and report.get('accepted') is True,
                             'generation': generation,
                             'review': report.get('review', {}) if matches else {},
                             'status': ('review passed' if report.get('accepted') else 'rejected') if matches else 'awaiting review'})
        approved = False
        approval_error = None
        try:
            approved = valid_asset(project, spec)
        except ValueError as exc:
            approval_error = str(exc)
        from .draft_selection import selected_draft_candidate
        choice = selected_draft_candidate(project, spec) if not approved else None
        selected = (spec['name'] if approved else str(Path(choice['path']).relative_to(root)) if choice
                    else attempts[-1]['path'] if attempts else None)
        records[spec['name']] = {'kind': spec['kind'], 'approved': approved,
                                'selected': selected, 'attempts': attempts,
                                'draft_selection': choice,
                                'approval_error': approval_error,
                                'failure': read_record(directory/'failed.json')}
        # These are the exact saved inputs for a canonical Flux redraw. Other
        # strategies can have extra repair/pose inputs, so do not mislabel them.
        if (attempts and project.get('render_settings', {}).get('renderer') == 'flux2'
                and any(a.get('generation', {}).get('strategy') == 'canonical_redraw'
                        for a in attempts if a.get('generation'))):
            reference_paths = []
            if spec.get('reference_layout') == 'cast_guide':
                guide = directory/'size-guide.png'
                if guide.exists():
                    reference_paths.append(('Cast: left to right, one of each character', guide.relative_to(root).as_posix()))
            else:
                reference_paths.extend((name, name) for name in spec['references'] if (root/name).is_file())
            if spec.get('visual_references'):
                from .visual_library import entries, reference_sheet
                import io
                for kind in ('prop', 'location'):
                    if any(e['kind'] == kind for e in entries(project, spec)):
                        sheet = directory/f'debug-{kind}-reference.png'
                        if not sheet.exists():
                            png = io.BytesIO()
                            reference_sheet(project, spec, kind).save(png, format='PNG')
                            atomic_view(sheet, png.getvalue())
                        reference_paths.append((kind.title()+' design reference', sheet.relative_to(root).as_posix()))
            records[spec['name']]['canonical_references'] = reference_paths
    manifest = {'status': 'review_draft', 'title': story['metadata']['title'],
                'note': 'Includes rejected and unfinished work. This is not publication approval.',
                'selection': 'Approved asset when available; otherwise best compared failed candidate. Until comparison succeeds, show the latest attempt. Every attempt remains available.',
                'assets': records}
    write_json(root/'drafts'/f'{digest(manifest)[:20]}.json', manifest)
    atomic_view(root/'draft-manifest.json', (json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode())
    esc = lambda value: html.escape(str(value), quote=True)

    def image(path, label):
        url = esc(quote(path, safe='/'))
        return f'<a href="{url}" target="_blank"><img loading="lazy" src="{url}" alt="{esc(label)}"></a>'

    def generation_details(attempt, record):
        data = attempt.get('generation')
        if not data:
            return '<p class="status">Exact generation prompt unavailable for this saved image.</p>'
        key = 'prompt-' + hashlib.sha256(attempt['path'].encode()).hexdigest()[:16]
        from .generation_info import METHODS
        info = data.get('info', {})
        method = METHODS.get(info.get('method'), METHODS['unknown'])
        model = info.get('model') or 'Model not recorded'
        loras = info.get('loras', [])
        model_label = ('FLUX.2 dev Turbo 8' if 'flux2' in model.lower() and any('turbo' in l['name'].lower() for l in loras)
                       else 'FLUX.2 dev' if 'flux2_dev' in model.lower() else model)
        recipe = []
        for label, key in [('steps', 'steps'), ('guidance', 'guidance'), ('CFG', 'cfg'), ('sampler', 'sampler'), ('scheduler', 'scheduler')]:
            if info.get(key) is not None:
                recipe.append(f'{label}: {info[key]}')
        if info.get('width') and info.get('height'):
            recipe.append(f'{info["width"]} × {info["height"]}')
        refs = record.get('canonical_references', []) if data['strategy'] == 'canonical_redraw' else []
        if 'reference_images' in info:
            refs = [(r['label'],r['path']) for r in info['reference_images']
                    if not Path(r['path']).is_absolute() and '..' not in Path(r['path']).parts
                    and (root/r['path']).is_file()]
        if data.get('source_image'):
            refs = [('Existing illustration before the removal edit', data['source_image'])]
        reference_html = ''.join('<figure>'+image(path, f'Image {i}: {label}')
            +f'<figcaption>Image {i}: {esc(label)}</figcaption></figure>'
            for i,(label,path) in enumerate(refs,1))
        return (f'<p class="generation-summary"><strong>{esc(method)}</strong><br>Model: {esc(model_label)}</p>'
            +'<details class="generation"><summary>Exact generation prompt and inputs</summary>'
            +f'<p class="status">Seed: <code>{esc(data["seed"])}</code> · {esc(data["strategy"])}</p>'
            +f'<p class="status">Model file: {esc(model)}<br>{esc(" · ".join(recipe))}</p>'
            +''.join(f'<p class="status">LoRA: {esc(l["name"])} · strength {esc(l["strength"])}</p>' for l in loras)
            +f'<p class="status">Settings: {esc(info.get("provenance", "not recorded"))}</p>'
            +f'<button type="button" data-copy="{key}">Copy full prompt</button> '
            +f'<a href="{esc(quote(data["record"], safe="/"))}" target="_blank">Saved raw record</a>'
            +f'<pre>{esc(data["prompt"])}</pre>'
            +('<div class="reference-inputs">'+reference_html+'</div>' if refs else '')+'</details>')

    def asset(name):
        record = records.get(name, {})
        selected = record.get('selected')
        if not selected:
            return '<div class="missing">Illustration not generated yet</div>'
        status = 'Automatically approved — still needs your review' if record['approved'] else 'Unapproved candidate — latest attempt'
        choice = record.get('draft_selection')
        if choice:
            status = f"Best failed candidate — attempt {choice['attempt']} (unapproved)"
            if choice['uncertain']:
                status += ' · comparison uncertain'
        attempts = record['attempts']
        current = next((a for a in attempts if a['path'] == selected), {})
        if record['approved'] and not current:
            current = next((a for a in reversed(attempts) if a['approved']), {})
        issues = current.get('review', {}).get('issues', [])
        if record.get('approval_error'):
            issues = [*issues, record['approval_error']]
        reasons = '<ul>'+''.join('<li>'+esc(reason)+'</li>' for reason in issues)+'</ul>' if issues else ''
        if choice:
            reasons = ('<p>'+esc(choice['reason'])+'</p><p>Comparison findings:</p><ul>'
                       +''.join('<li>'+esc(reason)+'</li>' for reason in choice['remaining_problems'])
                       +'</ul><details><summary>Original automatic review</summary>'+reasons+'</details>')
        gallery = ''.join('<figure>'+image(a['path'], a['status'])+'<figcaption>'+esc(Path(a['path']).stem+' · '+a['status'])+'</figcaption><ul>'+''.join('<li>'+esc(x)+'</li>' for x in a['review'].get('issues', []))+'</ul>'+generation_details(a,record)+'</figure>' for a in attempts)
        return image(selected, name)+f'<p class="status">{esc(status)}</p>'+reasons+generation_details(current,record)+(f'<details><summary>All {len(attempts)} saved attempts and reviews</summary><div class="attempts">{gallery}</div></details>' if attempts else '')

    rows = [f'<article><div><p class="label">COVER</p><h2>{esc(manifest["title"])}</h2></div><div>{asset("cover.png")}</div></article>']
    for page in story['pages']:
        n = page['pageNumber']
        rows.append(f'<article><div><p class="label">PAGE {n}</p><p class="prose">{esc(page["text"])}</p><details><summary>Illustration brief</summary><p>{esc(page["imagePrompt"])}</p></details></div><div>{asset(f"pages/page-{n:03d}.png")}</div></article>')
    cast = ''.join(f'<section><h3>{esc(c["name"])}</h3>{asset("characters/"+c["id"]+".png")}</section>' for c in project['production']['characters'])
    from .visual_library import entries, asset_name
    visual_library = ''.join(f'<section><h3>{esc(e["name"])}</h3>{asset(asset_name(e))}</section>' for e in entries(project))
    from .prop_groups import groups, asset_name as group_asset_name
    visual_library += ''.join(f'<section><h3>{esc(g["inner_detection"])} inside {esc(g["outer_detection"])}</h3>{asset(group_asset_name(g))}</section>' for g in groups(project))
    visual_section = ('<h2>Prop and location references</h2><div class="cast">'+visual_library+'</div>') if visual_library else ''
    scenes = [r for r in records.values() if r['kind'] == 'scene']
    count = sum(r['approved'] for r in scenes)
    document = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>'''+esc(manifest['title'])+''' — review draft</title><style>
*{box-sizing:border-box}body{margin:0;background:#f5f0e6;color:#2c3028;font:17px/1.6 system-ui}main{max-width:1200px;margin:auto;padding:32px}
h1{font:42px/1.2 Georgia,serif}.notice{padding:18px;background:#f2ddd0;border-left:4px solid #9a442d}
article{display:grid;grid-template-columns:1fr 1fr;gap:32px;border-top:1px solid #cfc7b8;padding:32px 0}.prose{font:25px/1.65 Georgia,serif;white-space:pre-line}
img{width:100%;height:auto;display:block}.label,.status,figcaption{font-size:13px}.missing{padding:80px 20px;background:#e6e1d6;text-align:center}
.cast,.attempts{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}figure{margin:0}details{font-size:14px}a{color:#426249}
.generation{margin:12px 0;padding:10px;border:1px solid #cfc7b8}.generation pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:540px;overflow:auto;font:13px/1.6 monospace;background:#fffbf3;padding:12px}.generation button{font:inherit;cursor:pointer;padding:5px 10px}.reference-inputs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}article>div,figure{min-width:0}
@media(max-width:700px){main{padding:20px}article{grid-template-columns:1fr}.cast,.attempts{grid-template-columns:1fr 1fr}.prose{font-size:22px}}
@media print{details{display:none}article{break-inside:avoid}}
</style><main><header><p class="label">BOOK REVIEW DRAFT</p><h1>'''+esc(manifest['title'])+f'''</h1><p class="notice">{count} of {len(scenes)} cover/page illustrations have passed automatic checks. Rejected attempts remain visible for you to judge. Missing artwork is shown as a placeholder. This draft is saved even if the run fails.</p>
<p>Refresh to see the latest saved results. <a href="story.json">Story JSON</a> · <a href="draft-manifest.json">Draft status and image records</a></p></header><h2>Character references</h2><div class="cast">{cast}</div>{visual_section}{''.join(rows)}</main><script>
document.addEventListener('click', async event => {{
 const button=event.target.closest('button[data-copy]'); if(!button)return;
 const prompt=button.parentElement.querySelector('pre');
 try {{await navigator.clipboard.writeText(prompt.textContent);button.textContent='Copied';}}
 catch {{const range=document.createRange();range.selectNodeContents(prompt);const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);button.textContent='Prompt selected — copy with Ctrl+C';}}
}});
</script></html>'''
    path = root/'review-draft.html'
    atomic_view(path, document.encode())
    return path


def refresh_review_draft(project):
    try:
        return write_review_draft(project)
    except Exception:
        logging.exception('Book v2: could not update the review draft; original generation outputs remain saved.')


def register_preview_routes():
    from aiohttp import web
    from server import PromptServer
    from .storage import books_root

    @PromptServer.instance.routes.get('/book-builder/books/{tail:.*}')
    async def book_file(request):
        root = books_root().resolve()
        path = (root/request.match_info['tail']).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() not in {'.html', '.png', '.jpg', '.json', '.pdf'}:
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={'Cache-Control': 'no-store'})

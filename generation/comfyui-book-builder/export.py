"""Readable book exports; prose is typeset, never sent to an image model."""
import html
import io
import json
from pathlib import Path

from .story import asset_specs
from .storage import asset_path, checked_root, valid_asset, write_exclusive, write_json


def font(size):
    from PIL import ImageFont
    for path in ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def wrap(draw, text, face, width):
    lines = []
    for paragraph in text.splitlines():
        current = ""
        for word in paragraph.split():
            if draw.textlength(word, font=face) > width:
                raise ValueError("A book word is too long to fit the page; revise its text.")
            candidate = f"{current} {word}".strip()
            if current and draw.textlength(candidate, font=face) > width:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    return lines


def laid_out_page(image, text, label):
    from PIL import Image, ImageDraw
    canvas = Image.new("RGB", (1120, 1536), "#fffaf1")
    canvas.paste(image.convert("RGB").resize((1024, 1024)), (48, 48))
    draw = ImageDraw.Draw(canvas)
    for size in range(34, 15, -1):
        face = font(size)
        lines = wrap(draw, text, face, 984)
        line_height = int(size * 1.45)
        if len(lines) * line_height <= 342:
            break
    else:
        raise ValueError("Book text cannot fit the layout. Reduce words per page.")
    y = 1110
    for line in lines:
        draw.text((68, y), line, fill="#302d2a", font=face)
        y += line_height
    draw.text((560, 1492), label, anchor="mm", fill="#827563", font=font(20))
    return canvas


def export_book(project, export_pdf):
    from PIL import Image, ImageDraw
    import numpy as np
    import torch
    root = checked_root(project)
    from .preview import refresh_review_draft
    draft_path = refresh_review_draft(project)
    quality_required = project.get("render_settings", {}).get("quality_required", False)
    if quality_required:
        from .story import digest
        from .quality import passed
        approval = project.get("story_quality", {})
        package = {"story": project["story"], "production": project["production"]}
        if (approval.get("accepted") is not True or approval.get("package_hash") != digest(package)
                or not passed(approval.get("review", {}))):
            raise ValueError("Book export requires editorial approval matching the exact story and production plan.")
    specs = asset_specs(project)
    missing = [s["name"] for s in specs if not valid_asset(project, s)]
    if missing:
        from .draft_selection import try_select_review_candidate
        for spec in specs:
            if spec['name'] in missing:
                try_select_review_candidate(project, spec)
        draft_path = refresh_review_draft(project)
        from .story import digest
        write_json(root/'quality'/f'incomplete-{digest(missing)[:12]}.json',
                   {'status':'incomplete', 'unapproved_assets':missing,
                    'approved_asset_count':len(specs)-len(missing), 'total_assets':len(specs)})
        raise ValueError(f"Book is incomplete: {', '.join(missing)}. Read the saved draft: {draft_path}")
    book = project["book"]
    manifest = {
        "status": "complete", "title": book["title"], "page_count": len(book["pages"]),
        "character_count": len(book["characters"]), "seed": project["config"]["seed"],
        "story": project["story"], "production": project["production"], "story_settings": project["config"], "render_settings": project["render_settings"],
        "assets": specs,
        "quality": {"editorial_approved": quality_required, "visual_approved": quality_required,
                    "reviewer": project["render_settings"].get("review_model"),
                    "note": "Automated reviews are fallible; inspect the readable book before publishing."},
    }
    if project.get('art_plan'):
        manifest['visual_state'] = project['art_plan']
        manifest['state_edits'] = project.get('state_edits',{})
    if project.get('reference_adoptions'):
        manifest['reference_adoptions'] = project['reference_adoptions']
    markdown = [f"# {book['title']}", "", book["summary"], "", "![Cover](cover.png)"]
    sections = [f'<section class="cover"><img src="cover.png" alt="Cover illustration"><h1>{html.escape(book["title"])}</h1></section>']
    for page in book["pages"]:
        n = page["page_number"]
        markdown += ["", f"## Page {n}", "", page["text"], "", f"![Page {n}](pages/page-{n:03d}.png)"]
        prose = "<br>".join(html.escape(page["text"]).splitlines())
        sections.append(f'<section><img src="pages/page-{n:03d}.png" alt="Illustration for page {n}"><p>{prose}</p><footer>{n}</footer></section>')
    document = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(book['title'])}</title><style>
*{{box-sizing:border-box}}body{{margin:0;padding:40px 16px;background:#e9e3d9;color:#302d2a;font-family:Georgia,serif}}
main{{max-width:850px;margin:auto}}section{{background:#fffaf1;padding:28px;margin-bottom:40px;break-after:page}}
img{{display:block;width:100%;height:auto}}h1{{font-size:clamp(28px,4vw,44px);text-align:center;font-weight:500;line-height:1.2}}
p{{font-size:clamp(20px,3vw,28px);line-height:1.65;margin:28px 18px}}footer{{text-align:center;color:#827563;font:14px sans-serif}}
@media print{{body{{padding:0;background:white}}main{{max-width:none}}section{{margin:0;padding:10mm}}p{{font-size:18pt}}}}
</style><main>{''.join(sections)}</main></html>'''
    write_exclusive(root / "story.md", ("\n".join(markdown) + "\n").encode())
    write_exclusive(root / "book.html", document.encode())
    import_guide = [
        f"# Import {book['title']} into onemorebook", "",
        "1. Open the app's Upload Story page and paste the contents of story.json.",
        "2. Select cover.png as the cover image.",
        "3. Select pages/page-001.png for page 1, page-002.png for page 2, and so on.",
        "4. If uploading character images, use the mapping below.", "",
    ]
    import_guide += [f"- {c['name']}: characters/{c['id']}.png" for c in book["characters"]]
    import_guide += ["", "The app assigns its database ID and createdAt value during upload. Do not paste manifest.json or plan.json into its story field."]
    write_exclusive(root / "IMPORT-TO-ONEMOREBOOK.md", ("\n".join(import_guide) + "\n").encode())
    # Save the exact prose separately from the artwork even without PDF export.
    for page in book["pages"]:
        write_exclusive(root / "pages" / f"page-{page['page_number']:03d}.txt", (page["text"] + "\n").encode())
    if export_pdf and not (root / "book.pdf").exists():
        pages = []
        for name, text, label in [("cover.png", book["title"], "")] + [(f"pages/page-{p['page_number']:03d}.png", p["text"], str(p["page_number"])) for p in book["pages"]]:
            with Image.open(asset_path(project, name)) as image:
                laid_out = laid_out_page(image, text, label)
            png = io.BytesIO()
            laid_out.save(png, format="PNG")
            write_exclusive(root / "layout" / name.replace("pages/", ""), png.getvalue())
            pages.append(laid_out)
        pdf = io.BytesIO()
        pages[0].save(pdf, format="PDF", save_all=True, append_images=pages[1:], resolution=144.0, title=book["title"])
        write_exclusive(root / "book.pdf", pdf.getvalue())
    thumbs = [("cover.png", "Cover")] + [(f"pages/page-{p['page_number']:03d}.png", f"Page {p['page_number']}") for p in book["pages"]]
    sheet = Image.new("RGB", (4 * 256, ((len(thumbs) + 3) // 4) * 288), "#fffaf1")
    draw = ImageDraw.Draw(sheet)
    for i, (name, label) in enumerate(thumbs):
        x, y = (i % 4) * 256, (i // 4) * 288
        with Image.open(asset_path(project, name)) as image:
            sheet.paste(image.convert("RGB").resize((248, 248)), (x + 4, y + 4))
        draw.text((x + 128, y + 270), label, anchor="mm", fill="#302d2a", font=font(18))
    data = io.BytesIO()
    sheet.save(data, format="PNG")
    write_exclusive(root / "contact-sheet.png", data.getvalue())
    write_json(root / "book.json", project["story"])
    if quality_required:
        from .storage import approval_path
        write_json(root / "quality-report.json", {"story": project["story_quality"],
                   "assets": {s["name"]: json.loads(approval_path(project, s).read_text()) for s in specs}})
    write_json(root / "manifest.json", manifest)
    summary = (f"{book['title']}\n{len(book['pages'])} pages, {len(book['characters'])} characters, cover and style reference.\n"
               f"Saved to: {root}\nOpen book.html to read the book." + ("\nPDF: book.pdf" if export_pdf else ""))
    return torch.from_numpy(np.array(sheet).astype(np.float32) / 255.0).unsqueeze(0), summary, str(root)

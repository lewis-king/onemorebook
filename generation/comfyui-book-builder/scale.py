"""A private visual cast-size guide assembled from the approved portraits."""
import re


def cast_height(character):
    value = character.get("height_cm")
    if value is None:
        match = re.search(r"\b(\d+(?:\.\d+)?)\s*cm\s*tall\b", character["appearance"], re.I)
        value = float(match[1]) if match else None
    return float(value) if value is not None and 1 <= float(value) <= 1000 else None


def height_targets(cast):
    """Compute canonical ratios in code; body landmarks are not units of height."""
    if not cast or not all(cast_height(c) for c in cast):
        return []
    anchor = max(cast, key=cast_height)
    return [{'id': c['id'], 'height_cm': cast_height(c), 'anchor_id': anchor['id'],
             'anchor_height_cm': cast_height(anchor),
             'standing_height_ratio': cast_height(c)/cast_height(anchor),
             'percent_of_anchor_height': round(100*cast_height(c)/cast_height(anchor), 1)}
            for c in cast]


def guide_cast(project, spec):
    from .quality import expected_scene
    if spec["kind"] != "scene":
        return []
    ids = expected_scene(project, spec)[0]
    by_id = {c["id"]:c for c in project["book"]["characters"]}
    cast = [by_id[cid] for cid in ids]
    return cast if len(cast)>1 and all(cast_height(c) for c in cast) else []


def make_scale_guide(project, spec):
    import numpy as np
    from PIL import Image
    from .storage import asset_path
    cast = guide_cast(project,spec)
    if not cast:
        raise ValueError("A scale guide needs at least two characters with explicit physical heights.")
    crops = []
    from .state_ledger import character_reference
    scene = project['book']['cover'] if spec['name'] == 'cover.png' else next(
        p for p in project['book']['pages'] if spec['name'] == f"pages/page-{p['page_number']:03d}.png")
    for c in cast:
        with Image.open(asset_path(project,character_reference(project, scene, c['id']))) as image:
            image=image.convert("RGB")
            pixels=np.asarray(image).astype(np.int16)
            border=np.concatenate([pixels[:12].reshape(-1,3),pixels[-12:].reshape(-1,3),
                                   pixels[:,:12].reshape(-1,3),pixels[:,-12:].reshape(-1,3)])
            background=np.median(border,axis=0)
            mask=np.max(np.abs(pixels-background),axis=2)>45
            ys,xs=np.where(mask)
            if len(xs)<100:
                raise ValueError(f"Cannot locate {c['name']} on its portrait backdrop.")
            box=(max(0,int(xs.min())-8),max(0,int(ys.min())-8),min(image.width,int(xs.max())+9),min(image.height,int(ys.max())+9))
            crops.append(image.crop(box))
    scale=700/max(cast_height(c) for c in cast)
    heights=[cast_height(c)*scale for c in cast]
    widths=[h*im.width/im.height for h,im in zip(heights,crops)]
    fit=min(1.0,920/sum(widths))
    heights=[max(12,round(h*fit)) for h in heights]
    widths=[max(8,round(w*fit)) for w in widths]
    gap=(1024-sum(widths))/(len(cast)+1)
    board=Image.new("RGB",(1024,1024),(250,247,235))
    x=gap
    for im,w,h in zip(crops,widths,heights):
        board.paste(im.resize((w,h),Image.Resampling.LANCZOS),(round(x),920-h))
        x+=w+gap
    return board

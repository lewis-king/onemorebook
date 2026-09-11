"""Recover measured cutout locations only when saved pixels prove preservation."""
import hashlib
import io
import json
from pathlib import Path


def preserved_boxes(project, spec, png, attempt):
    import numpy as np
    from PIL import Image
    from .storage import books_root, review_directory

    def sha(data):
        return hashlib.sha256(data).hexdigest()

    allowed = (books_root().resolve(), (books_root().parent/'codex/books').resolve())
    visited = set()

    def read_image(data):
        image = Image.open(io.BytesIO(data))
        return np.array(image.convert('RGB')), image.info

    def region_equal(a, b, box):
        x0,y0,x1,y1 = map(int,box)
        if a.shape != b.shape or not (0<=x0<x1<=a.shape[1] and 0<=y0<y1<=a.shape[0]):
            return False
        # Comfy's float-to-PNG conversion can round a channel by one level.
        return bool(np.max(np.abs(a[y0:y1,x0:x1].astype('int16')-b[y0:y1,x0:x1].astype('int16')))<=1)

    def walk(path, data, depth=0):
        path = Path(path).resolve()
        if depth>8 or path in visited or not any(path.is_relative_to(root) for root in allowed):
            return {}
        visited.add(path)
        pixels, info = read_image(data)
        source = json.loads(info.get('book_source','{}'))
        if source:
            source_path = Path(source['path']).resolve()
            if not any(source_path.is_relative_to(root) for root in allowed):return {}
            source_data = source_path.read_bytes()
            previous, _ = read_image(source_data)
            if sha(source_data)!=source['png_sha256'] or not np.array_equal(pixels,previous):return {}
            return walk(source_path,source_data,depth+1)
        record_path = path.with_name(path.stem+'-repair.json')
        if not record_path.exists():return {}
        record = json.loads(record_path.read_text())
        signature = json.loads(info.get('book_asset','{}')).get('signature')
        if not record.get('prepared') or record.get('signature')!=signature:return {}
        prepared_data = path.with_name(path.stem+'-repair-image.png').read_bytes()
        mask_data = path.with_name(path.stem+'-repair-mask.png').read_bytes()
        if sha(prepared_data)!=record['image_sha256'] or sha(mask_data)!=record['mask_sha256']:return {}
        prepared, _ = read_image(prepared_data)
        mask = np.array(Image.open(io.BytesIO(mask_data)).convert('L'))
        if prepared.shape!=pixels.shape or mask.shape!=pixels.shape[:2]:return {}
        source_path = path.with_name(f"attempt-{record['source_attempt']:02d}.png")
        source_data = source_path.read_bytes()
        if sha(source_data)!=record['source_sha256']:return {}
        prior, _ = read_image(source_data)
        result = {cid:box for cid,box in walk(source_path,source_data,depth+1).items()
                  if region_equal(pixels,prior,box['bbox'])}
        geometry = record['geometry']
        x,y = map(int,geometry['position'])
        x0,y0,x1,y1 = geometry['source_bbox']
        w,h = round((x1-x0)*geometry['factor']),round((y1-y0)*geometry['factor'])
        if not (0<=x<x+w<=pixels.shape[1] and 0<=y<y+h<=pixels.shape[0]):return result
        core = mask[y:y+h,x:x+w]==0
        delta = np.abs(pixels[y:y+h,x:x+w].astype('int16')-prepared[y:y+h,x:x+w].astype('int16'))
        if int(core.sum()) < max(50,w*h*.1) or np.max(delta[core])>1:return result
        result[record['target']] = {'bbox':[x,y,x+w,y+h], 'image_size':[pixels.shape[1],pixels.shape[0]],
            'identity_source':'verified_preserved_cutout', 'source':str(path), 'png_sha256':sha(data),
            'evidence':'SAM cutout coordinates; protected foreground pixels match the prepared repair.'}
        return result

    if attempt is None:return {}
    try:
        current = review_directory(project,spec)/f'attempt-{attempt:02d}.png'
        if sha(current.read_bytes())!=sha(png):return {}
        return walk(current,png)
    except (OSError,ValueError,KeyError,TypeError):
        return {}

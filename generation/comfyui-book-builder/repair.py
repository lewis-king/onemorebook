"""Conservative physical scale repair; identity pixels survive background inpainting."""
import hashlib
import io
import json
import logging
from pathlib import Path

from .scale import cast_height
from .story import object_schema
from .storage import review_directory, write_json, write_exclusive


def eligible_scale_repair(report):
    review = report.get('review', {})
    chars = review.get('characters', [])
    return (all(review.get('checks', {}).values()) and not review.get('uncertain', True)
            and review.get('unexpected_character_count') == 0 and len(chars) > 1
            and all(c['count'] == 1 and c['identity_matches'] and c['appearance_matches'] for c in chars)
            and any(not c['scale_matches'] for c in chars))


def review_resize_relations(project, spec, png, target, anchor, generate=None):
    """Non-contact gestures can depend on a figure's exact position too."""
    from .quality import json_model
    schema = object_schema({'can_resize_independently':{'type':'boolean'},
        'anchored_interactions':{'type':'array','items':{'type':'string','minLength':1}},
        'evidence':{'type':'string','minLength':1},'uncertain':{'type':'boolean'},
        'target_holds_object':{'type':'boolean'},
        'held_objects':{'type':'array','items':{'type':'string','minLength':1}}})
    prompt = ('Assess ONLY whether shrinking TARGET about its feet/base while leaving EVERY other '
        'character and prop pixel fixed would preserve the visible interactions. Do not judge whether '
        'the target is too large, its identity or the general art quality. A pointing finger aimed at '
        'its face, clothing or paw depends on that location even with no contact. A gaze aimed at a '
        'specific face, shared held object, handshake, embrace, handoff or other aligned action also '
        'depends on both participants. FIRST inspect TARGET hands/paws for any carried or held prop, '
        'including a jar, ball, stick, tool or basket. The segmentation moves ONLY the body, leaving '
        'ALL separate prop pixels at their old position. Even a prop held by TARGET alone makes '
        'independent shrinking unsafe: its hands would move away and leave the prop floating. '
        'Report target_holds_object=true and list each held object in that case. '
        'If TARGET points at another figure or object, shrinking its '
        'arm moves that ray too. List these anchored interactions in EITHER direction. Ordinary '
        'nearness or independently looking out toward the viewer is not an anchored interaction. '
        'A passive foot/base resting on a flat supporting surface is allowed only if nothing else '
        'depends on the old figure position. Return can_resize_independently=true only when no '
        'visible relationship would need the other actor/prop to be adjusted; be uncertain if unclear.\n'
        +'TARGET: '+json.dumps(target)+'\nANCHOR: '+json.dumps(anchor))
    if project['render_settings'].get('scale_repair_policy',1)>=4:
        schema['properties'].update(can_resize_with_held_objects={'type':'boolean'},
            other_anchored_interactions={'type':'array','items':{'type':'string','minLength':1}})
        schema['required'].extend(['can_resize_with_held_objects','other_anchored_interactions'])
        prompt += ('\nAssess a SECOND option separately: move TARGET and its exclusively held objects '
            'together as one unit, preserving every grip and their relative arrangement. Held objects '
            'must be inanimate portable props, never another actor/animal or fixed scenery. All other '
            'actors and objects remain fixed. can_resize_with_held_objects is true ONLY when the '
            'listed props are carried solely by TARGET and this group has no coupled relationship '
            'with anyone/anything outside it. List outside contacts, shared props, handoffs, embraces, '
            'pointing rays and directed gaze in other_anchored_interactions. The self-held prop '
            'alone is not an outside relationship. Shared ownership or occlusion by another actor '
            'makes this option unsafe. A jar carried by TARGET alone can move with its hands, '
            'even though body-only resizing is unsafe. No held objects means this second option '
            'is unnecessary and false. Unclear ownership or interactions require uncertain=true.')
    if project['render_settings'].get('scale_repair_policy',1)>=5:
        schema['properties']['target_grounded']={'type':'boolean'}
        schema['required'].append('target_grounded')
        prompt=prompt.replace('pointing rays and directed gaze in other_anchored_interactions.',
            'story-critical pointing rays and explicitly required gaze in other_anchored_interactions.')
        page=next((p for p in project['book']['pages']
                   if spec.get('name')==f"pages/page-{p['page_number']:03d}.png"),None)
        prose=page['text'] if page else project['book'].get('cover',{}).get('scene_prompt','')
        prompt += ('\nFor the SECOND, grouped option, distinguish the necessary prose action from '
            'incidental staging. Ordinary looking/facing toward a friend is not a fixed geometric '
            'contact and must not block a size correction merely because the exact eye-line shifts. '
            'List gaze only when the prose requires a specific visual target AND resizing demonstrably '
            'breaks that necessary action. Physical shared grips, embraces, supports and meaningful '
            'pointing directions remain blocking even if not mentioned in the prose. '
            'target_grounded=true requires the target feet/base visibly supported by ordinary ground '
            'at the same depth as the anchor, not held by another actor, riding, perched on a prop '
            'or floating. Its own portable hand-held prop does not remove ground support. '
            'If the support cannot be seen clearly, use false.\nPROSE EVENT: '+prose)
    return (generate or json_model)(project['config']['ollama_url'],project['render_settings']['review_model'],prompt,schema,[png])


def resize_relations_allow(audit):
    return (audit['can_resize_independently'] is True and audit['uncertain'] is False
            and audit['anchored_interactions'] == []
            and audit.get('target_holds_object', False) is False and not audit.get('held_objects', []))


def resize_group_allow(audit, require_grounded=False):
    return (audit.get('can_resize_with_held_objects') is True and audit.get('uncertain') is False
            and audit.get('target_holds_object') is True and 1<=len(audit.get('held_objects',[]))<=2
            and audit.get('other_anchored_interactions')==[]
            and (not require_grounded or audit.get('target_grounded') is True))


def group_resize_candidate(report, cid):
    """A carried prop can disqualify body-only resizing but still allow an audit."""
    geometry=report.get('geometry',{}).get(cid,{})
    pose=next((c for c in report.get('scale_review',{}).get('characters',[]) if c['id']==cid),{})
    return (geometry.get('measurement_decisive') is True and geometry.get('relative_factor',0)>1.4
            and pose.get('pose') in ('standing_upright','standing_four_legs')
            and pose.get('full_body_visible') is True and pose.get('same_depth_as_largest') is True)


def locate_held_objects(png, names, other_boxes):
    import re
    from .detection import detect_cast
    # DINO may correctly label "jar" without repeating its contents. Query the
    # physical object; keep the full description for ownership/provenance.
    cast=[{'id':f'held_{i}','appearance':name,
           'detection_prompt':re.split(r'\b(?:of|with|containing|filled)\b',name,flags=re.I)[0].strip()}
          for i,name in enumerate(names)]
    known,ambiguous=detect_cast(png,cast,return_candidates=True)
    if set(known)!={c['id'] for c in cast}:
        raise ValueError('Held props could not be uniquely detected; do not resize the body alone.')
    boxes=[]
    for character in cast:
        detection=known[character['id']];box=detection['bbox'];w,h=detection['image_size']
        area=(box[2]-box[0])*(box[3]-box[1])
        for other in other_boxes:
            overlap=max(0,min(box[2],other[2])-max(box[0],other[0]))*max(0,min(box[3],other[3])-max(box[1],other[1]))
            if area<=0 or overlap/area>.03:
                raise ValueError('Held prop overlaps a different actor; group resizing is unsafe.')
        boxes.append([round(v*1000/(w if i%2==0 else h)) for i,v in enumerate(box)])
    return boxes,known


def localize(project, spec, png, target, anchor, generate=None):
    from .quality import json_model
    generate = generate or json_model
    box = {'type':'array','items':{'type':'integer','minimum':0,'maximum':1000},'minItems':4,'maxItems':4}
    schema = object_schema({'target_bbox':box, 'anchor_bbox':box,
        'anchor_standing_upright':{'type':'boolean'}, 'target_full_body_visible':{'type':'boolean'},
        'same_depth':{'type':'boolean'}, 'independent_ground_contact':{'type':'boolean'},
        'evidence':{'type':'string'},'uncertain':{'type':'boolean'}})
    return generate(project['config']['ollama_url'], project['render_settings']['review_model'],
        'Locate TWO figures in this image for segmentation. Return bounding boxes [left,top,right,bottom] '
        'in normalized 0..1000 coordinates. Enclose the ENTIRE specified figure, including hair/ears, '
        'feet and tail, excluding shadows. Do not assess whether its size is correct. '
        'anchor_standing_upright requires the anchor fully visible, upright and standing, not kneeling '
        'or sitting. same_depth means both occupy approximately the same distance from the viewer. '
        'independent_ground_contact requires the target on the ground, not held, riding something, '
        'holding an object, intertwined or overlapping another figure. Be conservative if unsure. '
        'TARGET: '+json.dumps(target)+'\nANCHOR: '+json.dumps(anchor), schema, [png])


def validate_support_contact(target, anchor):
    """A palm/perch resize is allowed only if contact is confined to the feet/base."""
    import cv2
    import numpy as np
    ys,_=np.where(target)
    if not len(ys):raise ValueError('No target mask.')
    contact=(target>0)&(cv2.dilate(anchor,np.ones((15,15),np.uint8))>0)
    cy,_=np.where(contact)
    if len(cy)<3 or int(cy.min()) < int(ys.min())+.75*(int(ys.max())-int(ys.min())):
        raise ValueError('Supported figure is not isolated above a clear base contact; use a fresh composition.')


def validate_mask_connectivity(mask):
    """An occluded/disconnected actor cannot be relocated as an intact cutout."""
    import cv2
    import numpy as np
    binary=(mask>0).astype(np.uint8)
    _,_,stats,_=cv2.connectedComponentsWithStats(binary,8)
    areas=sorted((int(s[cv2.CC_STAT_AREA]) for s in stats[1:]),reverse=True)
    total=sum(areas)
    if not total:
        raise ValueError('No target mask.')
    # Ignore tiny segmentation speckles, but never leave or move a substantial
    # detached part as if it were one complete figure. Use a fresh composition.
    if len(areas)>1 and sum(areas[1:])>max(64,total*.01):
        raise ValueError('Target segmentation has disconnected body/background pieces; use a fresh composition.')
    return {'components':len(areas),'largest_fraction':areas[0]/total}


def prepare_pixels(png, boxes, target_height, anchor_height, checkpoint, supported_contact=False,
                   placement='feet', protected_boxes=(), thin_tail=False, held_boxes=()):
    import cv2
    import numpy as np
    from PIL import Image, ImageFilter
    import torch
    from segment_anything import SamPredictor, sam_model_registry
    pixels = np.array(Image.open(io.BytesIO(png)).convert('RGB'))
    height,width = pixels.shape[:2]
    previous_threads = torch.get_num_threads()
    try:
        torch.set_num_threads(min(8, previous_threads))
        model = sam_model_registry['vit_b'](checkpoint=str(checkpoint)).to('cpu')
        predictor = SamPredictor(model)
        predictor.set_image(pixels)
        masks=[]
        for coords in [*boxes,*held_boxes]:
            if coords[0]>=coords[2] or coords[1]>=coords[3]:
                raise ValueError('Invalid localization box.')
            box=np.array(coords,dtype=float)*np.array([width,height,width,height])/1000
            candidates,scores,_=predictor.predict(box=box,multimask_output=True)
            mask=candidates[int(np.argmax(scores))].astype(np.uint8)*255
            if float(max(scores))<.85 or np.count_nonzero(mask)<100:
                raise ValueError('Segmentation confidence/area insufficient for an identity-preserving repair.')
            masks.append(mask)
    finally:
        torch.set_num_threads(previous_threads)
    target,anchor=masks[:2]
    ys,xs=np.where(target); ay,ax=np.where(anchor)
    x0,x1,y0,y1=int(xs.min()),int(xs.max()+1),int(ys.min()),int(ys.max()+1)
    factor=(int(ay.max()-ay.min()+1)*target_height/anchor_height)/(y1-y0)
    if not .20<=factor<=.85:
        raise ValueError(f'Geometry does not support a conservative shrink repair (factor={factor:.3f}).')
    for prop in masks[2:]:
        # A detector/LLM label alone cannot establish a visible grip. The
        # segmented prop must actually touch the target's body/hand pixels.
        if np.count_nonzero((prop>0)&(cv2.dilate(target,np.ones((11,11),np.uint8))>0))<3:
            raise ValueError('Held prop segmentation does not meet the target hands/body.')
        target=np.maximum(target,prop)
    validate_mask_connectivity(target)
    if np.count_nonzero((target>0)&(anchor>0))>min(np.count_nonzero(target),np.count_nonzero(anchor))*.005:
        raise ValueError('Character masks overlap; use a fresh composition.')
    if supported_contact:
        validate_support_contact(target,anchor)
    sprite=Image.fromarray(pixels).convert('RGBA')
    sprite.putalpha(Image.fromarray(target).filter(ImageFilter.GaussianBlur(.5)))
    gy,gx=np.where(target);gx0,gx1,gy0,gy1=int(gx.min()),int(gx.max()+1),int(gy.min()),int(gy.max()+1)
    sprite=sprite.crop((gx0,gy0,gx1,gy1))
    w,h=round(sprite.width*factor),round(sprite.height*factor)
    sprite=sprite.resize((w,h),Image.Resampling.LANCZOS)
    # Clear a padded source region too: fine tails and cast shadows can extend
    # outside the segmented body. Reconstruct this scenery through inpainting.
    removal=cv2.dilate(target,np.ones((17,17),np.uint8))
    if thin_tail:
        padx=round((x1-x0)*.55);pady=max(12,round((y1-y0)*.15))
        removal[max(0,y0-pady):min(height,y1+pady),max(0,x0-padx):min(width,x1+padx)]=255
    removal=np.array(Image.fromarray(removal).filter(ImageFilter.GaussianBlur(3)))
    # Never erase any pixels from the size anchor.
    removal[cv2.dilate(anchor,np.ones((7,7),np.uint8))>0]=0
    for box in protected_boxes:
        bx0,by0,bx1,by1=[round(v*(width if i%2==0 else height)/1000) for i,v in enumerate(box)]
        removal[max(0,by0-8):min(height,by1+8),max(0,bx0-8):min(width,bx1+8)]=0
    background=cv2.inpaint(pixels,removal,9,cv2.INPAINT_TELEA)
    canvas=Image.fromarray(background).convert('RGBA')
    origin_x=(x0+x1)/2;origin_y=(y0+y1)/2 if placement=='center' else y1
    position=(round(origin_x+(gx0-origin_x)*factor),round(origin_y+(gy0-origin_y)*factor))
    canvas.alpha_composite(sprite,position)
    protected=Image.new('L',(width,height));protected.paste(sprite.getchannel('A'),position)
    # Protect actual character pixels, allowing the generated background right
    # up to the antialiased edge. A dilated protection mask left a pale halo.
    alpha=np.array(protected,dtype=np.float32)/255
    repair=np.rint(removal*(1-alpha)).astype(np.uint8)
    return canvas.convert('RGB'),Image.fromarray(repair),{'factor':factor,'source_bbox':[x0,y0,x1,y1],
        'anchor_bbox':[int(ax.min()),int(ay.min()),int(ax.max()+1),int(ay.max()+1)],'position':position,'placement':placement,
        'group_bbox':[gx0,gy0,gx1,gy1],'held_objects_count':len(held_boxes)}


def try_scale_repair(project, spec, source_attempt, attempt, report):
    if not eligible_scale_repair(report):
        return False
    directory=review_directory(project,spec)
    prefix=directory/f'attempt-{attempt:02d}-repair'
    record_path=prefix.with_suffix('.json')
    if record_path.exists():
        return json.loads(record_path.read_text())['prepared']
    # Several independently oversized figures can be corrected in consecutive
    # attempts, but never repeatedly shrink the same figure after a failed repair.
    repaired_ids=set()
    ancestor=source_attempt
    while (ancestor_path:=directory/f'attempt-{ancestor:02d}-repair.json').exists():
        previous=json.loads(ancestor_path.read_text())
        if previous.get('prepared'):
            repaired_ids.add(previous['target'])
        older=previous.get('source_attempt',ancestor)
        if older>=ancestor:break
        ancestor=older
    eligible=[c['id'] for c in report['review']['characters'] if not c['scale_matches']
              and c['id'] not in repaired_ids and (report.get('geometry',{}).get(c['id'],{}).get('safe_to_resize')
                  or (project['render_settings'].get('scale_repair_policy',1)>=5 and group_resize_candidate(report,c['id'])))]
    if not eligible:
        return False
    target_id=max(eligible,key=lambda cid:report['geometry'][cid]['relative_factor'])
    ids={c['id'] for c in report['review']['characters']}
    cast=[c for c in project['book']['characters'] if c['id'] in ids]
    if not all(cast_height(c) for c in cast):
        return False
    target=next(c for c in cast if c['id']==target_id)
    anchor=max(cast,key=cast_height)
    if target==anchor:
        return False
    import folder_paths
    checkpoint=Path(folder_paths.models_dir)/'sams/sam_vit_b_01ec64.pth'
    if not checkpoint.is_file():
        return False
    png=(directory/f'attempt-{source_attempt:02d}.png').read_bytes()
    if report.get('png_sha256')!=hashlib.sha256(png).hexdigest():
        raise ValueError('Scale repair source differs from its reviewed image.')
    held_names=[]
    if project['render_settings'].get('scale_repair_policy',1) >= 2:
        relation_path=directory/f'attempt-{attempt:02d}-resize-relations.json'
        if relation_path.exists():
            saved=json.loads(relation_path.read_text())
            if saved['source_sha256'] != report['png_sha256'] or saved['target'] != target_id:
                raise ValueError('Saved resize relation audit differs from its source.')
            relations=saved['review']
        else:
            relations=review_resize_relations(project,spec,png,target,anchor)
            write_json(relation_path,{'source_sha256':report['png_sha256'],'target':target_id,'review':relations})
        if (project['render_settings'].get('scale_repair_policy',1)>=4
                and resize_group_allow(relations,require_grounded=project['render_settings'].get('scale_repair_policy',1)>=5)):
            held_names=relations['held_objects']
        elif not resize_relations_allow(relations):
            write_json(record_path,{'prepared':False,'signature':spec['signature'],
                'source_attempt':source_attempt,'source_sha256':report['png_sha256'],
                'target':target_id,'anchor':anchor['id'],
                'reason':'Independent resize would break or cannot verify a coupled interaction.',
                'relations':relations})
            return False
    location_path=directory/f'attempt-{attempt:02d}-localization.json'
    measured=report.get('geometry',{}).get(target_id)
    detections=dict(report.get('detections',{}))
    for cid,geometry in report.get('geometry',{}).items():
        detections[cid]=geometry['target'];detections[geometry['anchor_id']]=geometry['anchor']
    if any(c['id'] not in detections for c in cast):
        return False
    w,h=next(iter(detections.values()))['image_size']
    normalize=lambda box:[round(v*1000/(w if i%2==0 else h)) for i,v in enumerate(box)]
    if measured and (measured.get('safe_to_resize') or held_names):
        location={'target_bbox':normalize(measured['target']['bbox']),
                  'anchor_bbox':normalize(measured['anchor']['bbox']),
                  'anchor_standing_upright':True,'target_full_body_visible':True,
                  'same_depth':True,'independent_ground_contact':not measured.get('requires_supported_contact',False),
                  'supported_contact':measured.get('requires_supported_contact',False),'uncertain':False,
                  'anchor_pose':measured.get('anchor_pose','standing_upright'),
                  'evidence':'Object-detector boxes, with pose/depth checks from the saved visual review.'}
        if not location_path.exists():write_json(location_path,location)
    elif location_path.exists():
        location=json.loads(location_path.read_text())
    else:
        # Language-model-only bounding boxes failed calibration. Never use them for a resize.
        return False
    record={'prepared':False,'signature':spec['signature'],'source_attempt':source_attempt,
            'source_sha256':hashlib.sha256(png).hexdigest(),'target':target_id,'anchor':anchor['id']}
    if (location['uncertain'] or not all(location[k] for k in ('anchor_standing_upright','target_full_body_visible','same_depth'))
            or not (location['independent_ground_contact'] or location.get('supported_contact'))):
        record['reason']='Localization does not support an independent ground-level size repair.'
        write_json(record_path,record)
        return False
    try:
        held_boxes=[]
        if held_names:
            prop_path=directory/f'attempt-{attempt:02d}-held-object-localization.json'
            if prop_path.exists():
                prop_record=json.loads(prop_path.read_text())
                if prop_record['source_sha256']!=report['png_sha256'] or prop_record['names']!=held_names:
                    raise ValueError('Saved held-object localization differs from this source.')
                held_boxes=prop_record['boxes']
            else:
                held_boxes,prop_detections=locate_held_objects(png,held_names,
                    [d['bbox'] for cid,d in detections.items() if cid!=target_id])
                write_json(prop_path,{'source_sha256':report['png_sha256'],'names':held_names,
                                     'boxes':held_boxes,'detections':prop_detections})
        pose=next((c.get('pose') for c in report.get('scale_review',{}).get('characters',[]) if c['id']==target_id),None)
        prepared,mask,geometry=prepare_pixels(png,[location['target_bbox'],location['anchor_bbox']],
                                            cast_height(target),cast_height(anchor),checkpoint,
                                            supported_contact=location.get('supported_contact',False),
                                            placement='center' if pose=='jumping' else 'feet',
                                            held_boxes=held_boxes,
                                            thin_tail='mouse' in target['appearance'].lower(),
                                            protected_boxes=[normalize(d['bbox']) for cid,d in detections.items()
                                                             if cid not in (target_id,anchor['id'])])
    except ValueError as exc:
        record['reason']=str(exc);write_json(record_path,record)
        return False
    for label,image in [('image',prepared),('mask',mask)]:
        data=io.BytesIO();image.save(data,format='PNG');data=data.getvalue()
        write_exclusive(directory/f'attempt-{attempt:02d}-repair-{label}.png',data)
        record[label+'_sha256']=hashlib.sha256(data).hexdigest()
    record.update(prepared=True,geometry=geometry)
    write_json(record_path,record)
    logging.info('Book v2: precise scale repair for %s, factor %.3f',target_id,geometry['factor'])
    return True

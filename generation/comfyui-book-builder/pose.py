"""Authored pose diagrams for stubborn scene edits; never observed measurements."""
import hashlib
import io
import json
import logging
import math
import re

from .story import object_schema
from .storage import review_directory, write_exclusive, write_json


def pose_action_failed(audit):
    """Costume and scale failures cannot establish a missing story action."""
    return bool(audit and audit.get('story_event_visible') is False
                and audit.get('uncertain') is False and audit.get('essential_issues'))


def supports_pose_diagram(cast):
    from .detection import detection_phrase
    # This renderer has bipedal joints and only the listed head silhouettes.
    # Other anatomies retain canonical image edits/redraws, not invented limbs.
    supported = {'human', 'person', 'child', 'girl', 'boy', 'woman', 'man',
                 'rabbit', 'fox', 'mouse', 'bear'}
    return all(set(re.findall(r'\w+', detection_phrase(c) or '')) & supported for c in cast)


def layout_schema(ids):
    point = {'type':'array','items':{'type':'number','minimum':0,'maximum':1024},'minItems':2,'maxItems':2}
    color = {'type':'string','pattern':'^#[0-9a-fA-F]{6}$'}
    figure = object_schema({
        'id':{'type':'string','enum':ids},
        'shape':{'type':'string','enum':['human','rabbit','fox','mouse','bear','bird','other']},
        **{key:point for key in ['head','shoulders','hips','left_elbow','left_hand','right_elbow','right_hand',
                                 'left_knee','left_foot','right_knee','right_foot','target']},
        'head_radius':{'type':'number','minimum':16,'maximum':90},
        'pointing_hand':{'type':'string','enum':['left','right','neither']},
        **{key:color for key in ['head_color','body_color','legs_color','foot_color','accent_color']}})
    prop = object_schema({'name':{'type':'string'},'shape':{'type':'string','enum':['ellipse','box']},
        'bounds':{'type':'array','items':{'type':'number','minimum':0,'maximum':1024},'minItems':4,'maxItems':4},
        'color':color})
    return object_schema({'intent':{'type':'string','minLength':1},
        'figures':{'type':'array','items':figure,'minItems':len(ids),'maxItems':len(ids)},
        'props':{'type':'array','items':prop,'maxItems':8}})


def validate_layout(layout, ids):
    import jsonschema
    jsonschema.validate(layout,layout_schema(ids))
    if sorted(f['id'] for f in layout['figures']) != sorted(ids):
        raise ValueError('Pose diagram must contain each expected character exactly once.')
    for f in layout['figures']:
        if f['shape'] == 'other':
            raise ValueError('Unsupported anatomy for a bipedal pose diagram; use a canonical image retry.')
        for side in ('left','right'):
            for a,b in [('shoulders',side+'_elbow'),(side+'_elbow',side+'_hand'),
                        ('hips',side+'_knee'),(side+'_knee',side+'_foot')]:
                if math.dist(f[a],f[b])>min(300,3*f['head_radius']):
                    raise ValueError(f"Implausibly long diagram limb for {f['id']}.")
        for joint in ('elbow','knee','foot'):
            if f['left_'+joint][0]>f['right_'+joint][0]+f['head_radius']*.2:
                raise ValueError(f"Crossed left/right {joint} coordinates for {f['id']}; left means image-left.")
    for p in layout['props']:
        x0,y0,x1,y1=p['bounds']
        if x0>=x1 or y0>=y1:
            raise ValueError('Invalid pose-guide prop bounds.')


def draw_layout(layout):
    from PIL import Image,ImageDraw
    image=Image.new('RGB',(1024,1024),'#fffdf3')
    draw=ImageDraw.Draw(image)
    def ellipse(x,y,rx,ry,color):
        draw.ellipse((x-rx,y-ry,x+rx,y+ry),fill=color)
    def limb(points,color,width):
        draw.line([tuple(p) for p in points],fill=color,width=round(width),joint='curve')
        for x,y in points:ellipse(x,y,width/2,width/2,color)
    for p in layout['props']:
        if p['shape']=='ellipse':draw.ellipse(tuple(p['bounds']),fill=p['color'],outline='#747b80',width=2)
        else:draw.rounded_rectangle(tuple(p['bounds']),radius=8,fill=p['color'])
    for f in sorted(layout['figures'],key=lambda f:max(f['left_foot'][1],f['right_foot'][1])):
        r=f['head_radius'];skin=f['head_color'];body=f['body_color']
        sx,sy=f['shoulders'];hx,hy=f['hips'];x,y=f['head']
        for side,sign in [('left',-1),('right',1)]:
            limb([[hx+sign*r*.4,hy],f[side+'_knee'],f[side+'_foot']],f['legs_color'],r*.5)
            fx,fy=f[side+'_foot'];ellipse(fx,fy,r*.4,r*.2,f['foot_color'])
        draw.polygon([(sx-r*.75,sy),(sx+r*.75,sy),(hx+r*.65,hy),(hx-r*.65,hy)],fill=body)
        for side,sign in [('left',-1),('right',1)]:
            limb([[sx+sign*r*.55,sy],f[side+'_elbow'],f[side+'_hand']],body if f['shape']=='human' else skin,r*.36)
            px,py=f[side+'_hand'];ellipse(px,py,r*.23,r*.23,skin)
            if f['pointing_hand']==side:
                tx,ty=f['target'];distance=math.hypot(tx-px,ty-py)
                if distance>0:
                    length=min(r*.42,distance)
                    limb([[px,py],[px+(tx-px)*length/distance,py+(ty-py)*length/distance]],skin,max(5,r*.13))
        limb([[sx,sy],[x,y+r*.6]],skin,r*.4)
        if f['shape']=='rabbit':
            for dx in (-.45,.45):ellipse(x+r*dx,y-r*1.5,r*.24,r*.95,skin)
        elif f['shape']=='fox':
            for sign in (-1,1):
                draw.polygon([(x+sign*r*.2,y-r*.65),(x+sign*r*.9,y-r*1.65),(x+sign*r*.95,y-r*.35)],fill=skin)
        elif f['shape'] in ('mouse','bear'):
            for dx in (-.75,.75):ellipse(x+r*dx,y-r*.8,r*.45,r*.45,skin)
        ellipse(x,y,r,r,skin)
        if f['shape']=='human':
            draw.arc((x-r,y-r,x+r,y+r),180,355,fill=f['accent_color'],width=max(8,round(r*.2)))
        elif f['shape'] in ('fox','bird'):
            sign=-1 if f['target'][0]<x else 1
            draw.polygon([(x,y+r*.1),(x+sign*r*1.35,y+r*.35),(x,y+r*.65)],fill=f['accent_color'])
        # Omit facial features: the original illustration supplies exact faces.
    return image


def try_pose_guide(project,spec,source_attempt,attempt,report,generate=None):
    """Save a desired-pose plan, or return False so the ordinary retry can proceed."""
    from .quality import json_model,expected_scene
    generate=generate or json_model
    directory=review_directory(project,spec)
    record_path=directory/f'attempt-{attempt:02d}-pose.json'
    image_path=directory/f'attempt-{attempt:02d}-pose.png'
    source=directory/f'attempt-{source_attempt:02d}.png'
    png=source.read_bytes()
    source_hash=hashlib.sha256(png).hexdigest()
    if report.get('signature')!=spec['signature'] or report.get('png_sha256')!=source_hash:
        raise ValueError('Pose correction source does not match its visual review.')
    ids,scene,prose=expected_scene(project,spec)
    cast=[{k:v for k,v in c.items() if k!='personality'} for c in project['book']['characters'] if c['id'] in ids]
    if not supports_pose_diagram(cast):
        write_json(directory/f'attempt-{attempt:02d}-pose-skipped.json', {
            'signature':spec['signature'], 'source_sha256':source_hash,
            'reason':'The diagram renderer cannot represent every character anatomy; continue with a canonical image retry.'})
        return False
    audit = report.get('layout_review')
    if audit is None:
        from .quality import review_scene_event
        path = directory/f'attempt-{attempt:02d}-pose-action-review.json'
        if path.exists():
            saved=json.loads(path.read_text())
            if saved['signature']!=spec['signature'] or saved['source_sha256']!=source_hash:
                raise ValueError('Action review belongs to a different pose correction source.')
            audit=saved['review']
        else:
            audit=review_scene_event(project,spec,png,generate=generate,
                                     prior_issues=report['review'].get('issues',[]))
            write_json(path,{'signature':spec['signature'],'source_sha256':source_hash,'review':audit})
    if not pose_action_failed(audit):
        return False
    if record_path.exists():
        record=json.loads(record_path.read_text())
        if record['signature']!=spec['signature'] or record['source_sha256']!=source_hash:
            raise ValueError('Pose guide belongs to a different candidate.')
        validate_layout(record['layout'],expected_scene(project,spec)[0])
        if not image_path.exists():
            buf=io.BytesIO();draw_layout(record['layout']).save(buf,format='PNG');write_exclusive(image_path,buf.getvalue())
        if hashlib.sha256(image_path.read_bytes()).hexdigest()!=record['image_sha256']:
            raise ValueError('Saved pose guide pixels differ from its plan.')
        return True
    prompt=("Design a rough POSE DIAGRAM for editing this existing illustration. You are AUTHORING desired "
            "coordinates, not measuring the current image. Keep the same cast, physical proportions and scene. "
            "Correct the reported action by making it visually unambiguous. You may reposition the target prop "
            "closer to a hand and bend a torso to make the contact readable, within the story's stated moment. "
            "Every actor must have a clear role; supporting actors can rest their hands while watching. "
            "Return coordinates on a 1024-square canvas: x increases right, y increases DOWN. "
            "head is its centre (excluding ears); shoulders and hips are torso centres. Left/right refer to "
            "the image side of the body. All elbow, hand, knee and foot coordinates are joint centres. "
            "Use connected anatomically plausible limbs. Each upper/lower limb segment must be at most "
            "THREE head radii long, and never over 300 pixels. Keep left elbows, knees and feet to the "
            "image-left of their right counterparts. To reach a low target, bend the torso and knees "
            "or move the object closer; never stretch an arm to bridge the gap. "
            "Keep every body and long ear inside the image. Use a clear composition with separated silhouettes. "
            "For pointing at a ground object, bend the actor toward it, lower the elbow and hand, and place "
            "the fingertip immediately above that actual object; do not leave the arm horizontal. Set target "
            "to the object's centre, and draw that object in props. For a non-pointing actor target is its gaze "
            "target. Keep the other arm in a natural supporting/resting pose. Match canonical clothing/skin/fur "
            "colours as hex values. body_color is the main garment; legs_color is trousers or fur; head_color "
            "is skin/fur; accent_color is hair for humans and muzzle for animals. Props are plain shapes without "
            "faces or lettering, only objects needed to clarify this action. The existing art supplies scenery "
            "and exact facial identity. Do not invent extra actors or events.\nCast: "+json.dumps(cast)+
            "\nRequired scene: "+scene+"\nProse: "+prose+"\nCorrections: "+
            json.dumps(audit.get('retry_instructions',[]))+"\nDesired edit: "+audit.get('retry_scene',''))
    for draft in (1,2):
        try:
            draft_path=directory/f'attempt-{attempt:02d}-pose-draft-{draft}.json'
            if draft_path.exists():
                layout=json.loads(draft_path.read_text())
            else:
                layout=generate(project['config']['ollama_url'],project['render_settings']['review_model'],
                                prompt,layout_schema(ids),[png])
                write_json(draft_path,layout)
            validate_layout(layout,ids)
            image=draw_layout(layout);buf=io.BytesIO();image.save(buf,format='PNG')
            write_json(record_path,{'signature':spec['signature'],'source_attempt':source_attempt,
                'source_sha256':source_hash,'image_sha256':hashlib.sha256(buf.getvalue()).hexdigest(),
                'purpose':'Authored desired pose; not observed geometry or resize measurements.',
                'model':project['render_settings']['review_model'],'prompt':prompt,'layout':layout})
            write_exclusive(image_path,buf.getvalue())
            return True
        except Exception as exc:
            import comfy.model_management as mm
            mm.throw_exception_if_processing_interrupted()
            write_json(directory/f'attempt-{attempt:02d}-pose-error-{draft}.json',{'error':str(exc)})
            prompt+='\nCorrect this invalid diagram: '+str(exc)
            if 'layout' in locals():prompt+='\nPrevious invalid layout: '+json.dumps(layout)
            logging.warning('Book v2: pose guide draft %d failed: %s',draft,exc)
    return False

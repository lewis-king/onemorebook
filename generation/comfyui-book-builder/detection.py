"""Local CPU object detection for measured, independently checked cast geometry."""
import io
import re
from pathlib import Path


def detection_phrase(character):
    phrase=character.get('detection_prompt')
    if phrase:
        return phrase.lower().strip().rstrip('.')+'.'
    appearance=character['appearance'].lower()
    # Legacy plans have no detection hint. Use only a recognisable subject noun.
    kinds=('mouse','badger','fox','rabbit','hare','squirrel','hedgehog','bear','duck','dog','cat',
           'owl','bird','turtle','frog','dragon','robot','elephant','lion','penguin','raccoon','panda','monkey',
           'otter','crab','sloth',
           'girl','boy','child','woman','man')
    found=[(m.start(),word) for word in kinds if (m:=re.search(r'\b'+word+r'\b',appearance))]
    if found:
        return 'a '+min(found)[1]+'.'
    # Older human portraits described age/hair/clothes without an explicit species noun.
    return 'a person.' if re.search(r'\b(human|hair)\b',appearance) else None


def partition_detections(boxes,scores,labels,phrases,image_size):
    """Keep ambiguous class labels attached to real boxes for reference matching."""
    def words(text):
        return set(re.findall(r'\w+',re.sub(r'\b(a|an|the)\b','',text.lower())))
    candidates=[]
    # Detector outputs are not score-sorted. Suppress duplicate proposals only
    # after selecting the strongest box, so an early partial body cannot hide
    # a later, higher-confidence whole-figure detection.
    proposals=sorted(zip(boxes,scores,labels),key=lambda item:item[1],reverse=True)
    for box,score,label in proposals:
        possible=[cid for cid,phrase in phrases.items() if phrase and words(phrase)<=words(label)]
        if not possible:continue
        duplicate=next((c for c in candidates if iou(box,c['bbox'])>.5),None)
        if duplicate:
            duplicate['possible_ids']=sorted(set(duplicate['possible_ids']+possible))
            continue
        candidates.append({'bbox':box,'score':score,'label':label,'possible_ids':possible,'image_size':list(image_size)})
    occurrences={cid:sum(cid in c['possible_ids'] for c in candidates) for cid in phrases}
    known={};unresolved=[]
    for index,candidate in enumerate(candidates):
        ids=candidate['possible_ids']
        if len(ids)==1 and occurrences[ids[0]]==1 and candidate['score']>=.35:
            known[ids[0]]={**candidate,'phrase':phrases[ids[0]]}
        else:
            unresolved.append({**candidate,'box_id':f'box-{index+1}'})
    return known,unresolved


def detect_cast(png,cast,return_candidates=False):
    import folder_paths
    import torch
    from PIL import Image
    from transformers import AutoProcessor,AutoModelForZeroShotObjectDetection
    path=Path(folder_paths.models_dir)/'grounding-dino-tiny'
    if not (path/'model.safetensors').is_file():
        return ({},[]) if return_candidates else {}
    image=Image.open(io.BytesIO(png)).convert('RGB')
    previous=torch.get_num_threads()
    try:
        torch.set_num_threads(min(8,previous))
        processor=AutoProcessor.from_pretrained(path,local_files_only=True)
        model=AutoModelForZeroShotObjectDetection.from_pretrained(path,local_files_only=True).to('cpu').eval()
        phrases={c['id']:detection_phrase(c) for c in cast}
        queries=list(dict.fromkeys(p for p in phrases.values() if p))
        if not queries:
            return ({},[]) if return_candidates else {}
        # Joint labels help the detector distinguish a mouse from a fox; querying
        # "mouse" alone incorrectly labelled the fox in the calibration image.
        inputs=processor(images=image,text=' '.join(queries),return_tensors='pt')
        with torch.inference_mode():
            outputs=model(**inputs)
        # Soft illustrated rabbits scored .28-.34 in measured saved examples.
        # Retain their boxes; low-confidence identities must be established by
        # canonical crop comparison before they can control geometry or repairs.
        detections=processor.post_process_grounded_object_detection(outputs,inputs.input_ids,
            threshold=.25,text_threshold=.20,target_sizes=[image.size[::-1]])[0]
        result,unresolved=partition_detections(detections['boxes'].tolist(),detections['scores'].tolist(),
                                             detections['text_labels'],phrases,image.size)
        return (result,unresolved) if return_candidates else result
    finally:
        torch.set_num_threads(previous)


def iou(a,b):
    intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection
    return intersection/union if union>0 else 0


def relative_size(target,anchor,target_cm,anchor_cm):
    """Only call after pose/depth checks establish comparable full-body heights."""
    observed=(target[3]-target[1])/(anchor[3]-anchor[1])
    intended=target_cm/anchor_cm
    ratio=observed/intended
    return {'observed_ratio':observed,'intended_ratio':intended,'relative_factor':ratio,
            'scale_matches':.65<=ratio<=1.4}


def measure_cast_scale(cast,detections,poses):
    from .scale import cast_height
    result={}
    if not cast or not all(cast_height(c) for c in cast):
        return result
    anchor=max(cast,key=cast_height)
    aid=anchor['id'];ap=poses.get(aid,{})
    comparable=ap.get('pose')=='standing_upright' or (ap.get('pose')=='jumping' and ap.get('body_extended'))
    if aid not in detections or not comparable or not ap.get('full_body_visible'):
        return result
    for character in cast:
        cid=character['id'];pose=poses.get(cid,{})
        kind=pose.get('pose')
        if (cid==aid or cid not in detections or not pose.get('full_body_visible')
                or not pose.get('same_depth_as_largest') or kind in ('unknown','lying',None)):
            continue
        measured=relative_size(detections[cid]['bbox'],detections[aid]['bbox'],cast_height(character),cast_height(anchor))
        upright=kind in ('standing_upright','standing_four_legs') or (kind=='jumping' and pose.get('body_extended'))
        # A compressed pose cannot explain being taller than the standing limit.
        # Conversely, its short bbox cannot certify correct scale or prove undersizing.
        decisive=upright or measured['relative_factor']>1.4
        result[cid]={**measured,'target':detections[cid],'anchor':detections[aid],'anchor_id':aid,'anchor_pose':ap.get('pose'),
                     'safe_to_resize':(bool(pose.get('independent_ground_contact')) or kind=='held')
                         and measured['relative_factor']>1.4,
                     'requires_supported_contact':kind=='held',
                     'measurement_decisive':decisive,'visual_verdict_before_measurement':pose['scale_matches']}
    return result

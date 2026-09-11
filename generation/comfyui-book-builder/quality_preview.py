"""Local, evidence-recording editorial and visual gates. Uncertain reviews fail closed."""
import base64
import io
import json
import re
import urllib.request

from .story import digest, object_schema

QA_VERSION = "1.38-qwen-preview"
STORY_QA_VERSION = "1.9"
DEFAULT_REVIEW_MODEL = "gemma4:31b"
TEXT_CHECKS = ("coherent_arc", "age_appropriate", "read_aloud", "continuity", "distinct_pages",
               "drawable_scenes", "cast_matches_scenes", "unambiguous_character_designs",
               "engaging_hook", "character_agency", "earned_resolution", "concrete_language",
               "distinct_character_designs", "user_constraints")
VISUAL_CHECKS = ("scene_matches", "style_matches", "anatomy_sound", "no_unwanted_text", "reference_background_ok")


def parse_model_json(text):
    """Accept one JSON document, optionally wrapped in one Markdown code fence."""
    text = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced[1]
    # Do not extract a convenient object from commentary or multiple documents.
    # The caller still validates the complete document against its strict schema.
    return json.loads(text)


from .quality import json_model
from .reasoning import story_reasoning_options


def review_schema(checks, extra=None):
    return object_schema({
        "checks": object_schema({key: {"type": "boolean"} for key in checks}),
        "evidence": {"type": "string", "minLength": 1},
        "issues": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "uncertain": {"type": "boolean"},
        **(extra or {}),
    })


def passed(report, expected_ids=None):
    checks = TEXT_CHECKS if expected_ids is None else VISUAL_CHECKS
    if set(report.get("checks", {})) != set(checks) or not all(report["checks"][c] is True for c in checks):
        return False
    if report.get("uncertain") is not False or report.get("issues") != [] or not report.get("evidence"):
        return False
    if expected_ids is not None:
        chars = report.get("characters", [])
        if sorted(c["id"] for c in chars) != sorted(expected_ids):
            return False
        if report.get("unexpected_character_count") != 0:
            return False
        if not all(c["count"] == 1 and c["identity_matches"] is True and c["appearance_matches"] is True
                   and c["scale_matches"] is True and c["evidence"] for c in chars):
            return False
    return True


def review_story(package, config, generate=json_model):
    limit = config.get('max_ensemble_pages', -1)
    ensemble = [p['pageNumber'] for p in package['story']['pages'] if len(p['charactersPresent']) >= 3]
    if limit >= 0 and len(ensemble) > limit:
        return {'qa_version': STORY_QA_VERSION, 'model': config['review_model'], 'package_hash': digest(package),
                'accepted': False, 'stage': 'scene_budget', 'page_audits': [],
                'review': {'checks': {'user_constraints': False}, 'uncertain': False,
                    'evidence': 'Page cast counts checked before the model-based editorial review.',
                    'issues': [f"Pages {ensemble} show three characters together ({len(ensemble)} pages); "
                               f"the requested maximum is {limit}. Preserve the cast and story events, but "
                               "choose one/two-character framing of an actual prose moment for the excess "
                               "group scenes. Update imagePrompt and charactersPresent together."]}}
    if config.get('prose_format') == 'plain-v2' and not config.get('story_override_hash'):
        missing = []
        for page in package['story']['pages']:
            absent = [name for name in page['charactersPresent']
                      if not re.search(r'\b'+re.escape(name)+r'\b', page['imagePrompt'], re.IGNORECASE)]
            if absent:
                missing.append(f"Page {page['pageNumber']}: name the visible actors {absent} explicitly in "
                               "imagePrompt and show their recognisable faces/identifying features. Keep "
                               "the same prose moment; an isolated boot/hand is insufficient for identity review.")
        if missing:
            return {'qa_version': STORY_QA_VERSION, 'model': config['review_model'], 'package_hash': digest(package),
                    'accepted': False, 'stage': 'scene_identity', 'page_audits': [],
                    'review': {'checks': {'drawable_scenes': False}, 'uncertain': False,
                               'evidence': 'Generated scene actor names checked before visual production.', 'issues': missing}}
    prompt = ("""Audit the whole story and private art plan as an independent picture-book editor; do not rewrite it.
Require a hook, clear character want, consequential choices, distinct page events and an earned ending.
Name the action resolving the problem and why the child wants the next page. Accept a compressed arc
for short books. Reject unexplained magic, abstract filler, repeated static scenes and design measurements
in prose. Check age suitability, natural read-aloud language, dialogue punctuation/speech marks, causality,
continuity and all explicit user constraints. Check that chosen methods serve the established goal;
an apparently opposing intermediate objective needs a textual explanation, not an invented justification.

Each imagePrompt must show a real prose moment with the correct visible action, props and state.
charactersPresent describes the CHOSEN FRAME, not every actor mentioned in prose: offscreen participants
are allowed. Listed actors need recognisable faces/features, not isolated boots/hands. Every cast member
needs one unambiguous species, fixed colours/outfit/footwear, distinct visual identity and consistent relative
size. Same-species designs must differ visibly. Check supporting characters as carefully as the lead.
Keep people/clothing out of visual_bible.style and characters out of style_reference_prompt.

Report only substantive defects with page numbers, evidence and specific corrections; do not invent
objections or broaden supplied designs. Mark uncertainty honestly. Explicit user requests override
decorative staging; a requirement that identifying clothes remain worn cannot be waived for a visual joke. """
              + json.dumps(package, ensure_ascii=False))
    report = generate(config["ollama_url"], config["review_model"], prompt, review_schema(TEXT_CHECKS),
                      **story_reasoning_options(config["review_model"]))
    page_audits = []
    pages = package["story"]["pages"]
    page_checks = ("moment_matches", "cast_consistent", "action_and_props_match", "location_and_scale_consistent", "prose_reads_well", "costume_consistent", "persistent_visual_state")
    schema = object_schema({"pages": {"type":"array", "items": object_schema({
        "pageNumber": {"type":"integer"}, "prose_event": {"type":"string"},
        "image_event": {"type":"string"},
        "illustrated_figures": {"type":"array","items":object_schema({
            "description":{"type":"string"},"cast_id":{"type":["string","null"]},"is_character":{"type":"boolean"}})},
        **review_schema(page_checks)["properties"]})}})
    for start in range(0, len(pages), 3):
        batch = pages[start:start+3]
        audit = generate(config["ollama_url"], config["review_model"],
            """For each page, first identify the imagePrompt's chosen frame, visible actors and moment, then compare
that moment with the prose. Check necessary actions, contacts, held objects, positions, location and scale.
Offscreen narrated participants are allowed; not every verb belongs in one image. Visible actors still
must perform the selected event: a carried friend standing separately or a ground target replaced by
another character is a contradiction. Allow established props to remain after use and harmless added
decoration; do not demand identical prose/image prop lists or invent requirements.

List every actual figure in illustrated_figures, with its production cast ID or null. Count humans,
animals and insects even if unnamed. Ordinary objects, hats on acorns, similes and offscreen mentions
are not acting cast; movement or decoration alone does not make an object a character.

Check costume against canonical design AND preceding story changes. A removed scarf cannot still be
worn while used elsewhere. Every prompt starts from clean references, so consequential visible stains,
missing parts, damage and action-critical carried objects must remain explicit until their established
reversal. Apply each change to its named surface; cleaning one ear does not clean the other.
Check natural, engaging read-aloud prose; reject design measurements and abstract filler.
Return one record per supplied page, with evidence and corrections only for real defects. """
            + json.dumps({"cast":package["production"]["characters"],
                          "continuity_context":[{'page':p['pageNumber'],'text':p['text'],'imagePrompt':p['imagePrompt']} for p in pages],
                          "pages_to_audit":batch},ensure_ascii=False), schema)
        expected = [p["pageNumber"] for p in batch]
        if sorted(p["pageNumber"] for p in audit["pages"]) != expected:
            raise ValueError("Editorial reviewer omitted or duplicated a page; nothing was approved.")
        page_audits.extend(audit["pages"])
    for page in page_audits:
        known={c['id']:c['name'] for c in package['production']['characters']}
        expected=next(p['charactersPresent'] for p in pages if p['pageNumber']==page['pageNumber'])
        figures=[f for f in page.get('illustrated_figures',[]) if f.get('is_character',True)]
        unknown=[f['description'] for f in figures if f.get('cast_id') not in known]
        actual=[known[f['cast_id']] for f in figures if f.get('cast_id') in known]
        if unknown or sorted(actual)!=sorted(expected):
            page['checks']['cast_consistent']=False
            page['issues'].append('Illustration cast differs from the registered page cast: '
                                  +json.dumps({'expected':expected,'observed':actual,'unregistered':unknown}))
        if not all(page["checks"].values()) or page["uncertain"] or page["issues"]:
            report["checks"]["drawable_scenes"] = False
            report["issues"].append(f"Page {page['pageNumber']}: " + "; ".join(page["issues"] or [page["evidence"]]))
    continuity_audit = None
    if passed(report):
        # A broad checklist missed an investigator who secretly caused the
        # mystery and reappeared elsewhere without a transition. Trace the
        # ending back through earlier actions before approving production.
        from .continuity import audit_request, apply_audit
        continuity_prompt, continuity_schema = audit_request(package['story'])
        continuity_audit = generate(config['ollama_url'], config['review_model'],
                                    continuity_prompt, continuity_schema,
                                    **story_reasoning_options(config['review_model']))
        apply_audit(report, continuity_audit, package['story'])
    return {"qa_version": STORY_QA_VERSION, "model": config["review_model"], "package_hash": digest(package),
            "accepted": passed(report), "review": report, "page_audits": page_audits,
            "continuity_audit": continuity_audit}


def expected_scene(project, spec):
    book = project["book"]
    if spec['kind'] in ('prop', 'location', 'prop_group'):
        return [], spec['prompt'], ''
    if spec["kind"] == "style":
        return [], book["style_reference_prompt"], ""
    if spec['kind'] == 'state':
        if spec.get('edits'):
            from .state_edit import edit_prompt
            return [spec['character_id']], edit_prompt(spec), ''
        return [spec['character_id']], spec['prompt'], ''
    if spec["kind"] == "character":
        cid = spec["name"].split("/")[1][:-4]
        return [cid], ("One full-body canonical portrait on a plain pale backdrop, with no scene or other figures. "
                       "This is the baseline permanent appearance before story events. Reject temporary stains, "
                       "food, injuries or event props unless explicitly part of the permanent appearance."), ""
    scene = book["cover"] if spec["name"] == "cover.png" else next(p for p in book["pages"] if spec["name"] == f"pages/page-{p['page_number']:03d}.png")
    from .scene_contract import scene_brief
    return scene["character_ids"], scene_brief(project, scene), scene.get("text", "")


def prior_scene_context(project, spec):
    """Earlier prose supplies established facts, not extra actors for this frame."""
    match = re.fullmatch(r'pages/page-(\d+)\.png', spec['name'])
    if not match:
        return []
    number = int(match[1])
    return [{'page': p['page_number'], 'text': p['text']} for p in project['book']['pages']
            if p['page_number'] < number]


def may_recheck_layout(report):
    """Reassess isolated scene objections; eligibility is never an approval.

    Words like 'holding' describe both essential actions and harmless grip
    variations. Only a grounded story/image review can distinguish those cases.
    Identity, anatomy and the other independent gates cannot be cleared here.
    """
    if report['checks'].get('scene_matches') is not False or not report.get('issues'):
        return False
    if any(report['checks'].get(k) is not True for k in VISUAL_CHECKS if k!='scene_matches'):
        return False
    if report.get('unexpected_character_count') != 0 or report.get('uncertain') is not False:
        return False
    if any(c['count']!=1 or not c['identity_matches'] or not c['appearance_matches'] for c in report['characters']):
        return False
    return True


OPTIONAL_STAGING = ('optional_placement', 'optional_framing', 'incidental_gaze',
                    'incidental_expression', 'incidental_grip', 'incidental_pose')


def scene_objections_are_optional(audit, prior_issues):
    """Every original objection needs evidence; actual story requirements veto."""
    classified = audit.get('prior_issues', [])
    def interchangeable_helper(issue):
        return (issue['kind'] == 'interchangeable_helper'
                and issue.get('required_by') in ('illustration_only', 'unsupported_objection')
                and audit.get('same_story_outcome') is True
                and audit.get('character_agency_preserved') is True
                and audit.get('explicit_actor_constraint_preserved') is True
                and bool(audit.get('whole_story_role_evidence', '').strip()))
    return (bool(prior_issues) and audit.get('story_event_visible') is True
            and audit.get('uncertain') is False and audit.get('essential_issues') == []
            and bool(audit.get('observed_event', '').strip())
            and bool(audit.get('required_story_event', '').strip())
            and sorted(i['issue_index'] for i in classified) == list(range(len(prior_issues)))
            and all(((i['kind'] in OPTIONAL_STAGING
                      and i.get('required_by') in ('illustration_only', 'unsupported_objection'))
                     or interchangeable_helper(i))
                    and bool(i.get('evidence', '').strip())
                    and bool(i.get('story_impact', '').strip()) for i in classified))


def enforce_scene_event(report, audit):
    """An independent event failure vetoes a broad pass; it cannot clear other gates."""
    valid = (audit.get('story_event_visible') is True and audit.get('uncertain') is False
             and audit.get('explicit_actor_constraint_preserved') is True
             and audit.get('character_agency_preserved') is True
             and not audit.get('essential_issues'))
    if valid:
        return
    report['checks']['scene_matches'] = False
    report['uncertain'] = report.get('uncertain', False) or audit.get('uncertain', True)
    for issue in audit.get('essential_issues') or ['The required story event or assigned actor could not be verified.']:
        if issue not in report['issues']:
            report['issues'].append(issue)
    report.setdefault('retry_instructions', []).extend(audit.get('retry_instructions', []))
    if audit.get('retry_scene'):
        report['retry_scene'] = audit['retry_scene']


def scene_detail_images(png):
    """Full frame plus four overlapping views; crops add detail, never new evidence."""
    from PIL import Image
    images = [png]
    with Image.open(io.BytesIO(png)) as im:
        w, h = im.size
        for box in ((0, 0, int(.625*w), int(.625*h)),
                    (int(.375*w), 0, w, int(.625*h)),
                    (0, int(.375*h), int(.625*w), h),
                    (int(.375*w), int(.375*h), w, h)):
            data = io.BytesIO()
            im.crop(box).save(data, format='PNG')
            images.append(data.getvalue())
    return images


def review_scene_event(project, spec, png, generate=json_model, prior_issues=()):
    ids, scene, prose = expected_scene(project,spec)
    cast = [{k:v for k,v in c.items() if k!='personality'} for c in project['book']['characters'] if c['id'] in ids]
    observation_schema = object_schema({
        'actors': {'type':'array','items':object_schema({
            'visible_description':{'type':'string'}, 'position':{'type':'string'},
            'torso_axis':{'type':'string','enum':['vertical','horizontal','diagonal','unclear']},
            'torso_front_faces':{'type':'string','enum':['ground','sky','camera_or_side','unclear']},
            'torso_orientation_and_support':{'type':'string'},
            'visible_actions_and_contacts':{'type':'string'}})},
        'object_contacts': {'type':'array', 'maxItems':12, 'items':object_schema({
            'source': {'type':'string'}, 'source_surface': {'type':'string'},
            'target': {'type':'string'}, 'target_surface': {'type':'string'},
            'relation': {'type':'string', 'enum':['touches','inside','separate','occluded','unclear']},
            'visible_evidence': {'type':'string'}})},
        'observed_event':{'type':'string'},
        'uncertain_contacts':{'type':'array','items':{'type':'string'}}})
    observation = generate(project['config']['ollama_url'], project['render_settings']['review_model'],
        """Image 1 is the full artwork. Images 2–5 are overlapping crops of that SAME artwork:
upper-left, upper-right, lower-left, lower-right. They add no actors or objects. Count only the full frame.
Observe without a story. Identify actors by species/features/current clothes, never names.
For each, describe torso orientation, limb positions and the supporting body part/surface BEFORE naming
an action. Report actual holds, gestures and targets; motion lines alone do not establish body posture.
Keep statues/toys separate from living actors.

For object_contacts, focus on conspicuous strands, streams, layers and attachments between objects.
Trace each material bridge to BOTH actual endpoints and describe any boundary it crosses. Distinguish
transparent outer surfaces from opaque contents, and cloth from shiny liquid. Describe physical contact,
not desired adhesion or intended physics. Incidental feet-on-ground contacts belong in actor support,
not this object list. Record uncertainty for obscured endpoints; proximity alone is not attachment.""", observation_schema, scene_detail_images(png))
    contact_schema = object_schema({
        'material_paths': {'type':'array', 'maxItems':5, 'items':{'type':'string','maxLength':400}},
        'uncertainty': {'type':'string','maxLength':400}})
    observation['focused_contact_geometry'] = generate(
        project['config']['ollama_url'], project['render_settings']['review_model'],
        """Image 1 is the full artwork; Images 2–5 are upper-left, upper-right, lower-left and lower-right
overlapping crops of the SAME image, not additional objects. Inspect inanimate-object contacts only.
Distinguish fabric, shiny liquid, transparent outer boundaries and opaque contents. Trace each conspicuous
strand, stream or coating along its visible path and identify the object/surface at BOTH ends. State
whether material visibly joins those surfaces continuously or has a gap; say which contained objects
remain separate from outer coatings. Describe geometry, not intended adhesion, motion or story meaning.
Ignore actor poses. Give up to five concise observed facts; no material bridge means an empty list.
Report obscured/unclear endpoints as uncertainty rather than inventing contact or separation.""",
        contact_schema, scene_detail_images(png))
    schema = object_schema({
        'observed_event': {'type':'string'}, 'required_story_event': {'type':'string'},
        'same_story_outcome': {'type':'boolean'}, 'character_agency_preserved': {'type':'boolean'},
        'explicit_actor_constraint_preserved': {'type':'boolean'}, 'whole_story_role_evidence': {'type':'string'},
        'story_event_visible': {'type':'boolean'}, 'uncertain': {'type':'boolean'},
        'essential_issues': {'type':'array','items':{'type':'string'}},
        'optional_layout_differences': {'type':'array','items':{'type':'string'}},
        'prior_issues': {'type':'array','minItems':len(prior_issues),'maxItems':len(prior_issues),
            'items':object_schema({'issue_index':{'type':'integer','minimum':0},
                'kind':{'type':'string','enum':[*OPTIONAL_STAGING,'interchangeable_helper','essential_action','required_emotion','required_prop_state','identity_or_count','other']},
                'required_by':{'type':'string','enum':['prose','explicit_user','continuity','illustration_only','unsupported_objection']},
                'story_impact':{'type':'string','minLength':1},
                'evidence':{'type':'string','minLength':1}})},
        'retry_scene': {'type':'string'}, 'retry_instructions': {'type':'array','items':{'type':'string'}}})
    prompt = (
        """Compare the independent visual observation with the required page event. First state what is
visible, then what the prose requires. Map species/clothing to the cast without changing the observed
actor to fit the story. Unestablished consequential contacts/actions require uncertainty. This check
covers action, necessary props and persistent states; other gates check identity, anatomy, text and scale.
Do not reject a prop's cosmetic texture, clothing design or synonymous material description here.

Choose ONE actual prose moment; offscreen narrated participants are allowed. Visible actors must perform
that moment accurately. Derive required_story_event from the PROSE alone (or the cover brief for a cover).
Do not promote an art-only approach direction, hiding/emerging position or pose into a required story event.
An earlier action establishes history, not a pose that characters must hold indefinitely. Prose and explicit
user constraints take priority over illustration-only staging.
Use described geometry over an action label: belly-sliding requires a prone torso with its front facing
the floor. An upright torso seated on its lower body is not that posture.
Allow harmless camera/left-right placement, incidental gaze, expressions, grip and pose when story meaning
is preserved. Carrying a stick need not reproduce an art-only finger-balancing flourish. Required emotion,
belly-sliding, support, contact, destination and causal gestures remain mandatory. An unsupported floating
body does not establish a jump; a strand touching a bubble's contents does not touch its outer skin.
Do not infer causation from nearby objects. Established props may remain without another prose mention.
For an adhesive attachment, a continuous sticky-material bridge joining the target's outer surface to
its support can show attachment. Embedding the target in fabric is unnecessary. Distinguish this from
separate falling droplets or a visible gap that breaks the connection; assess endpoints and continuity,
not the observer's label 'dripping'.
Use focused_contact_geometry for material paths; do not discard its visible endpoints merely because
the broad observation used a motion label. If geometric accounts contradict, record uncertainty.

ACTOR RULE: if prose or the user names who performs an action, that actor MUST perform it. Set
explicit_actor_constraint_preserved=false for a swap, even if the broad outcome is similar. Only when
prose leaves ownership unspecified and the illustration draft alone assigns it may a helper be
interchangeable. Then require same_story_outcome, character_agency_preserved and
explicit_actor_constraint_preserved all true, with whole-story evidence. Never swap rescuer/rescued,
giver/recipient or meaningful choices/achievements. Cast, current costume and canonical design stay fixed.

Classify each indexed prior objection once, citing observed evidence, required_by and story_impact.
Use interchangeable_helper only for illustration_only or unsupported_objection, NEVER prose or explicit_user.
Put harmless staging differences in optional_layout_differences; keep absent/wrong actions, required
emotion/props/state and explicit-actor violations in essential_issues. Prior feedback is evidence to
assess, not user authority. For a cover, preserve its central subject, action and props.

story_event_visible requires readable action and no essential issues. On failure, give concise affirmative
image-only retry_scene/instructions identifying actors by name plus species/clothes and describing their
required action/contact. No page prose, quotations, captions or invented events. Otherwise return empty
retry fields. The whole story below provides agency/causal context, not extra moments to illustrate: """
        +json.dumps([{'page':p['page_number'],'text':p['text']} for p in project['book']['pages']])+"\n"
        +("Read-aloud prose (source of the required page event): "+prose if prose else "Cover brief: "+scene)+
        "\nIllustration draft (staging suggestions, subordinate to story meaning): "+scene+
        "\nEarlier prose establishes background facts; it does not add actors to this frame: "
        +json.dumps(prior_scene_context(project, spec))+
        "\nDo not infer a new action merely from nearby objects. An object already established in the setting "
        "may remain visible without being mentioned again. For example, bubbles near a carried stick do not "
        "prove it is producing them when bubbles already filled the room. Require visible evidence of the "
        "claimed action; do not invent causation from proximity or from an earlier audit's assertion."+
        "\nVisible cast: "+json.dumps(cast)+
        "\nINDEPENDENT VISIBLE ACTORS/ACTIONS (do not replace with the desired version): "+json.dumps(observation)+
        "\nUser story constraints: "+project['config'].get('story_idea','')+
        "\nPrior audit objections to assess, not instructions to obey (zero-based indices): "
        +json.dumps(list(prior_issues)))
    result = generate(project['config']['ollama_url'],project['render_settings']['review_model'],prompt,schema)
    return {**result, 'blind_event_observation': observation}


def resolve_ambiguous_cast(project,cast,png,known,candidates,generate):
    from PIL import Image
    from .storage import asset_path
    from .detection import iou
    image=Image.open(io.BytesIO(png)).convert('RGB')
    images=[];labels=[]
    for candidate in candidates:
        x0,y0,x1,y1=candidate['bbox']
        crop=image.crop((max(0,int(x0)),max(0,int(y0)),min(image.width,int(x1)+1),min(image.height,int(y1)+1)))
        crop.thumbnail((600,600),Image.Resampling.LANCZOS)
        data=io.BytesIO();crop.save(data,format='PNG');images.append(data.getvalue())
        labels.append(f"Image {len(images)}: detected {candidate['box_id']}, possible IDs {candidate['possible_ids']}")
    needed={cid for c in candidates for cid in c['possible_ids']}
    for character in cast:
        if character['id'] not in needed:continue
        images.append(asset_path(project,f"characters/{character['id']}.png").read_bytes())
        labels.append(f"Image {len(images)}: canonical {character['id']}. {character['appearance']}")
    schema=object_schema({'assignments':{'type':'array','items':object_schema({
        'box_id':{'type':'string'},'character_id':{'type':['string','null']},
        'certain':{'type':'boolean'},'evidence':{'type':'string'}})}})
    audit=generate(project['config']['ollama_url'],project['render_settings']['review_model'],
        'Identify the dominant figure in each DETECTED CROP by comparing its species, face, colours and clothes '
        'to the labelled canonical portraits. These are already located image crops; do NOT generate coordinates. '
        'Return one assignment per box_id, choosing one of its possible IDs, or null/uncertain if ambiguous. '
        'Do not assign the same character twice or force a match. Ignore small fragments of neighbours at crop edges. '
        +'\n'.join(labels),schema,images)
    result=dict(known)
    assigned=audit['assignments']
    for item in assigned:
        cid=item.get('character_id')
        candidate=next((c for c in candidates if c['box_id']==item['box_id']),None)
        if (not item['certain'] or not item['evidence'] or candidate is None or cid not in candidate['possible_ids']
                or cid in result or sum(a['character_id']==cid for a in assigned)!=1
                or sum(a['box_id']==item['box_id'] for a in assigned)!=1
                or any(iou(candidate['bbox'],d['bbox'])>.5 for d in result.values())):
            continue
        result[cid]={**candidate,'identity_source':'canonical_crop_match','identity_evidence':item['evidence']}
    return result,{'candidates':candidates,**audit}


def review_tail_attachments(project, png, generate=json_model):
    """A separate, narrow check for detached/duplicate tails missed by the broad audit."""
    schema = review_schema(('tails_plausible',), {
        'observed_tails': {'type': 'array', 'items': {'type': 'string'}},
        'retry_instructions': {'type': 'array', 'items': {'type': 'string', 'minLength': 1}}})
    prompt = (
        'Inspect TAILS ONLY in this single candidate illustration. This is a narrow check, not a general '
        'anatomy review: do not assess arms, hands, feet, head size, clothes or story actions. '
        'List each separate visible tail-like shape, with its location, species and visible connection to '
        'the owning body. Two separated visible sections of one naturally occluded or curled tail can be '
        'one tail; do not count them twice if their path through the occlusion is physically plausible. '
        'A detached furry tail held in paws plus another complete tail on the same animal is an extra tail. '
        'A hidden tail is not a defect. Fail only visible extra, detached or impossibly attached tails '
        'relative to the supplied character designs; an explicitly multi-tailed fantasy design is allowed. '
        'Do not invent defects. Record the visible evidence before deciding. If a real tail defect is '
        'visible, give a short precise edit instruction naming the affected character and visible outfit, '
        'and the tail to remove or correct. Preserve all other tails, bodies, poses and scenery. Do not '
        'restate the whole scene or tell the editor only to fix anatomy. Return no correction instructions '
        'when tails are valid.\nCharacter designs: '
        + json.dumps([{k: v for k, v in c.items() if k != 'personality'}
                      for c in project['book']['characters']]))
    return generate(project['config']['ollama_url'], project['render_settings']['review_model'],
                    prompt, schema, [png])


def apply_tail_review(report, tail_review):
    """A layout reassessment cannot erase an independent anatomy rejection."""
    if (tail_review['checks']['tails_plausible'] is not True or tail_review['uncertain']
            or tail_review['issues']):
        report['checks']['anatomy_sound'] = False
        report['uncertain'] = report['uncertain'] or tail_review['uncertain']
        report['issues'].extend(tail_review['issues'] or ['Tail anatomy could not be verified.'])
        specific = tail_review.get('retry_instructions', [])
        report.setdefault('retry_instructions', []).extend(specific or [
            'Preserve each animal\'s canonical tail count and design. Show physically continuous tails '
            'attached to their owning bodies, with the required story action clearly visible.'])


def review_art(project, spec, png, generate=json_model, attempt=None):
    from .storage import asset_path
    if spec['kind'] == 'prop_group':
        from .prop_groups import review_reference
        return {'qa_version': QA_VERSION, 'model': project['render_settings']['review_model'],
                'signature': spec['signature'], **review_reference(project, spec, png, generate)}
    if spec['kind'] in ('prop', 'location', 'prop_group'):
        from .visual_review import review_reference
        return {'qa_version': QA_VERSION, 'model': project['render_settings']['review_model'],
                'signature': spec['signature'], **review_reference(project, spec, png, generate)}
    ids, scene, prose = expected_scene(project, spec)
    # Behavioural notes can contain plot events, not canonical visual features.
    cast = [{k:v for k,v in c.items() if k != "personality"}
            for c in project["book"]["characters"] if c["id"] in ids]
    from .state_ledger import active_changes, state_brief, character_reference
    scene_record = None
    changes = spec.get('changes', []) if spec['kind'] == 'state' else []
    if spec['kind'] == 'scene' and project.get('art_plan'):
        scene_record = project['book']['cover'] if spec['name'] == 'cover.png' else next(
            p for p in project['book']['pages'] if spec['name'] == f"pages/page-{p['page_number']:03d}.png")
        changes = active_changes(project, scene_record)
        scene += state_brief(project, scene_record)
    for character in cast:
        temporary = [c for c in changes if c['character_id'] == character['id']]
        if temporary:
            character['appearance'] += (' CURRENT story-state exceptions to the baseline design: '
                + '; '.join(c['after_state'] + ' on ' + c['surface'] for c in temporary)
                + '. These specific temporary changes are required; every other baseline detail stays fixed.')
    # Establish the actual current-state observations before the broad audit.
    # Previously the broad reviewer invented visible front buttons in a back
    # view, despite the focused audit correctly observing physical occlusion.
    from .state_quality import review_states, apply_state_review
    state_review = review_states(project, spec, png, generate)
    from .clothing import review_removed_clothing
    clothing_review = review_removed_clothing(project, spec, png, generate)
    from .detection import detect_cast, measure_cast_scale
    detections,unresolved = detect_cast(png, cast,return_candidates=True) if len(ids)>1 else ({},[])
    assignment=None
    if unresolved:
        detections,assignment=resolve_ambiguous_cast(project,cast,png,detections,unresolved,generate)
    from .preserved import preserved_boxes
    preserved = preserved_boxes(project,spec,png,attempt)
    for cid,box in preserved.items():
        if cid in ids and cid not in detections:
            detections[cid]=box
    inventory_schema = object_schema({"visible_figures": {"type": "array", "items": {"type": "string"}},
                                      "figure_count": {"type": "integer", "minimum": 0},
                                      "description": {"type": "string"}})
    # First pass is blind to the requested cast, reducing expectation-driven hallucination.
    inventory = generate(project["config"]["ollama_url"], project["render_settings"]["review_model"],
        "Describe ONLY what is actually visible in this image. List every separate human, animal, creature, robot or personified object with a face, including "
        "duplicates, specifying species, clothing/fur, location and size. One entry per individual figure. "
        "figure_count is the total number of these separate characters. Do not count ordinary inanimate props. Do not merge similar-looking figures. "
        "Describe visible shapes and contacts without inventing causation: nearby floating bubbles do not prove a stick is producing them. "
        "Pointed ears AND a bushy tail distinguish a fox from a mouse. Mention blended/hybrid features.",
        inventory_schema, [png])
    count_reconciliation = None
    effective_count = inventory['figure_count']
    if spec['kind'] == 'scene' and effective_count != len(ids):
        from .figure_count import reconcile_scene_count
        count_reconciliation = reconcile_scene_count(project, spec, png, inventory, generate)
        if count_reconciliation['resolved']:
            effective_count = count_reconciliation['figure_count']
    from .state_quality import protected_review_context
    protected_context = protected_review_context(project, spec, png)
    ref_data, labels = [], []
    for c in cast:
        if spec["kind"] != "character" and protected_context is None:
            name = character_reference(project, scene_record, c['id']) if scene_record else f"characters/{c['id']}.png"
            ref_data.append(asset_path(project, name).read_bytes())
            labels.append(f"Image {len(ref_data) + 1}: {'baseline before the required local edit' if spec['kind']=='state' else 'current scene reference'} {c['id']} ({c['name']})")
    if protected_context is not None:
        ref_data.append(protected_context['crop'])
        labels.append('Image 2: enlarged region from candidate Image 1 at the actual edit coordinates. This is the AFTER image, not a baseline or another figure.')
    if spec["kind"] == "character":
        ref_data.append(asset_path(project, "style.png").read_bytes())
        labels.append("Image 2: approved art-style reference ONLY. Ignore its scenery; the portrait needs a plain backdrop.")
    if detections:
        from PIL import Image
        candidate = Image.open(io.BytesIO(png)).convert('RGB')
        for cid, detection in detections.items():
            x0,y0,x1,y1=detection['bbox']
            if max(x1-x0,y1-y0) >= 250:
                continue
            pad=max(8,round(max(x1-x0,y1-y0)*.12))
            crop=candidate.crop((max(0,int(x0)-pad),max(0,int(y0)-pad),
                                 min(candidate.width,int(x1)+pad),min(candidate.height,int(y1)+pad)))
            crop.thumbnail((512,512),Image.Resampling.LANCZOS)
            if max(crop.size)<512:
                ratio=512/max(crop.size)
                crop=crop.resize((round(crop.width*ratio),round(crop.height*ratio)),Image.Resampling.LANCZOS)
            data=io.BytesIO();crop.save(data,format='PNG')
            ref_data.append(data.getvalue())
            labels.append(f"Image {len(ref_data)+1}: enlarged CROP of {cid} from candidate IMAGE 1. "
                          "Use for face/clothing details only, never for scale or counting. This is NOT a reference portrait.")
    character_schema = object_schema({
        "id": {"type": "string"}, "count": {"type": "integer", "minimum": 0},
        "identity_matches": {"type": "boolean"}, "appearance_matches": {"type": "boolean"},
        "scale_matches": {"type": "boolean"}, "evidence": {"type": "string", "minLength": 1}})
    schema = review_schema(VISUAL_CHECKS, {
        "characters": {"type": "array", "items": character_schema},
        "unexpected_character_count": {"type": "integer", "minimum": 0},
        "retry_instructions": {"type":"array","items":{"type":"string","minLength":1}},
        "retry_scene": {"type":"string"}})
    display_cast = cast
    if scene_record:
        from .state_ledger import scene_character_description
        display_cast = [{**c, 'appearance': scene_character_description(project, scene_record, c, current=True)} for c in cast]
    prompt = ("""Audit candidate IMAGE1. Other labelled images are references or candidate detail crops, not extra
figures: count only IMAGE1. Return one record per expected ID, count0 if absent. Check identity and
CURRENT appearance against the correct reference: species, face, body colours, clothes and required
temporary marks. Reject duplicates, missing or merged actors, wrong designs and consequential state errors.

Check the meaningful page action and actual target/contact, not mere coexistence of actor and prop.
Allow harmless pose/expression changes. Assess readable composition, major anatomy faults, lettering and
painted style. scale_matches=true here because a separate measurement gate evaluates physical scale.
For style art require no figures; for portraits require the specified plain backdrop without copied
source scenery. reference_background_ok=true for normal scenes. Mark uncertainty when identity is unclear.

Report concrete failures with the actor and visible evidence. retry_instructions are affirmative desired
corrections, naming actor plus species/current clothes and required action/target. Preserve correct details;
do not describe the bad picture, invent roles or use 'instead of'. Return an empty list when no correction
is needed. If scene_matches=false, also give a self-contained image-edit retry_scene under 200 words:
describe each visible actor's required role and relevant limb-to-object contact. Otherwise leave it empty.
"""
              f"Expected IDs: {ids}.\nCast: {json.dumps(display_cast,ensure_ascii=False)}\n"
              f"Reference image mapping: {labels}\nScene: {scene}\nPage prose: {prose}\n"
              f"Style: {project['book']['visual_bible']['style']}\n"
              f"Independent observed inventory of image 1 (may contain errors; check visually): {json.dumps(inventory)}")
    if spec['kind'] == 'scene':
        prompt += ("""
Scene priorities: exact visible cast/current designs, required props and meaningful prose event.
Prose-specified actors and explicit user constraints are mandatory; the illustration draft's camera,
left/right placement and incidental gaze are flexible only when meaning survives. Preserve action-defining
contact, support and destination. Missing/merged/duplicate actors, disconnected tools, wrong targets and
unsupported floating are real defects. User story constraints: """
                   +project['config'].get('story_idea',''))
        prompt += ("""
Allow art-only grip/pose flourishes to vary: a normally held stick can satisfy carrying it without
finger-balancing; looking up need not require tiptoes. Exact pose, balance, contact, position or emotion
is required when the prose, causality, continuity or user specifies it. Belly-sliding must show the belly
against its support, not sitting between splayed legs. Never broaden identity, state or anatomy to pass.""")
        prompt += ('\nA removed garment held across a belly or chest is not being worn if the neck '
                   'and shoulders are bare. Inspect actual attachment, not proximity to the body. '
                   'An inanimate statue, carved face, portrait or toy remains a prop unless the '
                   'story establishes it as an actual character. Do not count scenery as a duplicate.')
        if count_reconciliation is not None:
            prompt += '\nFocused count evidence (check against Image1): ' + json.dumps(count_reconciliation)
        prompt += ("\nEarlier prose (established background/prop context, not additional cast or moments to put "
                   "in this frame): "+json.dumps(prior_scene_context(project, spec))+
                   """
Established objects may remain visible without another prose mention. Proximity alone does not prove
a new action or cause; verify actual contact and outcome against the image, including claims in the inventory.""")
        if state_review is not None:
            prompt += ("""
Current costume/prop observations below are fallible evidence. Check visible surfaces and attachments
against CURRENT references. Hidden front fastenings are not restored merely because the back is plain;
an actual mark on the wrong surface still fails. Reference-required loose thread is valid. Preserve
independent identity, action, pose and anatomy checks.
"""
                       +json.dumps({'items':state_review.get('items'),
                                    'surface_observations':state_review.get('surface_observations')}))
    if spec['kind'] == 'state' and spec.get('edits'):
        prompt += ("""
For this edited portrait, Scene's final visible material and inventory define CURRENT appearance;
baseline costume describes the earlier state. Preserve intact fastenings. A removed sewn button may leave
cloth and fine thread, not a required hole. Reject a restored button, ambiguous solid dot, invented tear,
unrelated alteration, rectangular patch, smear, broken seam or mismatched texture.""")
    if protected_context is not None:
        prompt += ("""
The baseline is approved and exact RGB comparison confirms preservation outside the edit mask.
Review the changed region fully; no BEFORE image is supplied here. State/material checks remain mandatory.""")
    report = generate(project["config"]["ollama_url"], project["render_settings"]["review_model"],
                      prompt, schema, [png, *ref_data])
    from .appearance_review import recheck, needs_scene_confirmation, confirmed_scene
    appearance_rechecks = []
    if spec['kind'] == 'scene' and effective_count == len(ids):
        appearance_rechecks = recheck(project, spec, png, report, detections, generate)
    layout_review = None
    original_scene_issues = None
    cleared_appearance_only = needs_scene_confirmation(report, appearance_rechecks)
    if spec['kind']=='scene' and effective_count==len(ids) and (may_recheck_layout(report) or cleared_appearance_only):
        original_scene_issues = list(report['issues'])
        layout_review = review_scene_event(project,spec,png,generate=generate,prior_issues=original_scene_issues)
        if (scene_objections_are_optional(layout_review, original_scene_issues)
                or (cleared_appearance_only and confirmed_scene(layout_review))):
            report['checks']['scene_matches'] = True
            report['issues'] = []
            report['evidence'] += '\nFocused layout review: '+layout_review['observed_event']
            report['retry_instructions'] = []
            report['retry_scene'] = ''
    if spec['kind'] == 'scene' and project['render_settings'].get('independent_scene_review', 0) >= 1:
        if layout_review is None:
            layout_review = review_scene_event(project, spec, png, generate=generate)
        enforce_scene_event(report, layout_review)
    if effective_count != len(ids):
        report["issues"].append(f"Independent count found {effective_count} characters; exactly {len(ids)} are required, one per named character.")
        report.setdefault('retry_instructions',[]).append('Show exactly '+str(len(ids))+' figures: '+
            ', '.join(c['name'] for c in cast)+', each appearing once.')
    if count_reconciliation and count_reconciliation['resolved']:
        for cid, count in count_reconciliation['per_character'].items():
            if count != 1:
                report['issues'].append(f"Focused count found {count} instances of {cid}; exactly one is required.")
    scale_report = None
    geometry = {}
    if len(ids) > 1:
        from .scale import height_targets
        # A waist or chin is not a calibrated ruler in a stylized animal design.
        scale_schema = object_schema({
            "characters": {"type": "array", "items": object_schema({"id": {"type": "string"},
                "scale_matches": {"type": "boolean"}, "evidence": {"type": "string"},
                "pose": {"type":"string","enum":["standing_upright","standing_four_legs","sitting","crouching","jumping","lying","held","unknown"]},
                "full_body_visible":{"type":"boolean"},"same_depth_as_largest":{"type":"boolean"},
                "body_extended":{"type":"boolean"},
                "independent_ground_contact":{"type":"boolean"}})},
            "issues": {"type": "array", "items": {"type": "string"}}, "uncertain": {"type": "boolean"}})
        scale_report = generate(project["config"]["ollama_url"], project["render_settings"]["review_model"],
            "Assess physical SCALE only in this single candidate image. Compare each complete silhouette "
            "from the top of its head/ears/mane to its soles against the code-computed standing-height ratios. "
            "Ignore tails, held props and raised hands when judging height. Estimate each smaller figure's "
            "whole-body height as a fraction of the anchor's whole-body height, then compare it to the numeric "
            "target. Do NOT substitute a guessed waist, hip or chin landmark for that ratio: body landmarks "
            "vary in stylized designs. A 60cm character beside a 90cm character should be approximately TWO "
            "THIRDS as tall; requiring it to reach only the waist is an arithmetic error. A 50cm character "
            "beside a 90cm character is about 56 percent as tall. Compare each silhouette's own top-to-bottom "
            "span, not just head y-coordinates when the feet are at different positions. "
            "Use height_cm as the physical size when supplied. Account for sitting/kneeling poses and depth. "
            "Assess each smaller character against the physically tallest anchor independently: do not fail a "
            "correctly sized rabbit merely because a different fox is oversized. "
            "Do not assume all animals should be tiny: follow THIS book's specified proportions. "
            "Do not invent a mismatch or claim equal head sizes when one is visibly smaller. "
            "If a character is literally palm-sized it must fit in a palm; a knee-high character may reach "
            "the knee. Accept ordinary illustration stylization in head proportions and small natural variations. "
            "Never reject solely from a verbal waist/chin/hip claim that contradicts visible numeric proportions. "
            "Mark uncertain when the scene does not provide enough evidence. "
            "Give one record per expected ID, with a concrete observation supporting each verdict.\nCast: "
            + json.dumps(cast) + "\nCode-computed canonical height targets: " + json.dumps(height_targets(cast))
            + "\nScene: " + scene +
            "\nIndependent object-detector measurements in pixels: " + json.dumps(detections) +
            "\nAlso classify each character's pose, whether its whole body is visible, and whether it occupies "
            "roughly the same depth as the physically tallest cast member. independent_ground_contact is true "
            "when the character is freely standing, sitting, crouching or jumping in open space, not held, carrying something, riding, "
            "or intertwined with another figure. body_extended means the torso and at least one leg are extended "
            "so the figure's visible height is comparable to standing, including a stride or straight-legged jump; "
            "false for kneeling, a tucked jump or foreshortening. These pose flags govern whether a physical resize is safe.",
            scale_schema, [png])
        by_id = {c["id"]: c for c in scale_report["characters"]}
        geometry=measure_cast_scale(cast,detections,by_id)
        for cid,measured in geometry.items():
            pose=by_id[cid]
            if measured['measurement_decisive']:
                pose['scale_matches']=measured['scale_matches']
                pose['evidence']=(f"Measured visible height ratio {measured['observed_ratio']:.3f}; "
                    f"cast specifies standing height ratio {measured['intended_ratio']:.3f}, a factor of {measured['relative_factor']:.2f}. "
                    "Figures are at comparable depth; compressed poses cannot justify an oversized visible height.")
        if sorted(c["id"] for c in scale_report["characters"]) != sorted(ids) or scale_report["uncertain"]:
            report["uncertain"] = True
        for character in report["characters"]:
            assessment = by_id.get(character["id"], {})
            if assessment.get("scale_matches") is not True:
                character["scale_matches"] = False
                report["issues"].append(f"{character['id']} scale: {assessment.get('evidence','could not assess')}")
                from .scale import cast_height
                target=next(c for c in cast if c['id']==character['id'])
                if all(cast_height(c) for c in cast):
                    anchor=max(cast,key=cast_height)
                    report.setdefault('retry_instructions',[]).append(
                        f"Preserve {target['name']}'s canonical identity and outfit. When standing, "
                        f"{anchor['name']} is {cast_height(anchor)/cast_height(target):.1f} times as tall as {target['name']}; "
                        "keep those physical proportions through the requested pose.")
        # Character-specific final judgments above include measured evidence where available.
        # Preserve the raw scale issues in scale_review for audit, not as a conflicting second verdict.
    tail_review = None
    if any(re.search(r'\b(tails?|fox|rabbit|mouse|cat|dog|squirrel|raccoon)\b', c['appearance'], re.I) for c in cast):
        tail_review = review_tail_attachments(project, png, generate)
        apply_tail_review(report, tail_review)
    apply_state_review(report, state_review)
    apply_state_review(report, clothing_review)
    from .material import review_removed_fastening, apply_material_review
    material_review = review_removed_fastening(project,spec,png,generate)
    apply_material_review(report,material_review)
    from .scene_details import review_scene_fastening_inventory, apply_scene_fastening_review
    fastening_review = review_scene_fastening_inventory(project,spec,png,generate)
    apply_scene_fastening_review(report,fastening_review)
    from .scene_contract import review_scene_contract
    contract_review = review_scene_contract(project, spec, png, generate)
    apply_state_review(report, contract_review)
    visual_checks = []
    if spec['kind'] == 'scene' and spec.get('visual_references'):
        from .visual_review import review_scene, apply_checks
        visual_checks = review_scene(project, spec, png, generate)
        apply_checks(report, visual_checks)
    from .prop_groups import groups, check as check_object_scale
    object_checks = [check_object_scale(project, g, png, generate) for g in groups(project, spec)] if spec['kind'] == 'scene' else []
    if object_checks:
        from .visual_review import apply_checks
        apply_checks(report, object_checks)
    return {"qa_version": QA_VERSION, "model": project["render_settings"]["review_model"],
            "signature": spec["signature"], "accepted": passed(report, ids), "inventory": inventory,
            "count_reconciliation": count_reconciliation, "appearance_rechecks": appearance_rechecks,
            "scale_review": scale_report, "geometry":geometry, "detections":detections,
            "detection_assignment":assignment,"preserved_geometry":preserved,
            "initial_scene_issues":original_scene_issues,"layout_review":layout_review,
            "protected_state_context": None if protected_context is None else protected_context['proof'],
            "tail_review":tail_review,"state_review":state_review,"clothing_review":clothing_review,"material_review":material_review,
            "scene_fastening_review":fastening_review,"scene_contract_review":contract_review,
            "visual_reference_checks":visual_checks,"object_scale_checks":object_checks,"review": report}

"""Local, evidence-recording editorial and visual gates. Uncertain reviews fail closed."""
import base64
import io
import json
import re
import urllib.request

from .story import digest, object_schema
from .reasoning import story_reasoning_options

QA_VERSION = "1.41"
STORY_QA_VERSION = "1.10"
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


def json_model(url, model, prompt, schema, images=(), seed=0, num_ctx=16384, think=False, num_predict=4096, sampling=None):
    """Share the GPU cooperatively with ComfyUI; unload the reviewer on every exit."""
    import comfy.model_management as mm
    import jsonschema
    import time
    import hashlib
    from .review_session import current
    session=current.get()
    if session is not None:session['models'].add((url,model))
    started=time.monotonic()
    mm.throw_exception_if_processing_interrupted()
    mm.unload_all_models()
    mm.soft_empty_cache()
    message={'role':'user','content':prompt+'\nReturn JSON matching this schema:\n'+json.dumps(schema)}
    payload = {"model": model, "messages": [message], "format": schema, "stream": True,
               "think": think, "keep_alive": '5m' if session is not None else 0,
               "options": {"temperature": 0, "seed": seed % (2 ** 31), "num_ctx": num_ctx, "num_predict": num_predict, **(sampling or {})}}
    if images:
        message["images"] = [base64.b64encode(data).decode() for data in images]
    def request(data):
        return urllib.request.Request(url.rstrip("/") + ('/api/chat' if 'messages' in data else '/api/generate'), json.dumps(data).encode(),
                                      {"Content-Type": "application/json"})
    parts, complete = [], False
    try:
        with urllib.request.urlopen(request(payload), timeout=300) as response:
            for line in response:
                mm.throw_exception_if_processing_interrupted()
                if not line.strip():
                    continue
                part = json.loads(line)
                if part.get("error"):
                    raise RuntimeError(part["error"])
                parts.append(part.get("message", {}).get("content", ""))
                if sum(map(len, parts)) > 100_000:
                    raise ValueError("Review exceeded the response limit.")
                if part.get("done"):
                    complete = part.get("done_reason") != "length"
        if not complete:
            raise RuntimeError("Reviewer did not finish. No artwork has been approved.")
        result = parse_model_json("".join(parts))
        jsonschema.validate(result, schema)
        if session is not None:
            from .storage import write_json
            identity={'model':model,'prompt':prompt,'schema':schema,'seed':seed,'think':think,
                      'images':[hashlib.sha256(data).hexdigest() for data in images],
                      'options':payload['options']}
            key=digest(identity)
            directory=session['directory']/'model-calls'
            write_json(directory/(key+'-request.json'),identity)
            # Store the first exact response without conflicting timing writes
            # if the same review is requested twice within this asset phase.
            path=directory/(key+'-result.json')
            if not path.exists():write_json(path,{'result':result,'seconds':time.monotonic()-started,
                'load_duration':part.get('load_duration'),'eval_duration':part.get('eval_duration')})
        return result
    finally:
        if session is None:
            try:
                urllib.request.urlopen(request({"model": model, "keep_alive": 0}), timeout=15).close()
            except OSError:
                pass


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
    prompt = ("You are an independent children's picture-book editor. Audit the ENTIRE supplied story and private art plan. "
              "Do not rewrite it. Reject concrete defects; do not invent objections just to be critical. "
              "Check the beginning/problem/actions/earned ending, natural readable prose, age suitability, "
              "normal dialogue punctuation including quotation marks around direct speech in ordinary prose, "
              "cause and effect and continuity, distinct page events, illustration prompts matching the text "
              "and exact visible cast. charactersPresent specifies the figures INSIDE THE CHOSEN FRAME, not "
              "everyone mentioned in the paragraph. A close-up of two friends peeking through leaves is valid "
              "when the prose says all three friends hid behind the bush: the third friend may be offscreen. "
              "This is not a missing actor or a continuity gap. Count illustration limits from the visible "
              "frame, never from names mentioned in prose. Essential actions/states of actors IN the frame "
              "must still be correct. Every character needs one unambiguous species, stable colours/outfit/footwear "
              "and a recognisable depiction: a listed visible character needs its face and identifying features, "
              "not just an isolated boot or hand. Reframe the same prose moment if necessary. Check "
              "and relative size. 'Barefoot OR shoes', shifting fur colour, or mouse-sized/child-sized ambiguity "
              "is a defect. Check supporting characters just as strictly as the lead. "
              "Every cast member must have a distinct visual identity; two same-species characters need "
              "clear fixed differences in silhouette, colour or clothing, not just personality or names. "
              "Only visual technique and palette belong in visual_bible.style, not people or clothing. "
              "style_reference_prompt must be empty of characters. "
              "Evaluate storytelling, not only correctness. Require a hook, an identifiable character want, "
              "choices/actions that change the situation, and an earned ending. Generic warm sentiments or "
              "a magic fix without an established rule are not enough. Reject filler metaphors children "
              "cannot understand, repeated static scenes, and design specifications inserted into prose. "
              "For a two-page test, allow a compressed arc but still require a meaningful event/payoff. "
              "In your evidence name the actual action that solves the problem and why a child wants the next page. "
              "Give page numbers and concrete evidence for failures. Mark uncertain when unsure. "
              "user_constraints requires the explicit user premise to be obeyed. If the user says identifying clothes "
              "remain worn, even a funny gust blowing off the identifying scarf violates that requirement. "
              f"Target ages: {config['age_range']}. User premise: {config['story_idea']}.\n"
              + json.dumps(package, ensure_ascii=False))
    reasoning = story_reasoning_options(config['review_model'])
    report = generate(config["ollama_url"], config["review_model"], prompt, review_schema(TEXT_CHECKS), **reasoning)
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
            "Compare prose and imagePrompt on each supplied page independently. FIRST identify the chosen "
            "framing, visible actors and moment from imagePrompt. THEN locate that actual moment in the prose "
            "and compare its necessary action, positions, held objects and location. charactersPresent lists "
            "the figures inside this chosen frame. Other characters mentioned in prose may be offscreen, "
            "even when they are part of a group event. For example, prose saying three friends hide behind "
            "a bush can have a close-up of just two of them peeking through the leaves. Do not reject that "
            "as a missing actor. A close-up of an embarrassed culprit may omit the speaking detective, "
            "provided the culprit's visible action/state and necessary clues are correct. Do not require "
            "every narrated actor or verb to appear in one picture. This does NOT excuse contradictions "
            "in the visible actors' actions: two friends standing in the open do not depict those friends "
            "hiding; a carried friend standing separately does not depict being carried. A mouse on a palm "
            "in prose versus on grass in the "
            "image prompt is a failure. A character waving or holding a ribbon in prose versus just facing "
            "forward in the prompt is a failure. 'Smaller than a shoe' versus 'larger than a shoe' is a failure. "
            "The illustration may depict one moment from a sequence, but must not contradict that moment. "
            "An object established on earlier pages may remain visible without being mentioned in this page's prose. "
            "A tool may remain in someone's hand after its use. Harmless additional visual details are allowed: "
            "only reject actual contradictions, missing essential actions, or inconsistent actors/locations. "
            "Do not require the picture and prose to list identical props, and do not demand details the prose never specifies. "
            "List EVERY concrete figure depicted in imagePrompt in illustrated_figures, including unnamed insects, "
            "animals or people interacting with the cast. Assign its production cast ID, or null if it has none. "
            "A beetle wearing a hat is an additional character even if unnamed; ordinary acorns wearing hats without "
            "faces are props. Set is_character=false for ordinary objects: rolling/bouncing or decorative hats "
            "alone do not make an acorn or ball a character. Set it true for all humans, animals and insects. "
            "Do not count similes or figures merely mentioned offscreen. "
            "costume_consistent checks the immutable appearance against this page and preceding story actions. "
            "If a canonical scarf was removed to line a wagon, requiring it still around the neck is contradictory. "
            "Moving props are allowed, but fixed identity clothing cannot be both worn and used elsewhere. "
            "persistent_visual_state checks visible changes established earlier: jam-stained ears, wet or muddy "
            "clothes, a broken prop, or a carried object needed by the action. Every illustration starts from CLEAN "
            "canonical portraits, so each imagePrompt must explicitly carry forward any still-visible marks or damage "
            "until the story establishes their removal. A rabbit's ears dipped in jam on page 6 need jam mentioned "
            "in later prompts showing those ears, even when the later prose need not repeat it. Omitting a visible "
            "persistent mark is a concrete continuity failure. Cleaning one ear does not clean the other. "
            "Check engaging, natural read-aloud prose for "
            f"ages {config['age_range']}; reject numeric design measurements and empty abstract filler. "
            "Return exactly one record for every page supplied, identifying concrete corrections.\n"
            + json.dumps({"cast":package["production"]["characters"],
                          "continuity_context":[{'page':p['pageNumber'],'text':p['text'],'imagePrompt':p['imagePrompt']} for p in pages],
                          "pages_to_audit":batch},ensure_ascii=False), schema, **reasoning)
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
                                    continuity_prompt, continuity_schema, **reasoning)
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
    return scene["character_ids"], scene_brief(project, scene, normalize_staging=True), scene.get("text", "")


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


def review_scene_event(project, spec, png, generate=json_model, prior_issues=()):
    ids, scene, prose = expected_scene(project,spec)
    cast = [{k:v for k,v in c.items() if k!='personality'} for c in project['book']['characters'] if c['id'] in ids]
    observation_schema = object_schema({
        'actors': {'type':'array','items':object_schema({
            'visible_description':{'type':'string'}, 'position':{'type':'string'},
            'visible_actions_and_contacts':{'type':'string'}})},
        'observed_event':{'type':'string'},
        'uncertain_contacts':{'type':'array','items':{'type':'string'}}})
    observation = generate(project['config']['ollama_url'], project['render_settings']['review_model'],
        'Describe the actual visible actors and actions in this picture. You have no story or intended '
        'outcome. Identify each actor by species/appearance and current clothing, NEVER invent personal '
        'names. Say what each hand, paw or flipper visibly holds, touches, tips, pushes or pulls, and '
        'the target/result of that contact. A nearby hand is not necessarily gripping an object. '
        'If ownership is obscured, record that uncertainty instead of inferring who ought to act. '
        'Keep statues, toys and scenery separate from living actors. Describe the actual objects and '
        'actions, without inventing causation from proximity or a story you imagine.', observation_schema, [png])
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
        "Check whether a child can follow this page's STORY EVENT from the independent visual observation below. "
        "This is a semantic comparison: the observer saw the picture WITHOUT its story, desired action or names. "
        "Use the observer's species/clothing descriptions to map actors to the supplied cast; do not rewrite "
        "the observed actor to make it match the prose. The penguin and monkey are different actors even "
        "when their personal names are arbitrary. If observations cannot establish a consequential action, "
        "mark uncertainty. First describe the observed event faithfully, then the required event. "
        "Identity, anatomy, lettering and physical "
        "scale are checked separately. This pass checks action, necessary props and persistent visible states. "
        "An illustration can depict ONE moment in the prose rather than every action simultaneously. "
        "Only the listed actors must be in frame; others mentioned in prose can be outside this chosen shot. "
        "The art draft is a suggested staging, not a requirement to reproduce each camera angle, left/right "
        "placement or incidental gaze. Put harmless changes in optional_layout_differences, NEVER in "
        "essential_issues. Derive required_story_event from the read-aloud prose and explicit USER "
        "constraints. An earlier audit's preferred gaze or placement is not itself a story requirement. "
        "If the prose describes a conversation, participants may look at each other. If the prose "
        "describes inspecting something, their attention to that object matters. Explicit USER "
        "positioning requests remain mandatory. A facial expression suggested only by the art draft can "
        "vary when it fits the actual prose event. Classify that as incidental_expression. Emotions "
        "established in the prose or explicitly requested by the USER are essential: a smiling proud "
        "character does not depict a character described as crying or frightened. Such contradictions "
        "are required_emotion issues and must fail. Do not confuse this check with a permission to change "
        "the story's emotional meaning. "
        "Likewise, incidental grip and pose details in the illustration draft are flexible when the actual "
        "story action remains clear. If prose says a monkey arrives carrying a bamboo stick to help reach a bowl, "
        "holding the stick normally is sufficient even if the art draft asks for balancing it on one finger. "
        "The finger trick is incidental_grip, not an essential action. If prose says a panda looks up and gasps, "
        "an art draft's added tiptoes are incidental_pose; standing normally can tell that same event. "
        "Do not infer that sitting prevents looking up. BUT when the prose or an explicit user request makes "
        "balancing on one finger the trick that solves the problem, or stretching on tiptoes the action being "
        "told, the exact action matters. A grip that disconnects a tool from its user or prevents the narrated "
        "contact/pulling/carrying is also essential. The question is whether the child sees the same meaningful "
        "event, not whether every generated art-direction detail was obeyed. "
        "Reject a materially different or absent action: pointing at a friend rather than the named stones, "
        "standing on grass instead of pressing a boot onto the tub rim, a rope disconnected from the load, "
        "or a required held friend standing separately. Required props and established stains/damage cannot "
        "disappear. For a cover without prose, require "
        "its described central subject/action and props while allowing harmless composition choices. "
        "story_event_visible is true when the meaningful event is readable and essential_issues is empty. "
        "If false, give a short affirmative image-only retry_scene and specific retry_instructions. Never "
        "put page prose, quotations or captions in image editing instructions. Otherwise return empty retry fields.\n"
        "Inspect each prior audit objection, classify it and justify the classification using the observation and "
        "prose. Set required_by to the actual source: prose, explicit_user, continuity, illustration_only, "
        "or unsupported_objection. Explain story_impact: what story meaning would be lost, or why none is lost. "
        "An art draft and previous reviewer feedback are NOT explicit user requirements. Do not dismiss a "
        "real action/prop/identity problem as cosmetic.\n"
        "Actor ownership follows the read-aloud prose. If the prose names who performs an action, "
        "that named character must visibly perform it; a matching overall outcome cannot excuse "
        "swapping actors. If prose says Momo pours honey, Pip pouring fails even if both are helping. "
        "Only when the prose is agnostic about ownership may a helper assignment added solely by "
        "the illustration brief vary. Classify that as interchangeable_helper with required_by="
        "illustration_only. A prose-based actor objection is essential_action, never optional. "
        "Explicit user actor requirements, character agency, recipient, destination and contacts "
        "remain mandatory. Do not infer the right actor or outcome from nearby objects. "
        "same_story_outcome, character_agency_preserved and explicit_actor_constraint_preserved "
        "must all hold; explain the actual role evidence. Identity, count, costume and design remain fixed.\n"
        "Whole read-aloud story for role salience (not extra moments to draw): "
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
    prompt = ("Audit IMAGE 1, the candidate illustration. Other images are labelled identity/style references or enlarged candidate crops, NOT extra figures "
              "to count. Count figures ONLY in image 1. Compare each expected character to its reference and "
              "immutable description. Reject absent/duplicate characters, wrong species, mixed identities, "
              "wrong outfit/fur, or a scene that fails to depict the requested action. "
              "Distinguish explicitly requested temporary marks from identity changes: red jam ON a cream rabbit's "
              "ears is correct when this scene requires jam, while unexplained red fur is wrong. Check those "
              "requested marks and prop states as part of scene_matches, including whether they are missing. "
              "Check the target of a pointing gesture: a rabbit pointing sideways at a child's face does not "
              "depict pointing down at stones on the ground. Do not infer the requested action merely because "
              "both the actor and object exist in the picture. "
              "Accept reasonable pose/expression changes. Relative physical scale is assessed in a separate "
              "measurement step: set scale_matches=true here and concentrate on identity, appearance and action. "
              "Check expressive readable composition, major anatomy faults, no lettering, and requested illustration style. "
              "For style and portrait references reference_background_ok requires NO copied garden/porch/scene "
              "behind a portrait; style art must have NO figures. For normal scenes this check is true. "
              "Do not invent missing figures. Mark uncertain if identity cannot be assessed. "
              "Give exactly one character record per expected ID, with count=0 if missing. "
              "Every issue must be a concrete sentence identifying the character and correction, not a generic issue code. "
              "Also give retry_instructions as affirmative commands describing the DESIRED corrected picture, "
              "without describing the bad picture, negatives or 'instead of'. For example: 'Pip extends one paw "
              "diagonally down toward the stones on the ground.' Preserve the requested cast, identities, poses "
              "and scene; correct only actual defects. Identify the actor by name AND visible appearance "
              "(for example, Pip the cream rabbit in the blue waistcoat). Specify the desired gaze, limb "
              "direction and target when relevant; clarify other actors' roles if needed to avoid swapping actions. "
              "Return an empty array if there are none. If scene_matches is false, also write retry_scene: "
              "a concise, self-contained image EDIT instruction describing the complete desired action. "
              "Describe EVERY visible actor by appearance, its desired pose, what its hands/paws are doing, "
              "and its gaze target. Explicitly connect the active limb to the target object and its location. "
              "Other actors need their own clear supporting roles, so the editor cannot swap the action. "
              "For instance, a downward pointing gesture requires a lowered arm and gaze toward the ground; "
              "a listening child can rest both hands on her knees. Use only roles supported by this page, "
              "preserving correct details and props, not inventing a new story. Write the desired picture "
              "affirmatively, without recounting mistakes or using 'instead of'. Keep this under 200 words. "
              "Return an empty retry_scene when the scene is correct. "
              f"Expected IDs: {ids}.\nCast: {json.dumps(display_cast,ensure_ascii=False)}\n"
              f"Reference image mapping: {labels}\nScene: {scene}\nPage prose: {prose}\n"
              f"Style: {project['book']['visual_bible']['style']}\n"
              f"Independent observed inventory of image 1 (may contain errors; check visually): {json.dumps(inventory)}")
    if spec['kind'] == 'scene':
        prompt += ("\nScene validation priorities: preserve the exact visible cast, canonical identities/outfits, "
                   "required props and the meaningful story event. Image-prompt left/right placement, camera "
                   "angle and incidental gaze are staging suggestions when changing them leaves the story "
                   "equally readable. Do not reject ONLY for these harmless differences. For example, friends "
                   "discussing an idea beside a tub may stand on either side and look at each other. "
                   "Spatial relations remain mandatory when they determine the ACTION: holding a friend in "
                   "one's arms, pointing at the named ground object, boot-to-rim contact, or pulling a load "
                   "toward the required destination. A disconnected rope, wrong pointing target, missing actor, "
                   "merged bodies or duplicated character is NOT a harmless layout variation. Explicit user "
                   "positioning requests also remain mandatory. Do not broaden any character's design. "
                   "Judge the original prose event, not a convenient substitute.\nUser story constraints: "
                   +project['config'].get('story_idea',''))
        prompt += ("\nSeparate necessary story actions from incidental art direction. Carrying a bamboo stick "
                   "does not require balancing it on one finger merely because the illustration draft adds that "
                   "flourish. A natural full-hand grip is valid. Looking up does not require standing on tiptoes "
                   "unless the prose makes that action meaningful. Harmless grip, posture or pose variations "
                   "must not create a scene failure or retry instruction. Exact limb contact, balance, position "
                   "or emotion IS required when it conveys a narrated action, causal mechanism, established "
                   "continuity or explicit user requirement. Keep those meaningful distinctions and all cast, "
                   "identity, clothing, anatomy and physical-scale checks. The generated illustration draft "
                   "is not itself a set of explicit user requirements.")
        prompt += ('\nA removed garment held across a belly or chest is not being worn if the neck '
                   'and shoulders are bare. Inspect actual attachment, not proximity to the body. '
                   'An inanimate statue, carved face, portrait or toy remains a prop unless the '
                   'story establishes it as an actual character. Do not count scenery as a duplicate.')
        if count_reconciliation is not None:
            prompt += '\nFocused count evidence (check against Image1): ' + json.dumps(count_reconciliation)
        prompt += ("\nEarlier prose (established background/prop context, not additional cast or moments to put "
                   "in this frame): "+json.dumps(prior_scene_context(project, spec))+
                   "\nObjects already established in the setting may remain visible without being mentioned "
                   "again. Do not infer a new action or cause simply because objects are nearby. In particular, "
                   "bubbles already floating in a room do not prove a carried stick is blowing bubbles. Inspect "
                   "the visible evidence rather than accepting causal guesses in the blind inventory.")
        if state_review is not None:
            prompt += ('\nSeparately observed costume/prop evidence for THIS candidate and the approved '
                       'CURRENT references follows. Inspect it alongside the image; observations may be '
                       'fallible, but do not invent a visible fastening behind an occluded front surface. '
                       'A back/side view with a plain back does not prove restored front buttons. '
                       'Only visible contradicting details can establish such a mismatch. An incorrect '
                       'mark on the back still fails. Fine loose threads explicitly present on the '
                       'current reference are its required appearance, not an invented decoration. '
                       'Pose, readable action, identity and anatomy still need independent scrutiny.\n'
                       +json.dumps({'items':state_review.get('items'),
                                    'surface_observations':state_review.get('surface_observations')}))
    if spec['kind'] == 'state' and spec.get('edits'):
        prompt += ('\nThis is an edited reference portrait. The final visible region and final inventory in '
                   'Scene are the precise CURRENT appearance requirements. The original baseline costume '
                   'description describes its earlier state. A removed sewn button can leave continuous '
                   'cloth and fine loose thread; it does not require a tear or opening through the cloth. '
                   'Inspect the actual AFTER detail and the remaining intact fastenings. Reject a restored '
                   'selected button, solid ambiguous dot, invented hole, or unrelated change. Check the edit '
                   'for an obvious rectangular patch, blurred smear, broken seam or incompatible texture. '
                   'Fine loose stitches explicitly specified by the final region are permitted.')
    if protected_context is not None:
        prompt += ('\nThe baseline portrait has a saved valid approval. An exact RGB comparison confirms '
                   'every pixel outside the measured edit mask is unchanged. This establishes preservation '
                   'there; the edited region still needs full appearance, anatomy and style scrutiny. '
                   'No BEFORE portrait is supplied in this audit to avoid confusing its previous costume '
                   'with the required final appearance. The independent state and material checks remain mandatory.')
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

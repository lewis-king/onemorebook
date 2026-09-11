"""Private visual-state intervals. Never change the public story or baseline canon."""
import json
import re

STATE_VERSION = 1
STATE_REVIEW_VERSION = 5


class StatePlanningError(ValueError):
    """Bounded semantic planning failed; generated prose can return to its writer."""


def obj(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


def request(story, characters, *, constrain_evidence=False):
    text={'type':'string','minLength':1}
    identifier={'type':'string','pattern':'^[a-z][a-z0-9_]{0,31}$'}
    page={'type':'integer','enum':[p['pageNumber'] for p in story['pages']]}
    evidence={'type':'array','minItems':1,'items':obj({'pageNumber':page,'quote':text})}
    if constrain_evidence:
        # Generation selects exact prose and its matching page together. The
        # wider validator still reads historical short, verbatim quotations.
        # A quote can support no more than its actual meaning; the independent
        # semantic review still rejects invented changes and wrong intervals.
        evidence['items']={'anyOf':[
            obj({'pageNumber':{'type':'integer','enum':[p['pageNumber']]},
                 'quote':{'type':'string','enum':[p['text']]}})
            for p in story['pages']]}
    schema=obj({
        'changes':{'type':'array','maxItems':12,'items':obj({
            'id':identifier,'character_id':{'type':'string','enum':[c['id'] for c in characters]},
            'part':text,'surface':text,'before_state':text,'after_state':text,
            'from_page':page,'through_page':page,
            'active_pages':{'type':'array','minItems':1,'uniqueItems':True,'items':page},
            'operation':{'type':'string','enum':['modify_existing','add_clothing']},
            'onset':{'type':'string','enum':['before_opening','on_page','between_pages']},
            'evidence':evidence,
            'reference_edit':obj({'target_query':text,
                'selection':{'type':'string','enum':['single','topmost','bottommost','leftmost','rightmost','all']},
                'instruction':text}),
        })},
        'detached_props':{'type':'array','maxItems':12,'items':obj({
            'id':identifier,'source_change_id':identifier,'description':text,
            'visible_pages':{'type':'array','items':page,'uniqueItems':True},'evidence':evidence,
        })},
        'uncertain':{'type':'boolean'},'issues':{'type':'array','items':text},
    })
    prompt='''Compile a PRIVATE visual-state ledger for this already-written picture book.
Do not rewrite its prose, image prompts, cast or public schema. The normal character portraits
show their clean baseline design. Record ONLY consequential changes to a character's visible
appearance or identifying clothes: a lost fastening, removed hat, stain, tear or other physical
change that must persist across pictures. Ordinary poses, expressions, movements, lighting,
temporary carried objects and unchanged clothes are NOT state changes. An unchanged story
requires empty changes and detached_props arrays, not an invented alteration.

Read the entire prose before choosing effective intervals. A later reveal can establish that
a change happened BEFORE page 1; it must then apply from page 1, not only from its discovery.
Keep it through the final page unless the prose explicitly repairs/reverses it. If a page shows
the reversal, use that page's chosen illustration moment to determine the boundary. Include
exact short quotations from the prose as evidence. Never invent a repair, second accident,
garment modification or return trip to make an interval convenient. Mark uncertain when an
important interval cannot be determined. Do not demand an alteration on an offscreen character;
the program applies intervals only to pages where that character is depicted.

Trace EVERY putting-on, taking-off, draping, restoring and wearing-again event in order.
active_pages lists exactly the pages where this appearance is in force, including offscreen
pages. from_page/through_page are its first/last active pages. A scarf worn on pages 2-3,
removed and hung on a peg on pages 4-5, then worn again on page 6 has active_pages
[2,3,6], NOT every page 2-6. Reuse ONE change ID for the same returning appearance.
Do not keep an item worn merely because it remains present elsewhere in the picture.
Record the removed garment as a detached_prop on its visible detached pages, linked to
the change that established its worn design. Cite both removal and return evidence.

operation=add_clothing means a NEW worn garment/accessory over an otherwise unchanged
baseline body/outfit. It uses a separately reviewed whole-reference clothing edit: an absent
cape cannot be detected on the unclothed portrait. operation=modify_existing covers removals,
stains, tears, lost fastenings and changes to existing clothes; these KEEP protected local edits.
Never classify removal/replacement of an existing identifying item as add_clothing.

For each change, identify its physical PART and SURFACE. Front-centre coat buttons stay on
the front-centre chest, never on the back panel when a figure turns. Ear-tip jam stays on those
ears, not on a tail. Use the normal anatomical/garment surface and explain it explicitly.
Describe the before and after states. If the prose does not choose between otherwise identical
fastenings, select one deterministic position for visual continuity (such as the topmost front
button); this is art direction, not a new event. Do not invent how many fastenings the reference
has: refer to the selected one and preserve all others. A changed detail need not be forced into
view when that physical surface is hidden by the camera or another object.

A stain must be grounded in the prose at its actual body location and onset. Handling paint
with one finger does not establish paint over the belly, face or entire body. Do not spread a
contact mark to unmentioned surfaces or backdate a later illustration flourish. A transient
hand-to-object contact belongs in that scene's action; record a persistent mark only when
the prose establishes that appearance change. Illustration-only decorative marks are not
prose events and do not create a persistent interval. Copy baseline anatomy and colours
from the canonical character description; do not invent body-part colours for an edit.

The reference_edit gives a SHORT concrete object-detector query for the EXISTING item/part
on the baseline portrait, a deterministic selection, and a precise local-edit instruction. The
instruction changes that part only and preserves every other feature. Do not ask to redraw
the whole character, change pose, add a scene, labels or an alternate character design.
Examples: query 'a blue button.', selection topmost, replace that upper FRONT button with
blue fabric and a tiny loose blue thread; query 'a red hat.', selection single, show the same
head after the hat is removed. Do not use pixel coordinates; the reference will be measured.

Only list detached_props when the story actually reuses a removed costume item as a visible
object, so it should match its origin (a lost button, for example). Link it to its source change.
visible_pages are pages whose chosen imagePrompt shows that item, not pages where it is
merely mentioned, hidden in a pocket or still attached. Use the image prompt for visibility,
but PROSE evidence for events. No detached props for stains or normal unaltered garments.
Keep fields concise. Return no issues and uncertain=false for a clear ledger, including a
clear no-change story. This is state compilation, not a demand for photographic realism.
'''
    if constrain_evidence:
        prompt += ('\nFor each evidence entry select its pageNumber and EXACT COMPLETE page prose '
                   'from the schema choices. Copy the page text verbatim; the imagePrompt is NOT '
                   'event evidence. An illustration-only mark or incidental detail does not '
                   'establish a persistent change in the story. Do not invent such a change. '
                   'Selecting a true quotation is insufficient unless it supports the claimed event.\n')
    return prompt+'\n'+json.dumps({
        'prose_evidence_pages':[{'pageNumber':p['pageNumber'],'text':p['text']} for p in story['pages']],
        'illustration_visibility_only':[{'pageNumber':p['pageNumber'],'imagePrompt':p['imagePrompt'],
            'charactersPresent':p['charactersPresent']} for p in story['pages']],
        'canonical_characters':characters},ensure_ascii=False),schema


def validate(ledger, story, characters):
    import jsonschema
    import copy
    compatible = copy.deepcopy(ledger)
    # Read historical continuous intervals without modifying their saved bytes.
    for change in compatible.get('changes', []):
        change.setdefault('active_pages', list(range(change['from_page'],change['through_page']+1)))
        change.setdefault('operation','modify_existing')
    try:
        jsonschema.validate(compatible, request(story, characters)[1])
    except jsonschema.ValidationError as exc:
        raise ValueError('Invalid visual-state ledger: '+exc.message) from exc
    pages={p['pageNumber']:p for p in story['pages']}
    cast={c['id'] for c in characters}
    changes={}
    for change in ledger['changes']:
        cid=change['id']
        if cid in changes or not re.fullmatch('[a-z][a-z0-9_]{0,31}',cid):
            raise ValueError('Duplicate or unsafe state identifier.')
        if change['character_id'] not in cast:raise ValueError('Unknown state character.')
        start,end=change['from_page'],change['through_page']
        if start not in pages or end not in pages or start>end:raise ValueError('Invalid state interval.')
        active = change.get('active_pages',list(range(start,end+1)))
        if not active or min(active)!=start or max(active)!=end or set(active)-pages.keys():
            raise ValueError('Active state pages must match the interval endpoints and existing pages.')
        if change['onset']=='before_opening' and start!=min(pages):
            raise ValueError('A pre-opening state must apply from the first page.')
        changes[cid]=change
    prop_ids=set()
    for prop in ledger['detached_props']:
        if prop['id'] in prop_ids or prop['source_change_id'] not in changes:
            raise ValueError('Duplicate prop or missing origin change.')
        prop_ids.add(prop['id'])
        if len(set(prop['visible_pages']))!=len(prop['visible_pages']) or set(prop['visible_pages'])-pages.keys():
            raise ValueError('Invalid prop page coverage.')
    for item in [*ledger['changes'],*ledger['detached_props']]:
        if not item['evidence']:raise ValueError('State evidence is missing.')
        for fact in item['evidence']:
            if fact['pageNumber'] not in pages or fact['quote'] not in pages[fact['pageNumber']]['text']:
                page_text=pages.get(fact['pageNumber'],{}).get('text','')
                image_text=pages.get(fact['pageNumber'],{}).get('imagePrompt','')
                source=(' The supplied quote comes from the illustration prompt, not the prose.'
                        if fact['quote'] and fact['quote'] in image_text else '')
                raise ValueError(f"State evidence for {item['id']} on page {fact['pageNumber']} is not "
                                 f"an exact quotation from the cited prose.{source} "
                                 f"Supplied quote: {fact['quote']!r}. Available prose: {page_text!r}. "
                                 'Remove any unsupported change; do not invent new prose or events.')
    if ledger['uncertain'] or ledger['issues']:
        raise ValueError('Visual state requires clarification: '+json.dumps(ledger['issues']))
    return ledger


def active_on(change, page):
    return page in change.get('active_pages',range(change['from_page'],change['through_page']+1))


def is_addition(change):
    return change.get('operation') == 'add_clothing'


def requirements(ledger, story, characters):
    """Propagate approved intervals; the model cannot omit a later visible page."""
    validate(ledger,story,characters)
    names={c['name']:c['id'] for c in characters}
    result={}
    for page in story['pages']:
        n=page['pageNumber'];visible={names[name] for name in page['charactersPresent']}
        result[n]={'changes':[c['id'] for c in ledger['changes']
                              if c['character_id'] in visible and active_on(c,n)],
                   'props':[p['id'] for p in ledger['detached_props'] if n in p['visible_pages']]}
    return result


def review_request(story, cast, ledger):
    schema = obj({'costume_timeline':{'type':'array','items':obj({
                      'pageNumber':{'type':'integer'},'item':{'type':'string'},
                      'state':{'type':'string'},'prose_evidence':{'type':'string'}})},
                  'body_or_clothing_changes':{'type':'array','items':{'type':'string'}},
                  'ordinary_object_events':{'type':'array','items':{'type':'string'}},
                  'valid':{'type':'boolean'},'issues':{'type':'array','items':{'type':'string'}},
                  'evidence':{'type':'string'}})
    prompt = '''Independently check this PRIVATE COSTUME/BODY-APPEARANCE ledger against the entire prose.
First separate what physically changes on a character's body/clothing from ordinary actions
with objects. List actual body_or_clothing_changes and ordinary_object_events separately.
This separation determines the audit's scope, not whether a prop matters to the story.

FIRST independently build costume_timeline from the prose, including each acquisition,
putting-on, taking-off, draping elsewhere and wearing-again event. Cite exact prose evidence.
THEN compare each change's active_pages with that timeline. Being visible as an object is
different from being worn. A cape left on a jar is no longer on its wearer; if worn again later,
the intervening pages must remain inactive. Check add_clothing applies only to a new worn
item, never removal or modification of an existing canonical garment. Detached added clothes
must reference the change that established their design. Do not overlook removal just because
the item remains important. Ordinary separately carried objects are still out of scope.

For EVERY proposed stain/body alteration, check that the prose supports the specific
changed physical surface as well as the starting page. Touching paint with a finger does NOT
support paint streaks on a belly or a whole-body stain. Do not spread contact to unmentioned
surfaces or infer an unseen accident. Later art direction cannot backdate a stain into earlier
pages. An illustration-only decorative mark is not a persistent prose-established state.
Check every baseline colour/anatomy assertion against the canonical design as well.
Report unsupported alterations PRESENT IN THE LEDGER explicitly, naming their change ID;
require their removal FROM THE LEDGER. Accept a ledger that correctly omits unsupported or
illustration-only marks. Do not reject that correct omission because an illustration prompt
contains the mark: you are auditing the ledger, not rewriting the approved story or art brief.
A decorative mark in one illustration does not require a persistent alteration in this ledger.

IN SCOPE: a fastening removed from a garment, a worn hat taken off, a stain on fur, a tear,
or their restoration. Such a change modifies the clean baseline portrait and persists until
the prose reverses it. Check ownership, effective start/end, physical surface, missing or
invented changes, and exact supporting evidence. Read later confessions/reveals. Do not
invent a second accident, repair or return trip to resolve uncertain consequential timing.

OUT OF SCOPE: picking up, carrying, retrieving, setting down, borrowing or handing over an
ordinary object. Acquiring a kite, carrying a basket, or holding a book does not change the
character's baseline body or clothes, even if they keep that object until the final page.
Ordinary poses, facial expressions and lighting are also not costume/body changes. These
events belong in the page prose and illustration prompts; do not require them in this ledger.

detached_props means ONLY an item physically removed by one of the ledger's body/clothing
changes, with a source_change_id linking it to that removal (for example a lost coat button).
It is NOT a general prop inventory. A standalone object is not a detached costume part merely
because someone picks it up or it becomes important. If the story only moves ordinary objects
and all bodies/outfits remain unchanged, an empty changes/detached_props ledger is correct.

For genuine changes, merely finding a loose object is insufficient evidence of its owner;
the whole story must establish the connection. An inferred pre-opening event needs causal
evidence. A deterministic choice between identical buttons is allowed art direction. Hidden
body surfaces need not display their changes. Detached costume-prop visibility follows the
chosen image frame, not every prose mention. Reject uncertain consequential timing without
rewriting the prose. Return valid=true with no issues when this scoped ledger is complete.
'''
    return prompt+'\n'+json.dumps({
        'prose_evidence_pages':[{'pageNumber':p['pageNumber'],'text':p['text']} for p in story['pages']],
        'illustration_visibility_only':[{'pageNumber':p['pageNumber'],'imagePrompt':p['imagePrompt'],
            'charactersPresent':p['charactersPresent']} for p in story['pages']],
        'cast':cast,'ledger':ledger},ensure_ascii=False),schema


def compile_plan(project, model, generate=None):
    """Save each attempt before review and reuse only the exact approved plan."""
    from pathlib import Path
    from .quality import json_model
    from .storage import write_json
    from .story import digest
    import jsonschema
    generate = generate or json_model
    story, cast = project['story'], project['book']['characters']
    prompt, schema = request(story, cast, constrain_evidence=True)
    key = digest([STATE_VERSION, STATE_REVIEW_VERSION, story, cast, model, prompt, schema])
    root = Path(project['book_root']) / 'visual-state' / key[:16]
    root.mkdir(parents=True, exist_ok=True)
    feedback = ''
    for attempt in range(1, 4):
        path = root / f'attempt-{attempt:02d}.json'
        if path.exists():
            ledger = json.loads(path.read_text())
        else:
            ledger = generate(project['config']['ollama_url'], model,
                              prompt + feedback, schema, seed=attempt - 1)
            write_json(path, ledger)
        review_path = root / f'attempt-{attempt:02d}-review.json'
        if review_path.exists():
            review = json.loads(review_path.read_text())
        else:
            try:
                validate(ledger, story, cast)
            except (ValueError, jsonschema.ValidationError) as exc:
                review = {'valid': False, 'issues': [str(exc)]}
            else:
                review_prompt, review_schema = review_request(story,cast,ledger)
                review = generate(project['config']['ollama_url'], model,
                                  review_prompt, review_schema)
            write_json(review_path, review)
        if review.get('valid') is True and review.get('issues') == []:
            validate(ledger, story, cast)
            result = {'version': STATE_VERSION, 'review_version': STATE_REVIEW_VERSION, 'source_hash': key, 'ledger': ledger,
                      'pages': requirements(ledger, story, cast), 'review': review}
            # A cover may depict a different moment from the opening page. Ask
            # explicitly only if one of its characters changes during the story.
            cover_ids = set(project['book']['cover']['character_ids'])
            changing = any(c['character_id'] in cover_ids for c in ledger['changes']) or bool(ledger['detached_props'])
            cover_path = root / 'cover-moment.json'
            if changing:
                cover_schema = obj({'pageNumber': {'type': 'integer', 'enum': [p['pageNumber'] for p in story['pages']]},
                                    'prop_ids': {'type': 'array', 'uniqueItems': True,
                                                 'items': {'type': 'string', 'enum': [p['id'] for p in ledger['detached_props']] or ['none']},
                                                 'maxItems': len(ledger['detached_props'])},
                                    'evidence': {'type': 'string'}, 'uncertain': {'type': 'boolean'}})
                cover = json.loads(cover_path.read_text()) if cover_path.exists() else generate(
                    project['config']['ollama_url'], model,
                    'Choose the story moment whose costume/appearance state should apply to the cover. '
                    'Match the existing cover prompt, without rewriting it or inventing an event. '
                    'List ONLY detached-prop IDs that the cover prompt actually depicts. Empty when none. '
                    'Explain the choice; mark uncertain if the cover demands incompatible states.\n'
                    + json.dumps({'story': story, 'ledger': ledger}, ensure_ascii=False), cover_schema)
                write_json(cover_path, cover)
                if cover['uncertain']:
                    raise StatePlanningError('The cover visual state is ambiguous: ' + cover['evidence'])
            else:
                cover = {'pageNumber': story['pages'][0]['pageNumber'], 'prop_ids': [], 'evidence': 'Cover characters have no changed appearance.', 'uncertain': False}
            n = cover['pageNumber']
            result['cover_moment'] = cover
            result['cover'] = {'changes': [c['id'] for c in ledger['changes'] if c['character_id'] in cover_ids
                                           and active_on(c,n)], 'props': cover['prop_ids']}
            write_json(root / 'approved.json', result)
            return result
        feedback = ('\nCorrect this previous ledger, retaining the original story: ' + json.dumps(ledger)
                    + '\nReview: ' + json.dumps(review))
    raise StatePlanningError('Visual-state planning failed after three saved attempts. '
                             'Resolve the consequential ambiguity in the story or its illustration prompts; '
                             'do not invent an off-page event to justify it. Last review: '
                             + json.dumps(review, ensure_ascii=False) + '. Saved attempts: ' + str(root))


def scene_requirements(project, scene):
    plan = project.get('art_plan')
    if not plan:
        return {'changes': [], 'props': []}
    if 'page_number' not in scene:
        return plan['cover']
    return plan['pages'].get(str(scene['page_number']), plan['pages'].get(scene['page_number']))


def active_changes(project, scene, cid=None):
    wanted = scene_requirements(project, scene)['changes']
    return [c for c in project.get('art_plan', {}).get('ledger', {}).get('changes', [])
            if c['id'] in wanted and (cid is None or c['character_id'] == cid)]


def inactive_additions(project, scene):
    """Visible actors must stop wearing an addition outside its approved moments.

    Derive this from the ledger, including covers and interrupted wear intervals;
    never insert production requirements into the public story or change a ledger.
    """
    active = {c['id'] for c in active_changes(project, scene)}
    visible = set(scene['character_ids'])
    return [c for c in project.get('art_plan', {}).get('ledger', {}).get('changes', [])
            if is_addition(c) and c['character_id'] in visible and c['id'] not in active]


def variant_name(cid, changes):
    from .story import digest
    return f"states/{cid}-{digest(sorted(c['id'] for c in changes))[:12]}.png"


def character_reference(project, scene, cid):
    changes = active_changes(project, scene, cid)
    return variant_name(cid, changes) if changes else f'characters/{cid}.png'


def scene_character_description(project, scene, character, *, current=False):
    """Describe the current portrait without reintroducing altered baseline clothes."""
    changes = active_changes(project, scene, character['id'])
    if ((not current and project.get('render_settings', {}).get('state_scene_policy', 0) < 5)
            or not any(not is_addition(change) for change in changes)):
        return character['appearance']
    descriptions = ['Match the approved current reference: its face, species, body colours, '
                    'anatomy and currently worn clothes.']
    for change in changes:
        edit = project.get('state_edits', {}).get(change['id'])
        if edit:
            descriptions.append(f"Visible {change['surface']}: {edit['plan']['desired_region']}")
            # Individual edit inventories may describe other simultaneously
            # changed parts in their earlier state. The combined portrait wins.
            if len(changes) == 1:
                descriptions.append('Current clothing: ' + edit['plan']['inventory_after'])
        else:
            descriptions.append(f"Current {change['surface']}: {change['after_state']}.")
    return ' '.join(descriptions)


def restored_surface_brief(project, scene, change):
    """Describe the visible result, without repeating the unwanted wearing state."""
    actor = next(c for c in project['book']['characters'] if c['id'] == change['character_id'])
    current = active_changes(project, scene, actor['id'])
    if current:
        # An old bare-surface description must not erase another active garment.
        return (f"{actor['name']}'s current appearance: "
                + '; '.join(c['after_state'] + ' on ' + c['surface'] for c in current)
                + '. Its other visible surfaces follow the approved current character reference.')
    return f"{actor['name']}'s visible {change['part']} show {change['before_state']}, matching the approved character reference."


def state_brief(project, scene):
    brief = _active_state_brief(project, scene)
    if project.get('render_settings', {}).get('state_scene_policy', 0) < 3:
        return brief
    absent = inactive_additions(project, scene)
    if not absent:
        return brief
    if project['render_settings']['state_scene_policy'] >= 4:
        return (brief + '\nRequired visible character appearance:\n'
                + '\n'.join(dict.fromkeys(restored_surface_brief(project,scene,c) for c in absent))
                + '\nDetached items occupy their stated prop locations as separate physical objects.')
    names = {c['id']: c['name'] for c in project['book']['characters']}
    return brief + ('\nClothing removed or not yet introduced at this moment:\n'
        + '\n'.join(f"{names[c['character_id']]}: the temporary state '{c['after_state']}' is inactive. "
                    f"Follow the current character reference on {c['surface']}; this added garment is not worn."
                    for c in absent)
        + '\nPreserve all active clothing changes and baseline design. A detached garment belongs only '
          'at its specified prop location, with one physical copy, not also on its former wearer.')


def _active_state_brief(project, scene):
    changes = active_changes(project, scene)
    if not changes:
        return ''
    names = {c['id']: c['name'] for c in project['book']['characters']}
    if project.get('render_settings',{}).get('state_scene_policy',0) >= 1:
        descriptions=[]
        for change in changes:
            edit=project.get('state_edits',{}).get(change['id'])
            description=f"{names[change['character_id']]} — physical surface: {change['surface']}. "
            if edit:
                plan=edit['plan']
                description += (f"Current visible material: {plan['desired_region']} "
                                f"Current inventory: {plan['inventory_after']}")
                # The edit recipe freezes a portrait's pose/background while
                # changing one surface. Scene poses come from the story.
                # Retain policy 1 verbatim for saved prompt/signature recovery.
                if project['render_settings']['state_scene_policy'] == 1:
                    description += f" Preserve: {plan['preserved_features']}"
            else:
                description += change['after_state']
            descriptions.append(description)
        return ('\nCurrent appearance in this story moment:\n'+'\n'.join(descriptions)
                +'\nUse the approved CURRENT character reference for these details. '
                 'They belong only on the named physical surface. Depict them when that surface '
                 'is visible; a back view shows the plain back of the garment. Keep the same '
                 'physical arrangement through changes in pose and camera angle.')
    return ('\nStory state for this moment (a temporary change to the same baseline character):\n'
            + '\n'.join(f"{names[c['character_id']]}: {c['after_state']} on {c['surface']} ({c['part']}). "
                        f"Reference edit: {c['reference_edit']['instruction']}." for c in changes)
            + '\nPreserve all other design details. Show a changed detail only when its physical surface '
              'faces the camera and is unobscured; hidden front fastenings do not appear on a back panel. '
              'A hidden detail is not permission to restore it when it becomes visible again.')


def variant_specs(project):
    variants = {}
    for scene in [project['book']['cover'], *project['book']['pages']]:
        for cid in scene['character_ids']:
            changes = active_changes(project, scene, cid)
            if not changes:
                continue
            name = variant_name(cid, changes)
            variants[name] = {'name': name, 'kind': 'state', 'character_id': cid,
                'changes': changes, 'references': [f'characters/{cid}.png'],
                'prompt': 'Edit only the measured regions of this SAME character portrait. '
                          + ' '.join(c['reference_edit']['instruction'] + '.' for c in changes)
                          + ' Preserve every other feature, face, outfit detail, body proportions, pose, '
                            'art style and background exactly. One character, one view, no new labels.'}
            if any(is_addition(c) for c in changes):
                if not all(is_addition(c) for c in changes):
                    raise ValueError('A combined clothing addition and protected alteration needs a staged reference edit.')
                variants[name]['edit_mode'] = 'clothing_addition'
                variants[name]['prompt'] = ('Edit Image 1, the approved portrait of this SAME character. '
                    + ' '.join(c['reference_edit']['instruction']+'.' for c in changes)
                    + ' Add only the stated garment. Keep the face, species, fur, quills, existing clothes, '
                      'body proportions, pose, painted texture and pale background. One full-body character, '
                      'one view, no labels. The new clothing may cover the body where naturally worn.')
            if project.get('state_edits'):
                variants[name]['edits'] = [project['state_edits'][c['id']] for c in changes
                                           if c['id'] in project['state_edits']]
            if project.get('render_settings', {}).get('positive_flux_prompts'):
                variants[name]['prompt'] = ('Edit Image 1, the approved character portrait. '
                    + ' '.join(c['reference_edit']['instruction'].rstrip('.')+'.' for c in changes)
                    + ' Preserve the face, body proportions, pose, remaining outfit, painted style and '
                      'pale background. One full-body character in one view, with unmarked artwork surfaces.')
    return list(variants.values())

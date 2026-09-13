"""Private, human-reviewed production plan. Never changes the public story."""
import json
from .story import object_schema as obj, validate_package
from .assisted_references import MAX_REFERENCE_IMAGES, scene_reference_count
from .assisted_prompt_context import SCENE_GUIDANCE
from . import assisted_prop_states as prop_states

TEXT = {'type': 'string', 'minLength': 1, 'maxLength': 3000}
ID = {'type': 'string', 'pattern': '^[a-z][a-z0-9_]{0,31}$'}
IDS = {'type': 'array', 'items': ID, 'uniqueItems': True}


def schema(book, moment_ids=None):
    asset=obj({'id':ID,'kind':{'enum':['prop','location','character_state','prop_state']
                               +(['moment'] if moment_ids else [])},
               'name':TEXT,'appearance':TEXT,'source_character':{'type':'string'}})
    asset['required'].remove('source_character')
    # Optional for old saved plans; mandatory only for the new derived-prop kind.
    asset['properties'].update(source_assets={**IDS,'minItems':1,'maxItems':MAX_REFERENCE_IMAGES},
                               visible_pages={'type':'array','items':{'type':'integer','minimum':0},
                                              'minItems':1,'uniqueItems':True})
    constraints=[{'if':{'properties':{'kind':{'const':'prop_state'}}},
                  'then':{'required':['source_assets','visible_pages']}},
                 {'if':{'properties':{'kind':{'const':'character_state'}}},
                  'then':{'required':['source_character']}}]
    if moment_ids:
        # Moment references are the reader's own photographs, restyled by the
        # creator; the planner may only cite the ones that were uploaded.
        constraints.append({'if':{'properties':{'kind':{'const':'moment'}}},
                            'then':{'properties':{'id':{'enum':list(moment_ids)}}}})
    asset['allOf']=constraints
    return obj({
        'assets': {'type': 'array', 'maxItems': 24, 'items':asset},
        'scenes': {'type': 'array', 'minItems': len(book['pages'])+1, 'maxItems': len(book['pages'])+1,
                   'items': obj({'page': {'type': 'integer', 'minimum': 0},
                                 'moment': TEXT, 'character_refs': IDS, 'asset_refs': IDS})},
        'continuity_notes': TEXT,
    })


def request(package, config=None):
    from .story import make_render_plan
    book = make_render_plan(package['story'], package['production'])
    prompt = '''Plan illustrations for this approved children's book. Return the private JSON plan.
The story and canonical characters are fixed. A human will review this plan before any images.
assets: first scan the pages in order for every salient object that is built, broken, opened, filled,
repaired, decorated, stacked or otherwise changes and is shown again later. Give each persistent form
its own prop_state reference, including the incomplete/broken form where it first appears and the
completed/repaired form after the change. If a needed component is not already an asset, add a prop
for it before the state. Describe permanent shape, material, colours and size relative to a character.
Keep movable props and characters out of location reference designs. A prop reference depicts ONE
object; a prop_state depicts an assembly or changed object as one unit. If a character's outfit or
physical state changes, add a character_state reference with source_character set to its canonical ID
and appearance describing the complete current design. Other kinds may omit source_character.
Use unique IDs distinct from canonical character IDs. Avoid decorative reference proliferation.
scenes: page 0 is the cover, followed by every numbered page in order. Each moment is a concise
positive visual description of ONE instant that directly illustrates the page's prose. Preserve
the named actor, action, target and essential outcome. Use Name (species and distinguishing clothing)
when first naming each actor. One instance of each required character; identify the whole cast once.
Preserve recurring object designs and where a trapped object remains until freed.
Do not illustrate multiple sequential events at once or turn metaphors into extra objects.
Use natural prose, approximately 50–100 words per scene, not JSON/image-model instructions,
negative lists, measurements, labels or quoted story dialogue. The cover moment may describe the
title's visual treatment, but the exact title instruction is added by the renderer.
character_refs lists only visible canonical character IDs, substituting a character_state ID when
that change is active. It must match the approved page's charactersPresent exactly.
asset_refs lists relevant prop/location IDs, with at most ONE location. FLUX.2.dev has a budget of
SIX input reference images in total. Visible characters occupy ONE shared cast image, leaving
FIVE prop/place images. A scene without characters can use SIX prop/place images. Each reference
must be meaningful to that instant. A scene that introduces a persistent object state must use that
state reference immediately, and every later scene that shows the same state must use the same
reference; never reconstruct it from a different form or from loose components. Each prop/location
is a separate input. Reference numbering is added
by code; do not write Image N yourself. continuity_notes briefly explains object/state progression.
'''
    prompt += prop_states.GUIDANCE + SCENE_GUIDANCE
    if config and config.get('story_craft_version'):
        from .story_craft import ILLUSTRATION_GUIDANCE
        prompt += ILLUSTRATION_GUIDANCE
    if config and config.get('moment'):
        from .assisted_moment import plan_guidance
        prompt += plan_guidance(config['moment'])
    prompt += '\nBook package:\n'+json.dumps(package, ensure_ascii=False)
    moment_ids=[p['id'] for p in config['moment']['photos']] if config and config.get('moment') else None
    return prompt, schema(book, moment_ids)


def validate(package, plan, moment_ids=None):
    import jsonschema
    from .story import make_render_plan
    book = make_render_plan(package['story'], package['production'])
    jsonschema.validate(plan, schema(book, moment_ids))
    chars = {c['id']: c for c in book['characters']}
    assets = {a['id']: a for a in plan['assets']}
    if len(assets) != len(plan['assets']) or set(chars) & set(assets):
        raise ValueError('Reference IDs must be unique and distinct from the characters.')
    prop_states.ordered_assets(plan['assets'],len(book['pages']))
    for asset in assets.values():
        if asset['kind'] == 'character_state':
            if asset.get('source_character') not in chars:
                raise ValueError('A character state must identify its canonical character.')
        elif asset.get('source_character'):
            raise ValueError('Props and places cannot be character variants.')
    expected = [book['cover']] + book['pages']
    if [s['page'] for s in plan['scenes']] != list(range(len(expected))):
        raise ValueError('Plan scenes must be cover 0 followed by every page in order.')
    for scene, original in zip(plan['scenes'], expected):
        identities = []
        for ref in scene['character_refs']:
            if ref in chars:
                identities.append(ref)
            elif ref in assets and assets[ref]['kind'] == 'character_state':
                identities.append(assets[ref]['source_character'])
            else:
                raise ValueError(f'Unknown character reference {ref}.')
        if len(set(identities)) != len(identities) or set(identities) != set(original['character_ids']):
            raise ValueError(f"Page {scene['page']}: the planned cast must match the approved story exactly.")
        refs = scene['asset_refs']
        invalid = [r for r in refs if r not in assets or assets[r]['kind'] == 'character_state']
        if invalid:
            raise ValueError(f"Page {scene['page']}: unknown prop/place references: {', '.join(invalid)}.")
        count = scene_reference_count(scene['character_refs'], refs)
        if count > MAX_REFERENCE_IMAGES:
            cast = int(bool(scene['character_refs']))
            raise ValueError(f"Page {scene['page']}: this scene needs {count} reference images "
                             f"({cast} shared character image + {len(refs)} prop/place images). "
                             f"FLUX.2.dev's recommended budget is {MAX_REFERENCE_IMAGES} total; "
                             "reduce this scene's references.")
        if sum(assets[r]['kind'] == 'location' for r in refs) > 1:
            raise ValueError('A scene must choose one location reference.')
        prop_states.validate_scene(scene,assets)
    if moment_ids:
        # The book exists to keep the real day, one page per photograph in the
        # order the day happened: every numbered page recreates exactly one
        # moment, each moment exactly one page, moments never on the cover.
        order = {mid: i for i, mid in enumerate(moment_ids)}
        cited = {}
        for scene in plan['scenes']:
            moments_here = [r for r in scene['asset_refs']
                            if r in assets and assets[r]['kind'] == 'moment']
            if scene['page'] == 0 and moments_here:
                raise ValueError('The cover is illustrated from the story. Keep the reader\'s '
                                 'photographs on the numbered pages: ' + ', '.join(moments_here) + '.')
            if len(moments_here) > 1:
                raise ValueError(f'Page {scene["page"]}: give this page one moment only '
                                 f'({", ".join(moments_here)}). Each memory deserves its own page.')
            if scene['page'] > 0 and not moments_here:
                raise ValueError(f'Page {scene["page"]} has no photograph. This book has one page per '
                                 'photograph; give every page its moment from the day.')
            if moments_here:
                mid = moments_here[0]
                if mid in cited:
                    raise ValueError(f'{mid} illustrates two pages ({cited[mid]} and {scene["page"]}). '
                                     'Give each photograph one page.')
                cited[mid] = scene['page']
        unused = sorted(set(moment_ids) - set(cited), key=order.get)
        if unused:
            raise ValueError('Photographs without a page: ' + ', '.join(unused) + '. '
                             'This book has one page per photograph so it keeps the real day; '
                             'give every photograph its page, or remove it from the book.')
        numbered = [(cited[mid], mid) for mid in moment_ids if mid in cited]
        for (previous_page, previous), (page, mid) in zip(numbered, numbered[1:]):
            if page < previous_page:
                raise ValueError(f'Pages should follow your photograph order: {mid} is on page {page} '
                                 f'but {previous} is on page {previous_page}. Reorder the scenes to '
                                 'match the order of the day.')
    return book


def stages(package, plan, moment=None):
    from .assisted_store import new_stage
    from .story import cover_title_instruction
    from .assisted_moment import restyle_brief
    book = validate(package, plan, [p['id'] for p in moment['photos']] if moment else None)
    result = []
    def add(sid, kind, title, brief, refs, **extra):
        value = new_stage(sid, kind, title)
        value.update(brief=brief, references=refs, **extra)
        result.append(value)
    style = book['visual_bible']['style']
    add('style.png', 'style', 'Art style',
        'An inviting unoccupied landscape with simple vegetation and an open path. '+style+
        ' Clean unmarked artwork surfaces.', [])
    if moment:
        # Every uploaded photograph gets its own restyle stage, right after the
        # art style exists: photo as Image 1, style as Image 2. The scenes cite
        # the approved restyled versions through ordinary asset references.
        for photo in moment['photos']:
            short = photo['caption'] if len(photo['caption']) <= 42 else photo['caption'][:42].rstrip() + '…'
            add(f"moments/{photo['id']}.png", 'moment', short,
                restyle_brief(photo), ['style.png'], source_photo=photo)
    for char in book['characters']:
        add('characters/'+char['id']+'.png', 'character', char['name'],
            f"A single full-body portrait of {char['name']}, {char['appearance']}. "
            'Relaxed upright pose, feet visible, flat warm ivory background. '+style,
            ['style.png'], character_id=char['id'])
    paths = {a['id']: ('states' if a['kind']=='character_state' else 'props' if a['kind'] in ('prop','prop_state') else 'locations')+'/'+a['id']+'.png'
             for a in plan['assets']}
    paths.update({a['id']: 'moments/'+a['id']+'.png' for a in plan['assets'] if a['kind']=='moment'})
    paths.update({c['id']: 'characters/'+c['id']+'.png' for c in book['characters']})
    kinds = {a['id']: a['kind'] for a in plan['assets']}
    for asset in prop_states.ordered_assets(plan['assets'],len(book['pages'])):
        refs = ([paths[r] for r in asset['source_assets']] if asset['kind']=='prop_state' else
                [paths[asset['source_character']]] if asset['kind']=='character_state' else ['style.png'])
        framing = ('A single full-body character portrait, relaxed upright pose, feet visible, flat warm ivory background. '
                   if asset['kind']=='character_state' else 'One complete assembled or changed prop on a flat warm ivory background. '
                   if asset['kind']=='prop_state' else 'A single isolated object on a flat warm ivory background. '
                   if asset['kind']=='prop' else 'An unoccupied view of the setting. ')
        add(paths[asset['id']], asset['kind'], asset['name'], framing+asset['appearance']+'. '+style,
            refs, character_id=asset.get('source_character',''),
            **({'source_assets':asset['source_assets'],'visible_pages':asset['visible_pages']}
               if asset['kind']=='prop_state' else {}))
    for scene in plan['scenes']:
        n = scene['page']
        scene_moment = scene['moment']
        if n == 0:
            scene_moment = scene_moment.rstrip() + ' ' + cover_title_instruction(book['title'])
        cast_count = len(scene['character_refs'])
        moment_images = [f"Image {cast_count + i + 1}" for i, r in enumerate(scene['asset_refs'])
                         if kinds.get(r) == 'moment']
        if moment_images:
            # This page illustrates a real memory: the moment reference must drive
            # the scene, not sit in the background as loose inspiration.
            scene_moment += (' This page illustrates a real moment from the reader\'s day: recreate '
                             + ' and '.join(moment_images) + ' faithfully in this storybook style — same '
                             'people, poses, key objects and setting — so the memory stays recognisable.')
        add('cover.png' if n==0 else f'pages/page-{n:03d}.png', 'scene', 'Cover' if n==0 else f'Page {n}',
            scene_moment, [paths[r] for r in scene['character_refs']+scene['asset_refs']],
            cast_refs=[paths[r] for r in scene['character_refs']],
            cast_ids=[next((a['source_character'] for a in plan['assets'] if a['id']==r),r)
                      for r in scene['character_refs']],
            page=n, text='' if n==0 else book['pages'][n-1]['text'])
    return result

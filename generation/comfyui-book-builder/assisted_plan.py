"""Private, human-reviewed production plan. Never changes the public story."""
import json
from .story import object_schema as obj, validate_package
from .assisted_references import MAX_REFERENCE_IMAGES, scene_reference_count
from .assisted_prompt_context import SCENE_GUIDANCE
from . import assisted_prop_states as prop_states

TEXT = {'type': 'string', 'minLength': 1, 'maxLength': 3000}
ID = {'type': 'string', 'pattern': '^[a-z][a-z0-9_]{0,31}$'}
IDS = {'type': 'array', 'items': ID, 'uniqueItems': True}


def schema(book):
    asset=obj({'id':ID,'kind':{'enum':['prop','location','character_state','prop_state']},
               'name':TEXT,'appearance':TEXT,'source_character':{'type':'string'}})
    asset['required'].remove('source_character')
    # Optional for old saved plans; mandatory only for the new derived-prop kind.
    asset['properties'].update(source_assets={**IDS,'minItems':1,'maxItems':MAX_REFERENCE_IMAGES},
                               visible_pages={'type':'array','items':{'type':'integer','minimum':0},
                                              'minItems':1,'uniqueItems':True})
    asset['allOf']=[{'if':{'properties':{'kind':{'const':'prop_state'}}},
                     'then':{'required':['source_assets','visible_pages']}},
                    {'if':{'properties':{'kind':{'const':'character_state'}}},
                     'then':{'required':['source_character']}}]
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
assets: create reusable references for recurring salient objects and locations. Describe permanent
shape, material, colours and size relative to a character. Keep movable props and characters out of
location reference designs. A prop reference depicts ONE object; a prop_state can depict an assembly
of several existing objects as one unit. If a character's outfit or physical
state changes, add a character_state reference with source_character set to its canonical ID and
appearance describing the complete current design. Other kinds may omit source_character.
Use unique IDs distinct from canonical character IDs. Avoid decorative reference proliferation.
scenes: page 0 is the cover, followed by every numbered page in order. Each moment is a concise
positive visual description of ONE instant that directly illustrates the page's prose. Preserve
the named actor, action, target and essential outcome. Use Name (species and distinguishing clothing)
when first naming each actor. One instance of each required character; identify the whole cast once.
Preserve recurring object designs and where a trapped object remains until freed.
Do not illustrate multiple sequential events at once or turn metaphors into extra objects.
Use natural prose, approximately 50–100 words per scene, not JSON/image-model instructions,
negative lists, measurements, labels or quoted story dialogue. Typography is typeset separately.
character_refs lists only visible canonical character IDs, substituting a character_state ID when
that change is active. It must match the approved page's charactersPresent exactly.
asset_refs lists relevant prop/location IDs, with at most ONE location. FLUX.2.dev has a budget of
SIX input reference images in total. Visible characters occupy ONE shared cast image, leaving
FIVE prop/place images. A scene without characters can use SIX prop/place images. Each reference
must be meaningful to that instant. Each prop/location is a separate input. Reference numbering is added
by code; do not write Image N yourself. continuity_notes briefly explains object/state progression.
'''
    prompt += prop_states.GUIDANCE + SCENE_GUIDANCE
    if config and config.get('story_craft_version'):
        from .story_craft import ILLUSTRATION_GUIDANCE
        prompt += ILLUSTRATION_GUIDANCE
    prompt += '\nBook package:\n'+json.dumps(package, ensure_ascii=False)
    return prompt, schema(book)


def validate(package, plan):
    import jsonschema
    from .story import make_render_plan
    book = make_render_plan(package['story'], package['production'])
    jsonschema.validate(plan, schema(book))
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
    return book


def stages(package, plan):
    from .assisted_store import new_stage
    book = validate(package, plan)
    result = []
    def add(sid, kind, title, brief, refs, **extra):
        value = new_stage(sid, kind, title)
        value.update(brief=brief, references=refs, **extra)
        result.append(value)
    style = book['visual_bible']['style']
    add('style.png', 'style', 'Art style',
        'An inviting unoccupied landscape with simple vegetation and an open path. '+style+
        ' Clean unmarked artwork surfaces.', [])
    for char in book['characters']:
        add('characters/'+char['id']+'.png', 'character', char['name'],
            f"A single full-body portrait of {char['name']}, {char['appearance']}. "
            'Relaxed upright pose, feet visible, flat warm ivory background. '+style,
            ['style.png'], character_id=char['id'])
    paths = {a['id']: ('states' if a['kind']=='character_state' else 'props' if a['kind'] in ('prop','prop_state') else 'locations')+'/'+a['id']+'.png'
             for a in plan['assets']}
    paths.update({c['id']: 'characters/'+c['id']+'.png' for c in book['characters']})
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
        add('cover.png' if n==0 else f'pages/page-{n:03d}.png', 'scene', 'Cover' if n==0 else f'Page {n}',
            scene['moment'], [paths[r] for r in scene['character_refs']+scene['asset_refs']],
            cast_refs=[paths[r] for r in scene['character_refs']],
            cast_ids=[next((a['source_character'] for a in plan['assets'] if a['id']==r),r)
                      for r in scene['character_refs']],
            page=n, text='' if n==0 else book['pages'][n-1]['text'])
    return result

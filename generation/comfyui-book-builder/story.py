"""Book contracts and prompt construction; independent of ComfyUI/GPU state."""
import hashlib
import json
import re

VERSION = "2.1.0"
DEFAULT_STYLE = (
    "Warm, hand-painted children's picture-book illustration, soft gouache and "
    "coloured-pencil texture, clear shapes, "
    "gentle lighting, a cohesive warm pastel palette."
)
DEFAULT_IDEA = ""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def asset_seed(seed, name):
    return int(digest([seed, name])[:15], 16)


def object_schema(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def render_plan_schema(page_count, max_characters):
    text = {"type": "string", "minLength": 1}
    scene = object_schema({
        "scene_prompt": text,
        "character_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 3, "uniqueItems": True},
    })
    page = object_schema({
        "page_number": {"type": "integer", "minimum": 1, "maximum": page_count},
        "text": text,
        **scene["properties"],
    })
    character = object_schema({
        "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,31}$"},
        "name": text,
        "role": {"type": "string", "enum": ["main", "supporting"]},
        "appearance": text,
        "personality": text,
    })
    # Private production metadata only. Optional for older saved story plans.
    character["properties"]["height_cm"] = {"type": "number", "minimum": 1, "maximum": 1000}
    return object_schema({
        "title": text,
        "summary": text,
        "visual_bible": object_schema({"style": text, "palette": text, "world": text}),
        "style_reference_prompt": text,
        "characters": {"type": "array", "items": character, "minItems": 1, "maxItems": max_characters},
        "cover": scene,
        "pages": {"type": "array", "items": page, "minItems": page_count, "maxItems": page_count},
    })


def validate_book(book, page_count, max_characters):
    import jsonschema
    try:
        jsonschema.validate(book, render_plan_schema(page_count, max_characters))
    except jsonschema.ValidationError as exc:
        where = ".".join(map(str, exc.absolute_path)) or "book"
        raise ValueError(f"{where}: {exc.message}") from exc
    ids = [c["id"] for c in book["characters"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Character IDs must be unique.")
    if len({c["name"].casefold() for c in book["characters"]}) != len(ids):
        raise ValueError("Character names must be unique.")
    if sum(c["role"] == "main" for c in book["characters"]) != 1:
        raise ValueError("Exactly one character must have role 'main'.")
    for character in book["characters"]:
        if "height_cm" in character:
            import math
            if not math.isfinite(character["height_cm"]):
                raise ValueError(f"{character['name']}: height_cm must be finite.")
            match = re.search(r"\b(\d+(?:\.\d+)?)\s*cm\s*tall\b", character["appearance"], re.I)
            if match and abs(float(match[1])-character["height_cm"])>1:
                raise ValueError(f"{character['name']}: height_cm contradicts the appearance description.")
    if [p["page_number"] for p in book["pages"]] != list(range(1, page_count + 1)):
        raise ValueError("Pages must appear in order, numbered 1 through page_count without duplicates.")
    used = set()
    for label, scene in [("cover", book["cover"])] + [(f"page {p['page_number']}", p) for p in book["pages"]]:
        unknown = set(scene["character_ids"]) - set(ids)
        if unknown:
            raise ValueError(f"{label}: unknown character IDs {sorted(unknown)}; use only {ids}.")
        used.update(scene["character_ids"])
        if len(scene["scene_prompt"]) > 5000:
            raise ValueError(f"{label}: scene prompt exceeds 5000 characters.")
    unused = set(ids) - used
    if unused:
        raise ValueError(f"Unused cast members {sorted(unused)}. Remove them or include them in a scene.")
    for page in book["pages"]:
        if len(page["text"].split()) > 100:
            raise ValueError(f"Page {page['page_number']} is too long; maximum 100 words per page.")
    return book


def story_schema(page_count, max_characters):
    """The original app-facing contract. Never add production fields here."""
    text = {"type": "string", "minLength": 1}
    names = {"type": "array", "items": text, "uniqueItems": True}
    page = object_schema({
        "text": text,
        "pageNumber": {"type": "integer", "minimum": 1},
        "imagePrompt": text,
        "charactersPresent": names,
        "isMainCharacterPresent": {"type": "boolean"},
    })
    metadata = object_schema({
        "theme": text, "title": text, "ageRange": text,
        "characters": {**names, "minItems": 1, "maxItems": max_characters},
        "bookSummary": text, "storyPrompt": text, "coverImagePrompt": text,
        "styleReferencePrompt": text, "mainCharacterDescriptivePrompt": text,
    })
    return object_schema({
        "id": text,
        "pages": {"type": "array", "items": page, "minItems": page_count, "maxItems": page_count},
        "metadata": metadata,
    })


def production_schema(page_count, max_characters):
    properties = render_plan_schema(page_count, max_characters)["properties"]
    return object_schema({
        "visual_bible": properties["visual_bible"],
        "style_reference_prompt": properties["style_reference_prompt"],
        "characters": properties["characters"],
        "cover_character_ids": properties["cover"]["properties"]["character_ids"],
    })


def book_schema(page_count, max_characters):
    # The LLM returns two separate documents. Only `story` is given to the app.
    return object_schema({"story": story_schema(page_count, max_characters),
                          "production": production_schema(page_count, max_characters)})


def validate_story(story, page_count, max_characters):
    import jsonschema
    try:
        jsonschema.validate(story, story_schema(page_count, max_characters))
    except jsonschema.ValidationError as exc:
        raise ValueError(f"story.{'.'.join(map(str, exc.absolute_path))}: {exc.message}") from exc
    if [p["pageNumber"] for p in story["pages"]] != list(range(1, page_count + 1)):
        raise ValueError("Story pageNumber values must run from 1 through page_count in order.")
    names = set(story["metadata"]["characters"])
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError("Story character names must be distinct regardless of capitalization.")
    for page in story["pages"]:
        if not set(page["charactersPresent"]).issubset(names):
            raise ValueError(f"Page {page['pageNumber']}: charactersPresent must use exact metadata.characters names.")
        if len(page["charactersPresent"]) > 3:
            raise ValueError(f"Page {page['pageNumber']}: this renderer supports at most three visible characters.")
    return story


def make_render_plan(story, production):
    """Adapt the fixed public contract to private rendering data without editing it."""
    page_count = len(story["pages"])
    max_characters = len(story["metadata"]["characters"])
    validate_story(story, page_count, max_characters)
    import jsonschema
    try:
        jsonschema.validate(production, production_schema(page_count, max_characters))
    except jsonschema.ValidationError as exc:
        raise ValueError(f"production: {exc.message}") from exc
    # Private planning sometimes capitalizes a name differently from the public
    # story. Align an unambiguous spelling to the canonical story name without
    # altering either input document or accepting a genuinely different cast.
    canonical_names = {name.casefold(): name for name in story["metadata"]["characters"]}
    characters = [dict(c, name=canonical_names.get(c["name"].casefold(), c["name"]))
                  for c in production["characters"]]
    by_name = {c["name"]: c for c in characters}
    if len(by_name) != len(characters) or set(by_name) != set(story["metadata"]["characters"]):
        raise ValueError(f"Production cast must match metadata.characters. Expected {story['metadata']['characters']}; got {[c['name'] for c in production['characters']]}.")
    leads = [c["name"] for c in characters if c["role"] == "main"]
    if len(leads) != 1:
        raise ValueError("Production must identify exactly one main character.")
    for p in story["pages"]:
        if p["isMainCharacterPresent"] != (leads[0] in p["charactersPresent"]):
            raise ValueError(f"Page {p['pageNumber']}: isMainCharacterPresent contradicts charactersPresent.")
    book = {
        "title": story["metadata"]["title"], "summary": story["metadata"]["bookSummary"],
        "visual_bible": production["visual_bible"], "style_reference_prompt": production["style_reference_prompt"],
        "characters": characters,
        "cover": {"scene_prompt": story["metadata"]["coverImagePrompt"], "character_ids": production["cover_character_ids"]},
        "pages": [{"page_number": p["pageNumber"], "text": p["text"], "scene_prompt": p["imagePrompt"],
                   "character_ids": [by_name[name]["id"] for name in p["charactersPresent"]]} for p in story["pages"]],
    }
    return validate_book(book, page_count, max_characters)


def validate_package(package, page_count, max_characters):
    if set(package) != {"story", "production"}:
        raise ValueError("Return an envelope with exactly 'story' and 'production'.")
    validate_story(package["story"], page_count, max_characters)
    return make_render_plan(package["story"], package["production"])


def writing_prompt(config):
    if config.get('story_craft_version'):
        from . import story_craft
        if config['story_craft_version'] not in story_craft.SUPPORTED_VERSIONS:
            raise ValueError('This saved book needs an unavailable story craft version.')
        if config['story_craft_version'] == 'picturebook-2':
            from .story_craft_auto import writing_prompt as automatic_prompt
            return automatic_prompt(config)
        return story_craft.writing_prompt(config)
    idea = config["story_idea"].strip() or "Invent an original child-friendly story idea, cast and setting."
    if config.get('max_ensemble_pages', -1) >= 0:
        idea += (f"\nAt most {config['max_ensemble_pages']} pages may show three characters together. "
                 "Count charactersPresent entries to verify this limit. Other pages use one/two-character "
                 "framing of a real prose moment. Keep all recurring characters involved in the story.")
    return f"""Create a complete original picture book for ages {config['age_range']}.
Story idea: {idea}
Exactly {config['page_count']} story pages, plus a separate cover. At most {config['max_characters']} named characters.
Requested art direction: {config['art_style']}
Creative variation seed: {config['seed']}.
Write all story prose and metadata in British English (UK spelling and vocabulary), such as
colour, favourite, centre and organise. Keep dialogue natural for children in the UK; do not
switch to American spellings.

Write a coherent beginning, small problem, meaningful actions and a satisfying ending. The final
page must show a specific consequence of the protagonist's choice and pay off a detail planted
earlier. Do not stop after a character announces a new identity, repeats the premise, says a
generic thank-you or receives an unexplained magic fix. Give a comic reversal a concrete result
and reaction, or a tender ending a visible choice that changes what happens next. Follow the resolution
with a clear aftermath or settling image, a shared reaction and a final line that sounds finished when
read aloud while leaving a pleasant echo. Do not end on ordinary small talk or in the middle of motion.
Test the last
two pages against the original want/problem, decisive choice, immediate consequence and final
image or callback; if the ending would work after removing the setup, rewrite it.
Make the ending compatible with each participant's earlier actions, location and knowledge.
Explain any important departure, return trip, pretence or confusion needed for a surprise reveal;
the child should not have to invent those connecting events to understand the resolution.
Use natural read-aloud prose, about 20–50 words per page; do not force rhymes unless requested.
Page text is plain text for the reading app. Do not use Markdown emphasis, headings, or code formatting.
Plain text still needs normal punctuation: put direct speech inside quotation marks, and punctuate
the dialogue tags correctly. For example: “That is much too loud!” said Pip. Do not strip speech marks.
Each page must advance the story and have a distinct, visually drawable moment.
Write for the child's ear: concrete actions, precise sensory details, playful dialogue, and
occasional surprise. Let the protagonist make choices and solve the problem through action.
Avoid generic filler ('quiet joy', 'tail wrapped like a promise', 'their hearts filled with warmth'),
explicit moral lessons and unexplained magic that resolves the plot. Do not put character
measurements, design specifications or repeated outfit descriptions into page text.
Choose names that are easy to say aloud, clearly distinct and suited to each character's species,
personality and world. Avoid defaulting to the same familiar names or the same small set of animal
species in every book. Vary species, sounds and roles when the premise allows; if two characters
share a species, make their silhouettes, colours or clothing unmistakable. Avoid confusingly
similar names or initials.
Each page's imagePrompt must depict an actual moment from THAT page's prose. If the mouse
is in a hand in the prose, do not place it on the grass in the imagePrompt. Include key held
objects, actions and expressions. Do not replace an active scene with everybody facing forward.
The prose and imagePrompt must also obey the user's requested placement and actions.
Keep the cast small and reuse them. Describe each character's immutable species/age, face,
hair/fur, body shape, exact outfit colours, footwear and identifying accessory in appearance.
Use stable lowercase IDs; exactly one main character. Every visible person or animal belongs
to the cast and must be listed by exact name in that page's charactersPresent. Maximum three per illustration.
An empty charactersPresent list means a genuinely unpopulated scene, not anonymous extra actors.
An unnamed insect trading an object or an animal wearing a hat is a cast member too. Do not
add such actors outside metadata.characters and production.characters, even for a visual joke.
Keep clothing and physical features fixed throughout.
Carry visible temporary states forward explicitly in EVERY relevant imagePrompt. Each page is
rendered independently from clean canonical portraits: jam on an ear, muddy boots, wet fur or a
damaged prop will disappear unless that page's prompt says it is still present. Establish any
cleaning or repair in the story before removing the mark. Prose need not repeat these art details.
Include missing parts such as a lost costume button. If a later reveal establishes that a visible
change happened before the opening, the earlier illustrations need that changed state too.
Use separate carried props for tools. Do not remove identifying clothing to patch a wagon,
make a rope, etc.; that would contradict the canonical reference used by later illustrations.
The visual_bible must fix the palette, technique and recurring environment details in a way
that matches the requested art direction.
Use ONE exact outfit and footwear choice per character: never 'barefoot or shoes' or alternative colours.
Give every cast member a recognisably different visual design, not merely a different name
or personality. If two characters share a species, distinguish silhouette and fixed colours
or a strong identifying accessory. Keep these distinctions readable in a small illustration.
Give animal species distinctive anatomy (e.g. a mouse has round ears and a thin bare tail;
a fox has triangular ears, a pointed muzzle and a bushy tail). Describe supporting characters
as carefully as the main character. A character's size must be unambiguous relative to the others.
Design newly invented casts for readable picture-book illustrations: unless the user explicitly
requests tiny real-world proportions, use friendly anthropomorphic supporting animals whose
standing height is at least one fifth of the tallest character. State these fictional proportions
clearly and keep them fixed. This lets a child recognise expressions and identifying clothes.
Never change a size specified by the user or an existing supplied story to satisfy this preference.
visual_bible.style contains ONLY art materials and rendering technique, with no characters,
faces, outfits, or setting. visual_bible.world contains environment details only.
Include each character's physical size in appearance. For scenes with differently sized
characters, explicitly describe their relative scale in imagePrompt and coverImagePrompt:
a tiny mouse should fit in a child's palm, not become child-sized. Specify each character's
own clothing and footwear, including bare paws when appropriate; never share outfits between
characters. Keep these details consistent with mainCharacterDescriptivePrompt.
Also set production.characters[].height_cm to the character's normal full-body height in
centimetres (not tail length), so a visual cast-size guide can preserve those proportions.
Each imagePrompt describes composition, action, expressions, setting, time and light; use
the character names. Avoid dialogue balloons, written words, logos and text in the artwork.
Keep each listed visible character recognisable, including its face and identifying clothing
or features. Close-ups can crop legs, but do not list a character while showing only a detached
boot or hand. Frame the actor together with the relevant object and gesture instead.
Keep imagePrompt concise (at most 100 words), describe ONE drawable moment and where each
character is placed. Distinguish left/centre/right when three characters share a scene.
Use the characters' names in imagePrompt; their complete immutable appearances are already
in production.characters and supplied as reference images. Do not repeat the full character
description on every page. Spend the prompt on the page's actual action, framing and setting.
The coverImagePrompt must also specify the exact book title in quotation marks, with readable
story-appropriate display lettering and a considered placement that suits the scene. Keep the
title legible at thumbnail size, in clear space away from faces and the focal action, and include
no other words. Page imagePrompts contain artwork only; their reading text is typeset separately.
style_reference_prompt describes a beautiful EMPTY environment or still life from this world, with NO people, animals, faces,
silhouettes or characters, to establish the art style without contaminating later references.
Return an object with TWO SEPARATE documents: story and production.
story MUST follow the app's original contract exactly:
{{"id":"...","pages":[{{"text":"...","pageNumber":1,"imagePrompt":"...","charactersPresent":["exact character names"],"isMainCharacterPresent":true}}],
"metadata":{{"theme":"...","title":"...","ageRange":"...","characters":["exact character names"],"bookSummary":"...","storyPrompt":"...","coverImagePrompt":"...","styleReferencePrompt":"...","mainCharacterDescriptivePrompt":"..."}}}}.
Number pageNumber values 1 through {config['page_count']}. metadata.characters is an array of strings, NEVER objects.
charactersPresent uses those exact names. isMainCharacterPresent must agree with the main character's presence.
production is private automation data: visual_bible, style_reference_prompt, detailed characters
with IDs/name/role/appearance/personality, and cover_character_ids. Its cast names must match
story.metadata.characters exactly. The main character's appearance must agree with
story.metadata.mainCharacterDescriptivePrompt. Place all ID/reference/render planning fields ONLY in production.
Return only JSON matching the supplied envelope schema.
"""


def plain_generated_prose(package):
    """Generated app prose is plain text; retain the original draft separately."""
    import copy
    result=copy.deepcopy(package)
    if not isinstance(result,dict) or not isinstance(result.get('story'),dict) or not isinstance(result['story'].get('pages'),list):
        return result  # Let the schema validator report malformed model output.
    for page in result['story']['pages']:
        # Remove balanced Markdown emphasis, retaining punctuation and prose.
        # Do not touch IDs, art prompts, or imported user-supplied story JSON.
        if isinstance(page,dict) and isinstance(page.get('text'),str):
            page['text']=re.sub(r'(?<![\w*])(\*{1,2})([^*\n]+?)\1(?![\w*])',r'\2',page['text'])
    return result


def style_text(project):
    bible = project["book"]["visual_bible"]
    # Do not append the world description (which may mention the protagonist)
    # to every portrait and empty style reference. Strip subject-bearing clauses
    # from older art directions, without changing the public story document.
    clauses = re.split(r"[,.;]", bible["style"])
    technique = ", ".join(c.strip() for c in clauses if c.strip() and not re.search(
        r"\b(faces?|characters?|girls?|boys?|people|animals?|hair|fur|dress|outfit|footwear)\b", c, re.I))
    palette = bible['palette']
    if project.get('render_settings', {}).get('style_prompt_version', 1) >= 2:
        # A palette saying "red and yellow for clothing" repeatedly generated
        # people in an otherwise empty landscape. Keep the colours, not their
        # subject assignment. Canonical outfits live in character appearances.
        palette = re.sub(r'\s+for\s+(?:the\s+)?(?:clothing|clothes|outfits|costumes)\b', '', palette, flags=re.I)
        subjects = r'\b(faces?|characters?|girls?|boys?|people|animals?|hair|fur|dress|outfits?|footwear|clothing|clothes|coats?|boots?)\b'
        palette = ', '.join(c.strip() for c in re.split(r'[,.;]', palette) if c.strip() and not re.search(subjects,c,re.I))
    return f"{technique}. Palette: {palette}."


def reference_prompt(project, character):
    if project.get('render_settings', {}).get('positive_flux_prompts'):
        return (f"A full-body three-quarter portrait of {character['name']}: {character['appearance']}. "
                "One figure in a friendly neutral pose, head and feet visible against a plain pale backdrop. "
                "Show the baseline colours, surfaces and identifying clothes. "
                "Image 1 supplies painting style, palette and texture. Unmarked artwork surfaces. " + style_text(project))
    if project.get("render_settings", {}).get("portrait_prompt_version", 1) >= 2:
        # Personality may describe later plot events (for example jam on ears).
        # References establish the baseline design, before those events occur.
        # Preserve legacy prompt reconstruction for existing asset signatures.
        return (f"Create a single-character reference illustration of {character['name']}. "
                f"Permanent appearance: {character['appearance']}. "
                "Depict this baseline design in a friendly neutral full-body pose, head and feet visible, "
                "front three-quarter view on a plain pale backdrop. Show only permanent physical features "
                "and the specified identifying clothes. Skin, fur and clothing have their usual colours "
                "and condition; temporary story-event marks and carried story props belong in later scenes. "
                "Use Picture 1 ONLY for drawing style, palette and paint texture. One figure, one view, "
                "an uncluttered background without lettering or labels. " + style_text(project))
    return (f"Create a new single-character reference illustration of {character['name']}. "
            f"Exact appearance: {character['appearance']}. Personality: {character['personality']}. "
            "Use Picture 1 ONLY as a reference for the drawing style, palette and paint texture. "
            "Show this ONE character full body, head and feet visible, a clear front three-quarter view, "
            "friendly neutral pose on a simple uncluttered pale background. One figure only, "
            "no character sheet panels, no alternate views, no lettering or labels. " + style_text(project))


def scene_style_text(project):
    text = style_text(project)
    if project.get('render_settings', {}).get('scene_style_policy', 0) >= 1:
        # A colour assignment like "iridescent tones for the bubble" is not a
        # request for that prop on every page, including after it disappears.
        text = re.sub(r'\s+for\s+[^,.;]*', '', text, flags=re.I)
    return text


def scene_references(project, scene):
    from .state_ledger import character_reference
    refs = [character_reference(project, scene, cid) for cid in scene["character_ids"]]
    separate_style = (project.get('render_settings', {}).get('scene_reference_policy', 0) < 2
                      and not project.get('scene_contract'))
    if len(refs) < 3 and (separate_style or not refs):
        refs.append("style.png")
    return refs


def scene_prompt(project, scene):
    from .state_ledger import scene_character_description
    from .scene_contract import scene_brief
    cast = {c["id"]: c for c in project["book"]["characters"]}
    shared = uses_cast_guide(project, scene)
    parts = [f"One picture-book illustration with exactly {len(scene['character_ids'])} separate characters, each appearing ONCE.", scene_brief(project, scene)]
    if shared:
        parts.append("Image 1 shows the SAME cast together on one common scale, from left to right in the order below. "
                     "Preserve their canonical faces, species, colours, clothing AND physical proportions. "
                     "Use fresh expressive poses and the requested scene composition. Replace the pale backdrop completely; "
                     "do not copy the reference card rectangles, standing lineup or layout.")
    for i, cid in enumerate(scene["character_ids"], 1):
        c = cast[cid]
        label = f"Cast member {i} in Image 1" if shared else f"Image {i}"
        parts.append(f"{label}: {c['name']}. Keep this character's identity, species, colours and outfit. {scene_character_description(project, scene, c)}")
    if shared:
        from .scale import cast_height
        tallest = max((cast[cid] for cid in scene['character_ids']), key=cast_height)
        parts.append("Physical standing heights, including ears, remain proportional in every pose: " + "; ".join(
            f"{cast[cid]['name']} is {cast_height(cast[cid])/cast_height(tallest):.2f} times {tallest['name']}'s height"
            for cid in scene['character_ids'] if cid != tallest['id']) + ". Do not enlarge supporting characters to fill the frame.")
    if not shared and 'style.png' in scene_references(project, scene):
        parts.append(f"Picture {len(scene['character_ids']) + 1} is ONLY the style and palette reference, not an instruction to copy its composition.")
    if not scene["character_ids"]:
        parts.append("This is a character-free scene: no people, animals, faces, figures or silhouettes.")
    else:
        parts.append("Include only the named characters in this scene, once each. Do not blend their identities or outfits, and do not add extra characters.")
    cover = scene is project.get('book', {}).get('cover') or 'page_number' not in scene
    if cover:
        parts.append(cover_title_instruction(project['book']['title']))
    else:
        parts.append("No text, captions, speech bubbles, borders, watermarks or lettering.")
    parts.append(scene_style_text(project))
    parts.append("Use a fresh scene composition, not the reference portrait pose or a collage.")
    from .state_ledger import state_brief
    return "\n".join(parts) + state_brief(project, scene)


def cover_title_instruction(title):
    """Give the image model one exact, positive instruction for cover typography."""
    quoted = json.dumps(title, ensure_ascii=False)
    return (f'The cover includes the exact title {quoted} as readable lettering. Choose a display '
            'font and placement that fit the story mood and artwork; keep it legible at thumbnail '
            'size in clear negative space, away from faces and the focal action. Include only this '
            'title as text.')


def uses_cast_guide(project, scene):
    from .scale import cast_height
    settings = project.get('render_settings', {})
    by_id = {c['id']:c for c in project['book']['characters']}
    return ((settings.get('renderer') == 'flux2' or settings.get('qwen_scene_recipe') == 'edit2511_lightning8')
            and settings.get('reference_strategy') == 'cast_guide'
            and len(scene['character_ids']) > 1
            and all(cast_height(by_id[cid]) for cid in scene['character_ids']))


def asset_specs(project):
    seed = project["config"]["seed"]
    specs = [{"name": "style.png", "kind": "style", "references": [],
              "prompt": project["book"]["style_reference_prompt"] + "\n" + style_text(project) +
              " A completely unpopulated scene. No people, animals, faces, characters, text or lettering."}]
    if project.get('render_settings', {}).get('positive_flux_prompts'):
        specs[0]['prompt'] = (project['book']['style_reference_prompt'] + '\n' + style_text(project)
                             + ' A tranquil unpopulated setting, with unmarked artwork surfaces.')
    for c in project["book"]["characters"]:
        specs.append({"name": f"characters/{c['id']}.png", "kind": "character", "references": ["style.png"], "prompt": reference_prompt(project, c)})
    from .visual_library import specs as visual_specs, entries as visual_entries, asset_name as visual_asset_name
    specs.extend(visual_specs(project))
    from .prop_groups import specs as group_specs
    specs.extend(group_specs(project))
    from .state_ledger import variant_specs
    specs.extend(variant_specs(project))
    for name, scene in [("cover.png", project["book"]["cover"])] + [(f"pages/page-{p['page_number']:03d}.png", p) for p in project["book"]["pages"]]:
        specs.append({"name": name, "kind": "scene", "references": scene_references(project, scene), "prompt": scene_prompt(project, scene)})
        if uses_cast_guide(project, scene):
            specs[-1]['reference_layout'] = 'cast_guide'
        visual_refs = visual_entries(project, specs[-1])
        if visual_refs:
            specs[-1]['visual_references'] = [visual_asset_name(e) for e in visual_refs]
        if project.get('art_plan'):
            from .state_assets import scene_props
            specs[-1]['props'] = scene_props(project, scene)
        if project.get('state_edits'):
            from .state_ledger import active_changes
            specs[-1]['state_edit_hashes'] = [project['state_edits'][c['id']]['hash']
                                             for c in active_changes(project,scene)
                                             if c['id'] in project['state_edits']]
    for spec in specs:
        spec["seed"] = asset_seed(seed, spec["name"])
        spec["signature"] = digest([VERSION, project["book"], project.get("render_settings"), spec])
    return specs


def safe_asset_name(name):
    if not re.fullmatch(r"(?:style|cover)\.png|(?:characters|props|locations|prop_groups)/[a-z][a-z0-9_]{0,31}\.png|states/[a-z][a-z0-9_]{0,31}-[a-f0-9]{12}\.png|pages/page-[0-9]{3}\.png", name):
        raise ValueError(f"Invalid book asset name: {name!r}")
    return name

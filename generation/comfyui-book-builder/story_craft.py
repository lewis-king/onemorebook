"""Picture-book craft for new assisted sessions; no quality gate or public fields.

Sources and evidence limits: generation/docs/STORY-CRAFT-RESEARCH.md.
Keep this version stable for saved sessions; introduce a new version for later revisions.
"""
import re

VERSION = 'picturebook-1'
SUPPORTED_VERSIONS = (VERSION, 'picturebook-2')
DEFAULT_AGE = '4–7'

FLAVOURS = {
    'surprise': ('Choose for me', 'Choose ONE of the following approaches to suit the premise: '
                 'a playful adventure, comic mix-up, big-feelings story, or imaginative why tale. '
                 'Vary the approach between seeds; do not combine all four.'),
    'adventure': ('Playful adventure', 'Give the protagonist an appealing want and an obstacle. '
                  'Build a connected sequence of attempts with changing consequences. Plant an '
                  'ordinary detail early that the protagonist uses differently at the payoff. '
                  'Include playful dialogue, a discoverable surprise and room for a quiet beat.'),
    'comedy': ('Comic mix-up', 'Build a comic mismatch the child can spot: a confident claim, '
               'mistaken assumption or unexpected use of something familiar. Escalate it in '
               'different ways, with readable reactions and a final reversal or callback. '
               'Keep the underlying physical reality coherent. The joke is the situation, '
               'not humiliation, appearance, disability or a forced lesson.'),
    'feelings': ('Big feelings', 'Start from an everyday wish or expectation that matters to a '
                 'child. Let the feeling be understandable before anyone offers advice. Show it '
                 'in a concrete gesture, dialogue or choice. Allow help and time; let the child '
                 'character choose a small workable response. The original disappointment need '
                 'not disappear for the ending to feel hopeful. Keep warmth and humour; avoid '
                 'lectures, instant emotional cures or rewarding only cheerful behaviour. '
                 'When shyness or belonging is central, show patient inclusion and participation '
                 'at the character\'s own pace; quietness is not a fault to cure.'),
    'wonder': ('An imaginative why?', 'Begin with a curious why or how and invent an ORIGINAL '
               'playful explanation in a clearly make-believe world. Let attempts and their '
               'consequences lead to the answer; use a satisfying visual reveal. Signal this '
               'as an invented tale, not scientific fact or an authentic traditional story. '
               'Establish any fantastical rule early and apply it consistently.'),
}

LANGUAGE = {
    'patterned': ('Prose with a refrain', 'Use natural prose with a short, original recurring '
                  'phrase or exchange a child can join in with. Its context should change, '
                  'with a meaningful variation at the payoff. Repeat for anticipation, not '
                  'to fill pages. Do not force end rhyme.'),
    'prose': ('Natural prose', 'Use expressive read-aloud prose with varied sentence lengths, '
              'precise verbs and dialogue that gives each speaker a voice. Repetition is optional. '
              'Leave pauses for surprise; avoid ornamental filler and forced rhyme.'),
    'rhyme': ('Rhyming verse', 'Use a consistent spoken beat and natural syntax. Check every line '
              'for stress and sense; replace strained rhymes rather than changing the plot to fit '
              'them. A recurring chorus may help. Each line must earn its place. Preserve verse '
              'line breaks inside JSON text strings. A human will still need to read it aloud.'),
}

ART = {
    'painted': ('Warm painted texture', "Children's picture-book illustration in soft gouache "
                'and coloured pencil, expressive drawn faces, clear silhouettes, tactile paper '
                'texture, warm balanced colours and gentle light.'),
    'graphic': ('Bold graphic colour', "Children's picture-book illustration with lively ink "
                'outlines and flat gouache colour, expressive gestures, distinct silhouettes, '
                'large areas of colour and simple backgrounds around the focal action.'),
    'paper': ('Layered paper shapes', "Children's picture-book illustration with layered cut-paper "
              'shapes, softly textured colour, clear silhouettes, expressive simple faces and '
              'a small coordinated palette with contrasting focal accents.'),
}


def preferences(values):
    """Validate new-book choices once; never retrofit existing session configs."""
    if not any(key in values for key in ('story_flavour', 'read_aloud', 'art_preset')):
        return {'story_craft_version': 'picturebook-2'}
    # Saved workflow/API callers with explicit old choices keep that version.
    result = {}
    for key, options, default in [('story_flavour', FLAVOURS, 'surprise'),
                                  ('read_aloud', LANGUAGE, 'patterned'),
                                  ('art_preset', ART, 'painted')]:
        value = values.get(key, default)
        if not isinstance(value, str) or value not in options:
            raise ValueError(f'Unknown {key.replace("_", " ")}; choose an available option.')
        result[key] = value
    result['story_craft_version'] = VERSION
    return result


def age_guidance(age_range):
    numbers = [int(n) for n in re.findall(r'\d+', age_range)]
    if numbers and max(numbers) <= 3:
        return ('Keep language especially concrete and brief: usually 5–25 words per page, '
                'a simple visible cause and effect, familiar actions and repeated sounds.')
    if numbers and min(numbers) >= 7:
        return ('Use a compact picture-book form for older listeners: usually 30–65 words per '
                'page, a little more inference and wordplay, with visual evidence for the payoff.')
    return ('For shared reading at ages 4–7, use an accessible surface story with a second layer '
            'of wit or feeling to discover. Usually 20–55 words per page; let a reveal be shorter. '
            'These are pacing guides, not quotas. Use a few interesting words whose meanings '
            'are clear from action or pictures, rather than baby talk or vocabulary exercises.')


def writing_prompt(config):
    flavour = FLAVOURS[config.get('story_flavour', 'surprise')][1]
    language = LANGUAGE[config.get('read_aloud', 'patterned')][1]
    idea = config['story_idea'].strip() or 'Invent a fresh premise, cast and setting.'
    return f'''Create an original picture book for shared reading, ages {config['age_range']}.
Exactly {config['page_count']} story pages and a separate cover; at most {config['max_characters']} named characters.
Premise: {idea}
Art direction: {config['art_style']}
Creative variation seed: {config['seed']}.
Write all story prose and metadata in British English (UK spelling and vocabulary), such as
colour, favourite, centre and organise. Keep dialogue natural for children in the UK; do not
switch to American spellings.

STORY EXPERIENCE
{flavour}
{language}
{age_guidance(config['age_range'])}
Invent your own characters, world, phrases and plot. Draw on general picture-book craft rather
than recreating a published author's voice, recognisable cast, scenes or signature refrains.
Make the opening specific and interesting quickly. Give the protagonist a want, belief or worry
that a child can follow. Each page changes the situation, reveals character or pays off a joke;
not every page needs a new prop, mishap or cliffhanger. Vary tension, participation and quiet.
Put useful clues before their payoff. A page ending can invite a guess; the next page should
reward it. End with an earned action, image or callback, not an explanation of the moral. The
final page must show a specific consequence of the protagonist's choice and pay off a detail
planted earlier. Do not stop after a character simply announces a new identity, repeats the
premise, says a generic thank-you or gets an unexplained magic fix. Give a comic reversal a
concrete result and reaction, or give a tender ending a visible choice that changes what happens.
After the resolution, show a clear aftermath or settling image, a shared final reaction and a last
line with satisfying read-aloud cadence. The final page should feel unmistakably finished while
leaving a pleasant echo; do not end on ordinary small talk or in the middle of motion.
Gentle themes may emerge through consequences and relationships. Pure silliness is also worthwhile.
Allow support without making the protagonist a spectator. Keep surprises fair and stakes suitable
for the chosen age. Convey feelings through behaviour as well as occasional direct naming.

Choose names that are easy to say aloud, clearly distinct and suited to each character's species,
personality and world. Avoid defaulting to the same familiar names or the same small set of animal
species in every book. Vary species, sounds and roles when the premise allows; if two characters
share a species, make their silhouettes, colours or clothing unmistakable. Avoid confusingly
similar names or initials.

PLAN AND EDIT BEFORE RETURNING THE MANUSCRIPT
First work out the want/belief, the causal sequence, the turning point and the payoff. Then revise
the complete manuscript for read-aloud rhythm, originality and emotional credibility. Check each
choice against the goal: if a character starts protecting what they previously tried to destroy,
show WHY their goal changed or revise the action. Track who knows what, who acts, where each
character is, how they arrive, and each important object's location, size, support and condition.
Introduce needed tools before use; establish fantastical rules before they solve a problem.
Check the ending works with earlier choices. Test the last two pages: name the original want or
problem, decisive choice, immediate consequence and final image or callback. If the ending would
still work after removing the story's setup, revise it. Remove repetitive filler and unnecessary
explanation.
Return the finished manuscript only, not your reasoning, competing drafts or a self-awarded score.

WORDS AND PICTURES
Write plain reading text with normal punctuation and quoted direct speech. Keep design details,
measurements, illustration instructions and review questions out of the reading text.
For each page, imagePrompt describes ONE physically drawable instant in about 40–90 words.
Show the prose's explicit actor, action, target and relevant state. Pictures can ADD a reaction,
a visual clue or a joke the words leave unstated. Dialogue or pretend play may be deliberately
wrong: depict the established physical reality, not a literal version of a character's false
claim. Make the intentional contrast clear in imagePrompt without adding a second character.
Narration and essential actions still need to agree with the picture. Metaphors are not extra props.
Choose a clear focal action, readable face/gesture and natural gaze between participants.
Vary framing across pages when it serves the story; keep visual reveals after their setup.
Use Name (species and distinctive clothing/feature) at the first mention of each visible actor;
identify each actor once, then describe interactions. Describe essential contact/containment and
relative scale, not a repeated inventory of the cast. Surfaces are unmarked; text is typeset separately.

CANONICAL WORLD AND CONTINUITY
Use a small recurring cast with clearly different silhouettes, species anatomy or fixed colours.
Every visible person/animal, even a tiny helper, belongs to metadata.characters and production.characters;
charactersPresent lists their exact names, at most THREE per image. Empty means an unpopulated scene.
Show each listed actor recognisably; no detached-hand-only cameos. Exactly one main character.
appearance fixes species/age, face, body, colours, one outfit/footwear choice and identifying features.
Set normal full-body height_cm numerically and describe relative sizes consistently. For invented
animal casts, keep the smallest at least one fifth of the tallest unless the premise specifies
otherwise. Never change the user's requested proportions. Bare paws or unclothed animals are valid.
Preserve identity and recurring object geometry, material, colour and relative size. Design stable
clothing; use separate props for tools. Record visible dirt, wetness, damage, lost parts or intentional
story transformations in EVERY affected imagePrompt until the prose establishes a change or repair.
The private illustration plan can create state references; ordinary changes of emotion are poses,
not new character designs. Keep transformations simple enough to depict clearly.
visual_bible.style contains medium and rendering technique only; palette holds coordinated colours;
world holds environment only. Follow the requested art direction consistently, with focal contrast
and enough quiet space to read the gesture. style_reference_prompt is an unpopulated environment
or still life in that style. Cover artwork uses the canonical cast, suggests the premise, and
includes the exact title in quotation marks with readable, story-appropriate display lettering
placed in clear space away from faces and the focal action. Page artwork contains no lettering;
reading text is typeset separately.

OUTPUT CONTRACT
Return exactly TWO documents in one JSON object: story and production, matching the supplied schema.
story is the existing public app contract. Number pageNumber 1 through {config['page_count']}.
metadata includes theme, title, ageRange, characters, bookSummary, storyPrompt, coverImagePrompt,
styleReferencePrompt and mainCharacterDescriptivePrompt. The last field exactly describes the
one production character whose role is main. metadata.characters contains name strings;
isMainCharacterPresent agrees with the visible main character. metadata.ageRange is {config['age_range']}.
production contains visual_bible, style_reference_prompt, characters with id/name/role/appearance/
personality/height_cm, and cover_character_ids. Use stable lowercase IDs; cast names must match story.
The main appearance and style prompts must agree with their public metadata counterparts.
Put no new craft, review or reference-planning fields into the public story. Return only JSON.
'''


ILLUSTRATION_GUIDANCE = '''
Narrative illustration: preserve the approved story's joke, emotion and page-turn timing.
The reader may know more than a character. When speech or pretend play makes a knowingly false
claim, keep the established species, scale and physical reality; use expressions or staging to
make the contrast readable. Do not transform a character merely because they claim to be something
else. Actual story transformations need explicit state references. Image-only clues and reactions
may add meaning without contradicting narrated actions, introducing unlisted actors or revealing
tomorrow's surprise early. Vary close/medium/wide framing where useful, with ONE focal action and
readable gaze/gesture. Keep optional background detail subordinate; avoid a row of posed portraits.
Carry persistent objects/states forward. Storybook invention is deliberate; accidental changes of
cast, anatomy, geometry, contact or the prose's named actor are still errors.
'''


def review_guide(package, config):
    """Observable counts and human questions, deliberately not automated verdicts."""
    if config.get('story_craft_version') == 'picturebook-2':
        from .story_craft_auto import review_guide as automatic_guide
        return automatic_guide(package, config)
    pages = package.get('story', {}).get('pages', [])
    counts = [{'page': p.get('pageNumber'), 'words': len(p.get('text', '').split())}
              for p in pages if isinstance(p, dict) and isinstance(p.get('text', ''), str)]
    flavour = config.get('story_flavour', 'surprise')
    question = {
        'comedy': 'Can your child spot the comic mismatch, and does the ending give it a fresh turn?',
        'feelings': 'Does the character get time, support and a believable choice, without having to become cheerful or outgoing to belong?',
        'wonder': 'Does the invented explanation follow its own rules and feel clearly make-believe?',
        'adventure': 'Do the attempts change what happens, and does an earlier detail help earn the ending?',
        'surprise': 'Is there a particular joke, feeling or discovery that makes this book worth returning to?',
    }[flavour]
    return {'version': config['story_craft_version'], 'age_range': config['age_range'],
            'flavour': FLAVOURS[flavour][0], 'read_aloud': LANGUAGE[config['read_aloud']][0],
            'words': sum(c['words'] for c in counts), 'pages': counts,
            'questions': [question, 'Read a few pages aloud: do the words flow, with space to join in or react?',
                          'Can you follow who wants what and why each important action happens?',
                          'Do the pictures add a clue or reaction while preserving the actual story action?']}

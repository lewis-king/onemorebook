"""Open-ended craft defaults for the simple creator (picturebook-2)."""
from .assisted_story import page_bounds

ART_DIRECTION = (
    'Choose a coherent, expressive picture-book illustration medium and palette suited to '
    'this particular story and ages 4–7. Honour any visual preferences in the idea. Use '
    'readable silhouettes, faces, gestures and focal contrast. Keep the chosen look '
    'consistent throughout the book; describe materials and visual qualities in the visual bible.'
)


def writing_prompt(config):
    low, high = page_bounds(config)
    length = (f'Exactly {low} illustrated story pages.' if low == high else
              f'Choose {low}–{high} illustrated story pages while planning the manuscript. '
              'Choose the count for its natural pacing: give a meaningful beat room, combine '
              'redundant beats and stop at the earned ending. Do not pad to fourteen or to the '
              'maximum. These are reading screens with one illustration each, not printed leaves.')
    if low != high and config.get('page_count_target'):
        length += (f" Use {config['page_count_target']} pages as the starting point, then use fewer "
                   'or more within the range when the story benefits. Let the arc determine the '
                   'final count; do not squeeze or pad a story just to hit the starting point.')
    idea = config['story_idea'].strip() or 'Invent a fresh, distinctive premise, cast and setting.'
    return f'''Create an original, engaging picture book for shared reading at ages {config['age_range']}.
Idea and any reader preferences: {idea}
Creative variation seed: {config['seed']}.
{length} A separate cover is additional to that count.
At most {config['max_characters']} named characters; choose the cast the story needs.
Art direction: {config['art_style']}
Write all story prose and metadata in British English (UK spelling and vocabulary), such as
colour, favourite, centre and organise. Keep dialogue natural for children in the UK; do not
switch to American spellings.

STORY AND VOICE
Let the idea lead. Honour its requested subject, tone, form and visual preferences. When it
is blank, invent freely. The examples behind our craft guidance are inspiration, not a set
of genres or plot templates to choose from. Let tone, setting, structure and storytelling
form vary between books. Invent your own cast, phrases and events, rather than reproducing
a published story or a named creator's voice.

Open with something specific that invites curiosity. Give the reader a want, belief, question
or feeling to follow. Build useful connections between events, choices and consequences.
Every page contributes, whether through action, discovery, an exchange, anticipation or a
quiet moment. Not every page needs a mishap or cliffhanger. Plant what the ending will need;
finish with a satisfying action, image, surprise or callback. A good final page changes the
situation or characters in a specific, visible way and pays off something deliberately planted.
It may be funny, tender, wondrous or gently puzzling, but it must resolve the original want or
problem through a character's choice or a consequence. Do not end immediately after a character
announces a new belief, repeats the premise, says a generic thank-you or receives a convenient
magic fix. Give the reader one last earned beat: show what the choice causes, echo an earlier
detail with a fresh twist, or let the protagonist's new understanding alter what they do. If the
story is comic, make the final reversal have a concrete consequence and let the other characters
react. Then give the reader a recognisable ending beat: show the aftermath or a settling image, let the
characters share a final reaction, and land on a last sentence with satisfying read-aloud cadence. The
final page should feel unmistakably finished while leaving a pleasant echo; do not end on ordinary small
talk or halfway through an action. A book can be joyful or funny without teaching a lesson. Where a theme emerges, let the
reader experience it through events.

CAST AND NAMING
Choose names that are easy to say aloud, clearly different from one another and suited to each
character's species, personality and world. Do not default to the same familiar names or the same
small set of animals in every book. Vary species, sounds and roles when the premise allows, while
keeping the cast small and readable. Two characters can share a species only when their silhouettes,
colours or clothing make them unmistakable; avoid names with confusingly similar sounds or initials.

Choose a natural read-aloud voice for this premise. Repetition, dialogue, wordplay and rhyme
are techniques to use where they help; none is mandatory. Repetition should invite a child
to anticipate or join in, with changing context. Use precise verbs and varied sentence lengths.
Keep rhyme only when sense, spoken stress and syntax remain natural. Preserve deliberate
verse line breaks. Write plain text, with normal punctuation and dialogue, not Markdown styling.
For ages 4–7, make the surface story clear with something extra to notice on another reading.
Often 250–650 reading words in total works for our short digital books; a visual joke can be
shorter and a richer arc longer. This is pacing guidance, not a quota. Vary words per page;
a reveal may need very few. The contract allows at most 100 reading words on any one page.

EMOTIONAL CREDIBILITY
Feelings should make sense in context and appear through choices, expression and behaviour.
Give difficult feelings time and room. A small workable response and patient support can make
an ending hopeful even when disappointment remains. Let the protagonist participate in the
resolution. Where shyness or belonging matters, acceptance need not depend on becoming outgoing.
Do not force a feelings lesson into a story that is about something else.

PLAN, DRAFT AND EDIT BEFORE RETURNING
Work out the central thread, page beats, turning point and payoff; select the needed length.
Revise for read-aloud flow, emotional truth, originality and causal sense. Check who knows what,
who acts, how they arrive, and where objects are. If someone protects what they tried to destroy,
establish why their goal changed or revise the action. Establish useful tools or fantastical rules
before they solve a problem. Cut padding, needless explanation and repeated inventories.
Before returning the manuscript, test the last two pages: can you name the original want/problem,
the protagonist's decisive choice, its immediate consequence and the final image or callback? If
the final page would work unchanged after removing the story's specific setup, rewrite it. Check
that the ending is not merely a restatement of the title or premise and that each named character
has a purposeful, non-generic contribution or reaction.
Return only the finished manuscript and private production document, not reasoning or a score.

WORDS AND PICTURES
Keep reading text separate from visual instructions, measurements and design descriptions.
Each imagePrompt describes one drawable instant, usually 40–90 words: its actor, action, target
and important current state. Add a useful expression, reaction or clue that the words leave
unstated. Save a visual reveal for the right page. Deliberately false dialogue and pretend play
do not change physical reality: depict the actual character, not a second literal creature.
Narrated facts and explicit actors still need to match. Convey sounds and feelings through pose,
expression and gesture; symbolic effects belong only where the requested art direction calls for
them. Wordplay alone should not introduce floating objects or visible written sound effects.
Use Name (species and distinctive clothing/feature) once for each visible actor, then describe
their interaction. Choose a focal action and natural gaze, with essential contact, containment,
support and relative size made clear. Vary framing to serve the beat. Text is typeset separately.

CONTINUITY AND CONTRACT
Use distinct, stable character silhouettes and anatomy. Every visible person or animal belongs
to both public metadata.characters and private production.characters. charactersPresent contains
their exact names, at most three per illustration; empty means an unpopulated scene. Show each
listed actor recognisably, once. Exactly one main character. Fix species/age, face, body colours,
outfit and footwear (or bare feet/paws) in each appearance; keep these consistent across prompts.
Use numeric height_cm and consistent relative sizes, honouring the requested proportions.
Keep recurring objects' geometry, material, colour and relative size stable. Carry visible wetness,
dirt, damage, lost parts or intentional transformations through affected prompts until the story
establishes a change. Emotional expressions are poses, not new character designs.
visual_bible.style describes the chosen medium/rendering, palette its coordinated colours, and
world the environment. style_reference_prompt depicts an unpopulated environment or still life.
Make public style/main-character prompts agree with their private counterparts. The cover uses
canonical characters, suggests the premise, and includes the exact title in quotation marks with
readable, story-appropriate display lettering placed in clear space away from faces and the focal
action. Page artwork contains no lettering; reading text is typeset separately. Keep backgrounds
subordinate to the focal action.

Return exactly one JSON object containing story and production, matching the supplied schema.
Number pageNumber consecutively from 1 through the actual chosen story length.
metadata must include theme, title, ageRange, characters, bookSummary, storyPrompt,
coverImagePrompt, styleReferencePrompt and mainCharacterDescriptivePrompt. The last field must
be the full appearance of the one production character whose role is main.
metadata.ageRange is {config['age_range']}; metadata.characters is an array of name strings.
isMainCharacterPresent must agree with the named visible cast. Use stable lowercase private IDs;
cover_character_ids must refer to the private cast. No new planning, reference or review fields
belong in the public story JSON. All reading text and required metadata must be complete.
'''


def review_guide(package, config):
    counts = [{'page': p['pageNumber'], 'words': len(p['text'].split())}
              for p in package['story']['pages']]
    return {'version': 'picturebook-2', 'age_range': config['age_range'],
            'page_count': len(counts), 'words': sum(p['words'] for p in counts), 'pages': counts,
            'questions': ['Does this feel like a story your child would want to hear again?',
                          'Read it aloud: does it flow, with space to notice, wonder or join in?',
                          'Does each page earn its place, and does the final choice create a specific, earned payoff?',
                          'Do choices and feelings make sense, with pictures that support the story?',
                          'Are the names easy to say and the animal cast distinctive for this story?']}

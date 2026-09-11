# Writing picture books children want to hear again

Research and implementation notes, 11 September 2026. Initial audience: **shared reading with children aged 4–7**, as requested by Lewis. This describes listening and looking with an adult, not an independent-reading level.

The creative aim is a distinctive, enjoyable book whose words and pictures work together. An emotionally useful story, a comic misunderstanding and an imaginative adventure can all meet that aim. They should not all be forced through the same lesson-and-three-failures template.

## What was examined

This is a focused analysis of publisher descriptions, author/illustrator material, legally accessible samples and developmental research. It is **not a claim to have read every page of every named book**. Visual inspection included two interior samples of *I Am a Tiger* from Ross Collins's site, a *Room on the Broom* illustration from Axel Scheffler's site, a French-edition interior sample of *Bea's Bad Day* from Scholastic, and the *Once Upon a Giraffe* cover from Hachette. The latter's interior page sequence was not accessible. The Bloomsbury activity PDFs were indexed but their image previews failed; the Scholastic sample supplied the direct visual evidence for Bea.

Authorial craft advice, publisher positioning, experimental findings and our design interpretations are distinguished below. The research does not establish that one palette, plot formula or AI prompt produces universally preferred books. Lewis's daughter's responses are essential evidence for this product.

## Form and length correction after Lewis's feedback

The examples are inspiration, not an exhaustive menu of story types. Lewis wants a child to be able to press Generate with no configuration. The live create form now has one optional idea box and Generate. An idea can express genre, tone, art direction or other preferences in ordinary language. When blank, the writer invents freely. Rhythmic language, coherent goals, emotional credibility and visual storytelling remain internal craft guidance, not user controls. No particular refrain, moral, narrative form or art preset is mandatory.

The published editions checked mostly share a print format:

| Example / edition | Publisher's printed page count |
| --- | --- |
| [Sammy Feels Shy, ISBN 9781526673947](https://www.bloomsbury.com/uk/sammy-feels-shy-9781526673947/) | 32 |
| [Bea's Bad Day, ISBN 9781526651358](https://www.bloomsbury.com/uk/beas-bad-day-9781526651358/) | 32 |
| [I Am a Tiger, ISBN 9781509855155](https://www.panmacmillan.com.au/9781509855155/) | 32 |
| [Room on the Broom, ISBN 9781509804771](https://www.panmacmillan.com/authors/julia-donaldson/room-on-the-broom/9781509804771) | 32 |
| [Once Upon a Giraffe, ISBN 9781444975024, Hachette publisher catalogue](https://www.hachetteindia.com/stocklists/AIs%20%28New%20title%20info%29/2024/July/July%202024%20New%20Releases%20-%20Procurements%20AI%20Pack.pdf) | 32 |

This does **not** establish twelve digital story pages as the right length. Printed page counts include material outside the story and can use facing pages for one illustration. Joyce Dunbar's practitioner guide describes the common structure as 12–14 story spreads (24–28 pages). [BookTrust guide](https://www.booktrust.org.uk/resources/find-resources/joyce-dunbars-guide-to-writing-picture-books/)

Penguin's publishing guidance describes story picture books as commonly 32 pages, with roughly 500–1,000 words. This is a publishing convention, not a developmental requirement. Exact word counts for all the named books were not established from complete manuscripts in this review; do not claim the previous 12-page or per-page word settings were validated by those examples. [Penguin's advice](https://www.penguin.co.uk/about/company-articles/how-to-write-a-children-s-picture-book)

For this digital app we now use **12 illustrated story pages as the starting point**, with the local writer free to choose **8–16** when the story benefits, plus a separate cover. Lewis confirmed this preference after the initial 8–16 proposal. The writer chooses while planning the arc, not by randomising a number, padding to twelve or asking the author to choose a length. The suggested 250–650 total reading words is our short digital read-aloud target, with room for a much shorter visual joke or a richer arc; it is not a quota or a measured optimum. Pace, earned page turns and completeness matter more than filling a number. Our one-image-plus-text reading screen is not automatically equivalent to either a printed leaf or a spread.

The public JSON format is unchanged. New automatic-length attempts validate within the stored range, then against the original schema at their actual length, including sequential numbering, cast and other contracts. Approval records the chosen candidate's page count; private planning, page stages and export use that manuscript. Older fixed-length sessions remain fixed. Human review still determines readiness.

## The books: different ways to earn another reading

### Julia Donaldson and her illustrators

Donaldson's work is not one illustration style: the visual choices belong to collaborators including Axel Scheffler, Lydia Monks and others. For this review, *Room on the Broom* supplies a concrete example. Its accumulation of passengers creates a visible pattern and a physical consequence; the changing group gives an illustrator a way to stage anticipation and reactions. In the sample examined, the flying witch and cat have distinct silhouettes against storm clouds, while the birds' expressions add a secondary response. Atmosphere can be dark without making the characters hard to read. These observations come from [Scheffler's own book page and sample artwork](https://axelscheffler.com/books-with-julia-donaldson/room-on-the-broom).

Donaldson's own teaching treats good verse as structured spoken rhythm, with something like a song's recurring element. She stresses natural scanning, cutting padding and having another person read a draft aloud. Patterned prose is a sound alternative when rhyme becomes strained. This is practitioner advice, not a developmental experiment. [Donaldson's BBC Maestro notes, lessons on repetition and rhyme](https://assets.cdn.bbcmaestro.com/julia-donaldson-writings-childrens-picture-books-course-notes-v2.pdf)

**Our application:** offer a refrain without requiring a rhyming book; change its meaning or context at the ending. Plant details that can earn a payoff. Preserve a distinct visual cast and let reaction shots contribute. Invent new situations, language and designs rather than asking for an imitation of a named creator.

### Bea's Bad Day — Tom Percival

The publisher presents a recognisable emotional situation: anticipation of a birthday meets disruptive weather and disappointment. It positions the story as an opening for conversation about expectations and flexibility. That is more specific than a generic instruction to be happy or resilient. [Bloomsbury's description](https://www.bloomsbury.com/uk/beas-bad-day-9781526651358/)

In the interior sample examined, clenched fists, closed eyes and the dog's concerned gaze carry the emotion. Bea remains strongly coloured while much of the room is grey; radiating divisions make the feeling of things falling apart visible. That is a deliberate expressive device, not evidence that the room literally shatters. [Scholastic's French-edition page and sample](https://www.scholastic.ca/editions/nos-livres/livre/la-journe-gche-de-ba-9781039709690)

**Our application:** give a feeling a concrete cause, time and a believable response. Permit help while preserving the protagonist's choices. The original disappointment can remain even when something becomes manageable. Use posture, gaze and focal colour before introducing elaborate symbolic effects. Our current renderer should not invent cracks, objects or damaged anatomy to literalise an emotional metaphor.

### Sammy Feels Shy — Tom Percival, Big Bright Feelings

Lewis identified this as probably his daughter's favourite in the series, so it is a particularly relevant editorial reference. Bloomsbury's description links the discomfort to specific social situations and being watched or labelled; the increasing pinkness externalises a feeling that can be hard to describe. This analysis uses the publisher's description and teaching extracts, not a complete reading of the book. [Bloomsbury's book page](https://www.bloomsbury.com/uk/sammy-feels-shy-9781526673947/)

The publisher's teaching pack connects expression and posture with emotion, asks what Lily does to help, and proposes low-pressure invitations, kindness and time to watch before joining. It supplies concrete ways to discuss the relationship between a feeling, its context and supportive behaviour. This is teaching guidance, not evidence that reading the book treats social anxiety. [Bloomsbury's resource pack, especially pages 6 and 9–10](https://www.bloomsbury.com/media/eidgg224/sfs_resourcepack_v4_.pdf)

**Our application:** for a shyness or belonging premise, a hopeful ending can be a small, chosen act of participation. Do not make acceptance depend on becoming outgoing. Let another character help without taking over. Show emotional change through readable posture, expression, gaze and interpersonal distance. These are our editorial choices informed by the material; we do not assume why Lewis's daughter prefers the book or reuse Sammy's pink transformation as a template.

### I Am a Tiger — Karl Newson and Ross Collins

The comedy relies on the reader seeing a mouse while the character argues otherwise. The arrival of a real tiger increases the mismatch; confident reinterpretation sustains the game. The child has useful knowledge that the characters do not seem to apply. This reading is supported by the [publisher's synopsis](https://www.panmacmillan.com/authors/karl-newson/i-am-a-tiger/9781509855155) and [BookTrust's discussion of the reader's inside knowledge](https://www.booktrust.org.uk/book-recommendations/bookfinder/i-am-a-tiger/).

In Collins's sampled spreads, uncluttered colour fields make contrasting body sizes and incredulous faces readable. The small protagonist occupies very little physical space but draws attention through stance and the others' gaze. The image is part of the joke; a literal illustration of the claim would destroy it. [Collins's book page and interior samples](https://www.rosscollins.net/picturebooks/i-am-a-tiger.php)

**Our application:** separate a character's claim from the physical truth. A pretend monster need not become a monster or summon an extra one. Let the child discover the mismatch, vary the reactions, then deliver a reversal or callback. A funny book need not end in a moral correction.

### Once Upon a Giraffe — Ken Wilson-Max and Tumi K. Steyn

Hachette describes this as an animal origin story inspired by traditional stories from Africa. The question concerns the giraffe's neck, with reaching for inaccessible leaves providing the imaginative mechanism. Curiosity supplies the reason to keep listening. The inspected cover uses a strong animal silhouette, graphic pattern, a large sun shape and a coordinated contrasting palette. These are observations of the cover, not claims about all interior pages. Steyn is the credited illustrator. [Hachette's book page](https://www.hachette.co.uk/titles/ken-wilson-max-2/african-stories-once-upon-a-giraffe/9781444975024/)

**Our application:** a separate imaginative “why?” mode, with a new question and a clear invented cause. Make fantasy recognisable as fantasy rather than presenting it as natural history. Do not label an invented AI story as an authentic African folktale, or treat a continent's many traditions as one generic visual style. The transferable craft is curiosity and an earned visual answer, not borrowed cultural authority.

## What developmental research supports—and what it does not

| Finding and source | Practical implication | Boundary of the evidence |
| --- | --- | --- |
| Three-year-olds retained novel word–object associations better after repeated readings of the same stories than after different stories containing the same target words. [Horst, Parsons & Bryan, 2011](https://pubmed.ncbi.nlm.nih.gov/21713179/) | Make rereading rewarding: a recognisable pattern, a clue worth finding again and concrete language. | This tests contextual repetition across readings. It does not prove that repeating a catchphrase on every page improves learning or enjoyment. |
| Preschoolers used goals and causal structure when recalling supported narratives. [Wenner, 2004](https://pubmed.ncbi.nlm.nih.gov/15250184/) | Keep the protagonist's want, attempts and resulting changes connected. Establish why a goal changes. | Comprehension/recall evidence does not prescribe a single plot shape. |
| Children preferred causally informative versions of expository storybooks in a controlled study. [Shavlik, Bauer & Booth, 2020](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2020.00666/full) | A meaningful “why?” and a satisfying answer are promising sources of interest. | Expository-book preference is not a direct test of invented animal fables. Applying it to our wonder mode is an editorial inference. |
| In word-learning experiments with 3.5-year-olds, two competing illustrations made referent identification harder; a guiding gesture helped. [Flack & Horst, 2018](https://onlinelibrary.wiley.com/doi/full/10.1002/icd.2047) | Give each frame a clear focus. Use gaze, gesture and contrast to direct attention to the relevant object/action. | It does not establish that all richly illustrated books are bad, nor measure a universal ideal number of objects for 4–7-year-olds. |
| A small preschool study found gains in emotion comprehension after repeated shared reading of specially designed picture books. [LaForge et al., 2018](https://cje-rce.ca/index.php/cje-rce/article/view/3181) | Clear emotional situations and opportunities to discuss them are worthwhile. | Eighteen participants and a specific intervention: no basis for promising therapeutic effects from generated stories. |
| A cluster-randomized dialogic-reading intervention supported narrative comprehension and vocabulary. [2020 study](https://www.sciencedirect.com/science/article/pii/S0885200619301395) | Leave room for a child to predict, notice, explain or respond; the adult's conversation matters. | Intervention effects are not proof that putting quiz questions in a manuscript is beneficial. Our questions belong in adult review guidance, not the reading text. |
| Picture-book learning and transfer depend on developing symbolic understanding and book features. [Strouse, Nyhout & Ganea, 2018 review](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2018.00050/full) | Distinguish a story's pretend rules from real-world explanations. Make an intended connection to everyday experience understandable. | Enjoyment, learning a word and transferring a moral are different outcomes. None is a proxy for all the others. |
| One experiment with 4–6-year-olds found an increase in altruistic giving after a human sharing story, but not the corresponding anthropomorphic-animal version. [Larsen, Lee & Ganea, 2018](https://pubmed.ncbi.nlm.nih.gov/28766863/) | For a concrete everyday lesson, human situations are worth considering; do not assume animal stories teach it better. | One sharing task does not justify banning animals or claiming children learn nothing from them. Animal comedy and imaginative enjoyment remain valid aims. |

Early humour research documents diverse forms of play, including unexpected actions and mislabelling, rather than a single universal joke. The Early Humor Survey covers children only up to 47 months and has limitations in agreement with laboratory measures; it is useful background, not a calibrated prescription for our 4–7 audience. [Hoicka et al., published online 2021](https://link.springer.com/article/10.3758/s13428-021-01704-4)

The design interpretation is to make humour understandable from a familiar expectation plus a visible violation, and then test whether the child finds it funny. Avoid conflating laughing, comprehending and remembering.

## Craft principles (initial implementation)

The implementation is an editorial synthesis of these sources and the failures Lewis has already identified. The controls described in this initial version were subsequently replaced by the simple form above; saved version-1 books keep their instructions. The numeric word ranges below are our pacing defaults, not developmental thresholds.

- **Audience:** ages 4–7 by default, with a clear surface story and an optional second layer of humour, inference or emotion. Usually 20–55 words per page; an effective reveal can be much shorter. Retain the existing contract's hard ceiling of 100 words per page.
- **Specific opening:** an appealing want, belief or worry appears promptly. Avoid generic introductions followed by unrelated tasks.
- **Consequences:** an attempt should affect what happens next. A three-failure sequence is available, not mandatory. Quiet pages and discoveries can advance a story too.
- **Payoff:** establish important information before it matters. A last-page callback or image can supply satisfaction without a paragraph explaining a lesson.
- **Language:** patterned prose, natural prose and rhyming verse are separate options. Rhyme requires a human read aloud; valid JSON cannot demonstrate good metre.
- **Emotion:** show a cause and a response the child can recognise. Avoid shame, automatic cheerfulness and instantaneous cures. Let support and agency coexist. In shyness or belonging stories, acceptance must not require becoming outgoing.
- **Picture contribution:** preserve explicit narrated facts and named actions. Add a useful reaction or clue. Keep deliberately false character dialogue distinct from the physical scene.
- **Visual clarity:** one focal instant; readable expression, gesture and gaze; framing changes that serve the story. Decorative detail remains secondary. Keep approved identities, prop geometry and current states consistent.
- **Variety:** three material-based art directions—warm painted texture, bold graphic colour and layered paper shapes—are independent of story flavour. A custom art direction replaces the preset rather than accumulating conflicting styles.
- **Originality:** no published plots, signature refrains or named-author imitation in the generator templates. The book examples inform our craft analysis, not reusable story content.

The previous bubble story's goal reversal is specifically addressed in the writer's general causal check: when a character starts protecting something they wanted to destroy, establish why or revise the action. Likewise the pouring actor must match explicit prose, whereas an unstated pose or optional flourish should not become a blocker.

## Initial implementation and version compatibility

`story_craft.py` supplies versioned writing guidance, validated creative choices and human review questions. New assisted sessions store the choices and version. Existing sessions without that version keep their original writer/planner instructions and saved configs; they are not silently rewritten halfway through a book.

The local Gemma request still uses reasoning and the existing bounded recovery for transport/JSON failures. Within that one creative request, the prompt asks the writer to plan, draft and edit before returning the manuscript. **This is not an independently verified editorial pass.** No new autonomous score, repair loop or approval gate is introduced. The human remains the editor.

`story-guide.json` is a private sidecar containing actual word counts, selected approach and questions to help the adult review. It contains no claim that the story passed a psychological or literary assessment. The interface also derives a fresh guide for a human-revised story. The public story/production envelope and `contracts/story.schema.json` remain unchanged. Nothing new is added to the reader app's imported story.

The private illustration planner gets the same distinction between physical fact, pretend claims, emotion and reveal timing for new sessions. Image model, sampler, Turbo settings, reference packing and approval sequence are unchanged by this work.

## How we should judge progress

Use Lewis's real reads as the test, with different flavours and premises. Keep the first draft, feedback and revised candidate so we can inspect what actually improved. Useful observations include where the listener joins in, predicts, laughs, asks a question, loses interest or requests the book again. These are observations, not a score to optimise at the expense of the child.

For the adult: read several pages cold; ask whether each important choice makes sense; check the ending's setup; inspect the correspondence of words and pictures. For rhyme, mark the lines that require an unnatural stress. For feelings, check whether the child has room to feel before being told what to do. For comedy, check that an image correction would not accidentally remove the joke.

Before claiming the generator reliably produces excellent books, we need multiple complete human-reviewed examples. Structural tests protect the contract and saved work. Text samples can show how the new guidance behaves. Neither proves that the final illustrations or audience response are already good enough.

## Verification of the initial craft changes

328 automated tests passed, including new-session preferences, unchanged older configs, the exact public schema, private review sidecars, human revisions and approval boundaries. Desktop/mobile browser checks verified the choices are submitted correctly, the selected candidate gets its own guide, and existing book review still works. The backend was reloaded while idle, with all four pre-existing assisted session files unchanged across the restart. A separate starter workflow copy was validated by the official local MCP with no errors or warnings.

One eight-page text-only draft, *The Glip-Glop-Bloop*, completed in one local Gemma 4 request (51.23 seconds), with reasoning enabled, 205 reading words and no structural repair. It stopped at human review. Its supportive exchange and repeating anticipation are promising, but its first illustration brief adds unrequested abstract bubbles and some sound effects contain Markdown emphasis. The draft has not been approved; no artwork was generated. Those are recorded editorial limitations, not silently accepted fixes. This single example is not a before/after literary benchmark.

Exact request, response, reasoning, seed, graph, validation and candidate remain in `output/books/book-assisted-20260911104330-d81a8f131e/`. The verification session is hidden from the normal library to keep the user's books uncluttered, but can be opened directly. Screenshots, test log, readable sample and receipts are in `.local/story-craft-20260911/`.


## Simple-form and flexible-length verification — 2026-09-11

The create page now submits only an optional idea. New sessions persist private picturebook-2 settings: ages 4–7, automatic 8–16 pages, twelve as a soft planning target. Existing fixed-length books keep their configs. All 335 unit/API tests pass; seven focused length tests pass after the target change. Tests cover differently sized attempts, manual revisions, recovery without new inference, approval of an earlier length, planning and complete fixture export. Desktop/mobile browser checks pass for blank input, free-text preferences, error/retry, actual candidate counts and layout. Both idle backend reloads preserved all saved session bytes (five then six sessions). Public schema is byte-identical.

One blank-input local Gemma sample, Oona and the Echo-Jar, chose fourteen pages/372 words in 70.02 seconds, one complete response. It paused at story review with no approvals/images. It was submitted before Lewis added twelve as the soft starting point; its exact saved request remains unchanged. This verifies variable-length plumbing, not that the final preference always yields good pacing. Editorial gaps are recorded in .local/simple-creator-20260911/sample-review.md, including an unestablished second jar and an inconsistent description of the quiet space. No automatic quality claim is made.

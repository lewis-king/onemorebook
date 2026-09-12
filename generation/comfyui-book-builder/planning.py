"""A private narrative outline before prose and production constraints are combined."""
from .story import object_schema
from .reasoning import story_reasoning_options

DEFAULT_WRITER_MODEL = "gemma4:31b"


def outline_schema(page_count):
    text = {"type": "string", "minLength": 1}
    return object_schema({
        "title": text, "opening_hook": text, "main_character_want": text, "concrete_problem": text,
        "world_rule": text, "earned_resolution": text, "delight_or_surprise": text,
        "beats": {"type": "array", "minItems": page_count, "maxItems": page_count,
                  "items": object_schema({"page": {"type": "integer"}, "event": text,
                    "character_choice": text, "what_changes": text, "drawable_moment": text,
                    "page_turn_reason": text})}})


def outline_prompt(config):
    return f"""You are developing an excellent original picture book for children aged {config['age_range']}.
Premise and constraints: {config['story_idea'] or 'Invent an original, playful child-friendly adventure.'}
Exactly {config['page_count']} pages and at most {config['max_characters']} named characters.
Variation seed: {config['seed']}.

Plan the STORY before writing prose or illustration specifications. Return a private beat outline.
Give the protagonist a concrete want, a visually clear problem, and actions with consequences.
Open with an intriguing event, not a weather report or a generic description of a lovely village.
Use a small number of purposeful failed attempts, a discovery or reversal, and a resolution
earned by something the characters DO. Include a distinctive, child-comprehensible visual joke,
surprise or recurring detail. Supporting characters contribute different useful ideas or actions.
Warmth comes from behaviour and dialogue; never finish by explaining the moral to the reader.
If magic exists, establish a simple rule early and use it consistently. 'They were kind, so the
light magically grew brighter' is not an earned solution unless a clear rule and action support it.
Make each page change the situation. Vary visual action, framing and expressions. A string of
characters standing in the same garden looking at a glow is not enough for a whole book.
Leave the child wanting to turn each page: an unanswered question, comic consequence,
promising discovery or small suspense. The final page supplies a satisfying payoff/callback.
For only two or three pages, compress the arc instead of inventing needless intermediate steps.
Use physical events that a child can follow. Objects do not acquire new powers merely because
the plot needs a solution. Keep track of where important objects are, what each character knows,
and why the next action follows. The resolution must solve the ORIGINAL problem, not abandon it.
For a mystery or surprise reveal, trace the implicated characters backwards through the plot.
If someone caused the problem then helped investigate it, explain their pretence or confusion.
Establish important departures, return trips or concealed actions needed to understand the ending.
A final callback must refer to something actually established earlier. The last beat must show a
specific consequence of the protagonist's choice, so it cannot be replaced by “and then everyone
was happy”, a repeated premise, a new identity announcement, a generic thank-you or an unrelated
accident. Avoid thank-you messages written before the action they thank someone for, inexplicable
forgotten items, or an unrelated accident that fixes everything. Each supporting character
contributes to the solution. Leave room for the prose writer to choose names that are easy to say
aloud, clearly distinct and suited to the species and world; vary the cast when the premise allows.
The cast limit includes unnamed insects or animals who act in a scene; do not introduce a
last-minute beetle, bird or stranger beyond the requested cast. Use the established team.
Plan readable illustrations with a small, visually distinctive cast. Unless miniature characters
are explicitly requested, prefer child-sized or knee-high anthropomorphic animal friends whose
faces and outfits remain readable alongside the protagonist. Avoid unnecessary extreme size gaps.
Keep each character's identifying clothing fixed. If a cloth, hat or scarf is needed as a
tool, introduce it as a separate carried prop, not an identifying garment that must be worn.
Do not include character measurements, camera jargon or moral abstractions in the prose plan.
Number beats 1 through {config['page_count']}. Keep each field concise and specific.
"""


def review_outline(outline, config, generate=None):
    import json
    from .quality import json_model, review_schema
    generate = generate or json_model
    checks = ('causal_plot', 'clear_original_problem', 'character_agency', 'earned_resolution',
              'continuity', 'engaging_page_turns', 'age_appropriate')
    report = generate(config['ollama_url'], config['review_model'],
        "Review this picture-book outline for story-blocking defects before prose or art. Read the "
        "whole plot: what the protagonist wants, what the friends try and learn, and how their final "
        "action resolves the original problem. Reject a contradicted established rule, an unexplained "
        "essential change of object or knowledge, an unearned accidental solution, or a missing ending. "
        "Evaluate each supporting character's contribution across the WHOLE story; a comic failed "
        "attempt is allowed even if that one attempt teaches nothing. Children may try silly ideas. "
        "Accept consistent fantasy, comic exaggeration and ordinary unstated transitions. Missing "
        "engineering detail is not proof of impossible action. Distinguish an actual contradiction "
        "from a plausible action the final prose or illustration can clarify. Do not invent spatial "
        "constraints, restrict a tool beyond the stated facts, or silently expand a world rule. "
        "For a rule violation, quote the exact rule and the exact conflicting event, then explain "
        "why the reader cannot reconcile them. Require a concrete final consequence and a callback or "
        "fresh image rooted in an earlier detail; a generic happy ending or premise repetition is a "
        "blocking defect. Read named surfaces literally: a rule about leaves "
        "does not automatically cover a trunk. Prioritize the reader's understanding of cause, "
        "motivation and consequence. Do not reject minor omissions or an opportunity to improve a joke. "
        "Return an empty issues list when there is no story-blocking defect. If you report a blocking "
        "issue, set its corresponding check false and cite the beats; do not set every check true "
        "while appending an optional editorial preference to issues. Repair suggestions must obey "
        "the same established facts and solve the actual problem. "
        f"Ages {config['age_range']}; premise: {config['story_idea']}.\n" + json.dumps(outline),
        review_schema(checks), **story_reasoning_options(config['review_model']))
    return {'accepted': all(report['checks'].values()) and not report['uncertain'] and not report['issues'],
            'review': report}


def outline_retry_prompt(config, previous=None, feedback='', *, reset=False):
    """Avoid anchoring every retry to the same rejected resolution."""
    import json
    base = outline_prompt(config)
    if previous is None:
        return base + ('\nCorrect these structural defects: ' + feedback if feedback else '')
    if reset:
        abandoned = {key: previous.get(key) for key in
                     ('concrete_problem', 'world_rule', 'earned_resolution')}
        return (base + '\nThe earlier approach exhausted its useful revisions. Develop a substantially '
                'different causal sequence and resolution instead of patching that mechanism again. '
                'For an open premise, invent a different adventure. Preserve every explicit user premise '
                'constraint, age, page count and cast limit. Use a few clear, drawable interactions; '
                'do not add a complicated new device or physical rule to rescue an earlier device. '
                'This is a new plot candidate and must still pass the same editor.\n'
                'Abandoned approach (do not reuse its mechanism): ' + json.dumps(abandoned) +
                '\nPrevious objections, which may themselves be fallible: ' + feedback)
    return (base + "\nRevise the previous outline to fix the editor's specific story defects. "
            'Check the proposed repair against the whole plot; do not copy a repair suggestion that '
            'introduces a new contradiction. Prefer a simple action with a clear result. Keep successful '
            'events and user constraints. Return the complete outline.\nEditor: ' + feedback +
            '\nPrevious outline: ' + json.dumps(previous, ensure_ascii=False))

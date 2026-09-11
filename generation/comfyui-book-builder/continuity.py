"""Focused, evidence-first narrative continuity check before book production."""
import json


from .story import object_schema


def audit_request(story):
    text = {'type': 'string', 'minLength': 1}
    timeline = {'type': 'array', 'minItems': len(story['pages']), 'maxItems': len(story['pages']), 'items': object_schema({
            'pageNumber': {'type': 'integer', 'enum': [p['pageNumber'] for p in story['pages']]},
            'events_and_locations': text,
            'knowledge_and_object_changes': text,
        })}
    schema = object_schema({
        'facts': object_schema({
            'ending_cause': text,
            'earlier_actions_of_revealed_participants': text,
            'required_missing_transitions': text,
            'visible_changed_objects_or_clothing': text,
            'timeline': timeline,
        }),
        'issues': {'type': 'array', 'items': object_schema({
            'pages': {'type': 'array', 'minItems': 1, 'items': {'type': 'integer'}},
            'kind': {'type': 'string', 'enum': ['sequence', 'knowledge', 'cause_and_effect', 'visible_state']},
            'evidence': text, 'repair_direction': text,
        })},
        'uncertain': {'type': 'boolean'},
        'verdict': {'type': 'string', 'enum': ['pass', 'revise']},
    })
    prompt = '''Audit the supplied children's story for story-state continuity only. Do not rewrite it.
First establish the facts before writing an issues list or verdict. Record a concise
page-by-page timeline based on the actual prose. Track the locations,
knowledge and actions of important participants and what happens to important objects.
Then identify concrete contradictions or missing causal links a young reader needs to follow
the resolution. Your verdict must be based on the text, not on a plausible extra story you invent.

Accept ordinary between-page movement, natural ellipsis, playful exaggeration and talking
animals. A character may leave a scene or reappear if that movement is evident from the
sequence. Do not demand a sentence for every footstep. Characters mentioned in prose can
be outside an illustration's frame; charactersPresent is not a complete attendance register.
Surprises and mistaken beliefs are welcome. A reveal must still be compatible with earlier
actions and knowledge, or explain the missing transition/deception. Do not invent an unstated
lie, return trip, second accident, transfer of an important object or new magical rule to
justify a contradiction. Distinguish what a character believes from what the narrator states.

In ending_cause, identify the actual cause or solution revealed at the end and when it happened.
In earlier_actions_of_revealed_participants, trace what anyone implicated in that explanation
was doing earlier and what they must already have known. If a character secretly caused a
mystery, then helped investigate it, does the text explain their pretence or confusion? If they
were walking with the investigators but are then discovered elsewhere with the missing item,
does the text establish how that change of role/location occurred? Report a required missing
transition when a young reader must supply an untold concealment, return trip or second event
to understand the reveal. A mystery should be surprising but intelligible, not merely possible
after an adult invents the connecting events. If there is no such reveal, say this is not applicable.

Check the imagePrompt only for important visible story states: a missing part, stain, broken
object or essential carried clue must be included when that part is visible. Each illustration
starts from clean canonical references, so it cannot infer those changes from a prior image.
A changed item outside the chosen frame does not need to be listed. In
visible_changed_objects_or_clothing, explicitly compare each crucial changed part against
the prompts that show it. A character looking at
an unchanged reference costume does not communicate a missing part. Do not reject harmless
decorative details or ask for identical wording across prose and imagePrompt.

Report the relevant page numbers, the actual conflicting facts, and a concise repair direction
for each substantive issue. Return pass with no issues when the sequence is sound; do not
manufacture objections to satisfy a quota. Return one timeline entry for every supplied page.
'''
    return prompt + '\n' + json.dumps({'pages': story['pages']}, ensure_ascii=False), schema


def validate_audit(result, story):
    expected = sorted(p['pageNumber'] for p in story['pages'])
    if sorted(p['pageNumber'] for p in result['facts']['timeline']) != expected:
        raise ValueError('Continuity audit omitted or duplicated a page.')
    if any(set(issue['pages']) - set(expected) for issue in result['issues']):
        raise ValueError('Continuity audit cites an unknown page.')
    return result['verdict'] == 'pass' and not result['uncertain'] and not result['issues']


def apply_audit(report, result, story):
    """A failed timeline vetoes publication; a pass never clears another defect."""
    if validate_audit(result, story):
        return
    report['checks']['continuity'] = False
    report['uncertain'] = report.get('uncertain', False) or result['uncertain']
    for issue in result['issues']:
        report['issues'].append(f"Pages {issue['pages']}: {issue['evidence']} {issue['repair_direction']}")
        if issue['kind'] == 'visible_state':
            report['checks']['drawable_scenes'] = False
    if not result['issues']:
        report['issues'].append('Continuity audit requires revision or remains uncertain: '
                               + result['facts']['required_missing_transitions'])

"""Scene relationships for the planner and human-requested prompt revisions."""
import json

VERSION = 2
SCENE_GUIDANCE = '''The approved page prose determines who acts, the action and target, and the story
state. Correct illustration-brief details that contradict it; never change story facts to fit an image.
Keep each accessory with its wearer and its specific attachment point; describe it
once using the approved current design, rather than repeating a loose accessory description.
For a visible part of an object, name its parent and where it belongs. Put light, colour and other
effects on the intended surface. Preserve contact, containment, support, relative size and current
attachments. Keep those relationships until the story explicitly changes them; preserve intentional
magic or movement when the story calls for it. Check the pictured target against the page's prose.
An assembled or changed prop keeps its established state on later pages even when the prose names
only one part. Use its state reference as one object and describe the relevant part's position within
it. Earlier story events establish context; depict only this page's moment, not a montage of events.
'''

PROMPT_SCHEMA = {'type': 'object', 'properties': {'prompt': {'type': 'string', 'minLength': 1,
                 'maxLength': 5000}}, 'required': ['prompt'], 'additionalProperties': False}


def revision_request(current, intent, prompt, references, stages, *, preparing=False):
    editing = intent.get('mode') == 'edit'
    task = ('Write ONE concise FLUX.2 image-edit instruction. Identify the edited subject by its '
            'species or visible distinguishing feature as well as its name, with explicit accessory '
            'ownership. Preserve unaffected interactions, composition and style. ' if editing else
            'Rewrite ONE concise FLUX.2 scene prompt to address human feedback. Describe the desired '
            'result positively. Preserve the named actors, their actions and the intended cast count. '
            'Bind each actor to its species and distinguishing clothing once, beside its action. ')
    if preparing:
        task = ('Prepare ONE concise final FLUX.2 scene prompt from the approved page prose, '
                'illustration brief and reference designs. Reconcile contradictions using the page prose. '
                'Preserve compatible creative choices. Bind each actor to its species and distinguishing '
                'clothing once, beside its action, and preserve the intended cast count. ')
    photo_inputs = [f'Image {i+1}' for i, ref in enumerate(references)
                    if ref['label'].startswith('The real photograph')]
    if photo_inputs:
        task += (', '.join(photo_inputs) + (' is' if len(photo_inputs) == 1 else ' are') +
                 ' the reader\'s real photograph for this page: recreate it faithfully — same people, '
                 'poses, key objects and setting — in this storybook style, never as a photograph. ')
    # These are design notes, not additional images. In an edit, only the selected
    # illustration is supplied. Never claim that approved portraits are Image 2+.
    notes = [{'stage': sid, 'kind': stages[sid]['kind'], 'name': stages[sid]['title'],
              'design_brief': stages[sid]['brief']} for sid in current['references']]
    context = {'page_text': current.get('text', ''),
               'earlier_story_events': [{'page':s['page'],'text':s['text']} for s in stages.values()
                                        if s.get('page',0)>0 and s['page']<current.get('page',0)],
               'image_inputs': [{'image': i+1, 'role': ref['label']}
                                for i, ref in enumerate(references)],
               'reference_design_notes': notes}
    return (task + SCENE_GUIDANCE +
            'The image_inputs list is the complete set of supplied images. Reference design notes '
            'are text context only. Refer only to those actual image numbers. '
            'Use human feedback to correct departures from the approved design; preserve successful '
            'details. Return JSON with prompt only. Keep the final instruction concise; do not copy '
            'all these notes, append negative lists, repeat cast descriptions or add commentary. '
            '\nOriginal prompt: ' + prompt + '\nHuman feedback: ' + intent['feedback'] +
            '\nScene context JSON:\n' + json.dumps(context, ensure_ascii=False))

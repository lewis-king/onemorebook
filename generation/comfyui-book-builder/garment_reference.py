"""Describe a detached garment without feeding its former wearer into the scene.

The approved worn portrait remains the visual QA reference. Rendering uses a
separately checked garment-only description, never a falsely labelled crop.
"""
import hashlib
import json


def garment_design(project, prop, generate=None):
    from .quality import json_model
    from .state_assets import prop_reference
    from .state_ledger import obj
    from .storage import checked_root, write_json
    from .story import digest
    generate = generate or json_model
    source, _ = prop_reference(project, prop)
    change = next(c for c in project['art_plan']['ledger']['changes'] if c['id'] == prop['source_change_id'])
    policy = 2 if project['render_settings'].get('garment_reference_policy',0)>=2 else 1
    subject = change['after_state']
    if policy>=2:
        from .state_ledger import is_addition
        if not is_addition(change):
            # after_state describes the now-bare wearer, not the removed item.
            subject = change['reference_edit']['target_query']
    context = {'source_sha256':hashlib.sha256(source).hexdigest(), 'change':change,
               'prop':prop, 'model':project['render_settings']['review_model'], 'policy':policy}
    directory = checked_root(project)/'visual-state'/'garment-designs'/digest(context)[:20]
    schema = obj({'description':{'type':'string','minLength':1},
                  'uncertain':{'type':'boolean'}, 'issues':{'type':'array','items':{'type':'string'}}})
    prompt = ('Describe ONLY the named garment visible on this approved character portrait, so an image '
        'model can draw that SAME garment as a detached object. Specify its material, colour, overall '
        'construction, shape and distinctive visible pattern/details. Exclude the wearer, body, face, '
        'skin/fur/quills, pose and background. Do not make the object anthropomorphic. Clothing may unfold '
        'or untie when removed; describe its design without freezing its worn neck knot or body posture. '
        'Do not invent a hidden side or unseen ornament. Keep the description under120words.\n'
        +json.dumps({'garment_state':subject,'detached_object':prop['description']}))
    if policy>=2:
        prompt = prompt.replace('approved character portrait','approved source image')
        prompt += ('\nDescribe the fabric/item as actually visible in the source. Any new story marks '
                   'such as honey, mud or paint are supplied separately by the scene state; do not invent '
                   'them on the original source design. The crop may include body pixels for context: '
                   'exclude those entirely from the detached object description.')
    for attempt in (1,2):
        draft_path=directory/f'description-{attempt}.json'
        if draft_path.exists():
            draft=json.loads(draft_path.read_text())
        else:
            draft=generate(project['config']['ollama_url'],context['model'],prompt,schema,[source])
            write_json(draft_path,draft)
        check_schema=obj({'faithful':{'type':'boolean'},'garment_only':{'type':'boolean'},
            'uncertain':{'type':'boolean'},'evidence':{'type':'string','minLength':1},
            'issues':{'type':'array','items':{'type':'string'}}})
        review_path=directory/f'review-{attempt}.json'
        if review_path.exists():
            review=json.loads(review_path.read_text())
        else:
            review=generate(project['config']['ollama_url'],context['model'],
                'Compare this garment-only design description against the actual named garment in the '
                'approved portrait. It must preserve the visible material, colour and distinctive design '
                'without inventing details or including the wearer, face, body, fur or background as part '
                'of the detached object. Flexible fabric may drape differently and may naturally untie '
                'after removal; pose-dependent folds and worn fastening position are not new design. '
                'Reject consequential discrepancies or ambiguity, not harmless wording.\n'
                +json.dumps({'garment':subject,'description':draft['description']}),
                check_schema,[source])
            write_json(review_path,review)
        accepted=(not draft['uncertain'] and not draft['issues'] and review['faithful']
                  and review['garment_only'] and not review['uncertain'] and not review['issues'])
        if accepted:
            write_json(directory/'provenance.json',{**context,'description':draft['description'],
                'attempt':attempt,'review':review,'reference_role':'checked garment description; not a measured crop'})
            return draft['description']
        prompt+='\nCorrect the prior description using these observed discrepancies: '+json.dumps({'draft':draft,'review':review})
    raise ValueError('Detached garment design could not be verified; saved evidence: '+str(directory))

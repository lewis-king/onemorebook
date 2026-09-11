"""Bind scene verbs to short, checked descriptions of the current visible cast."""
import json
import re


def context(project, spec):
    from .quality import expected_scene
    from .state_ledger import scene_character_description, active_changes
    ids, _, _ = expected_scene(project, spec)
    scene = project['book']['cover'] if spec['name'] == 'cover.png' else next(
        p for p in project['book']['pages'] if spec['name'] == f"pages/page-{p['page_number']:03d}.png")
    return scene, [{'id': c['id'], 'name': c['name'], 'baseline': c['appearance'],
        'current': scene_character_description(project, scene, c, current=True),
        'active_changes': active_changes(project, scene, c['id'])}
        for c in project['book']['characters'] if c['id'] in ids]


def labels(project, spec, generate=None):
    from .quality import json_model
    from .story import digest, object_schema as obj
    from .storage import checked_root, write_json
    generate = generate or json_model
    _, cast = context(project, spec)
    if not cast:
        return {}
    model = project['render_settings']['review_model']
    key = digest([1, cast, model])
    root = checked_root(project) / 'visual-state' / 'actor-labels' / key[:20]
    saved = root / 'approved.json'
    if saved.exists():
        value = json.loads(saved.read_text())
        if value['source_hash'] != key:
            raise ValueError('Actor-label source mismatch.')
        return value['labels']
    ids = [c['id'] for c in cast]
    schema = obj({'labels': obj({cid: {'type': 'string', 'minLength': 3, 'maxLength': 110} for cid in ids}),
                  'uncertain': {'type': 'boolean'}, 'issues': {'type': 'array', 'items': {'type': 'string'}}})
    prompt = ('Produce a SHORT visual qualifier to put beside each character name in its scene ACTION. '
        'Use species (or human age/hair descriptor) plus one CURRENT distinctive colour/clothing feature: '
        'e.g. "the brown monkey in the teal vest". Same-species characters need visible distinguishing '
        'features. Use only grounded appearance in the supplied current canon, not personality, actions, '
        'names or invented details. Current appearance/active changes override baseline clothes: a removed '
        'scarf must NOT be used as a worn identifying label. Unchanged body traits remain valid. Keep '
        'each qualifier ideally under12words; no parentheses, names, height claims or nested sentences. '
        'Labels must distinguish the visible cast without rewriting any story.\n' + json.dumps(cast))
    audit_schema = obj({'grounded': {'type': 'boolean'}, 'current_state_correct': {'type': 'boolean'},
        'distinguishing': {'type': 'boolean'}, 'uncertain': {'type': 'boolean'},
        'issues': {'type': 'array', 'items': {'type': 'string'}}, 'evidence': {'type': 'string'}})
    for attempt in (1, 2):
        request = root / f'request-{attempt}.json'
        write_json(request, {'prompt': prompt, 'schema': schema, 'model': model})
        draft_path = root / f'labels-{attempt}.json'
        draft = json.loads(draft_path.read_text()) if draft_path.exists() else generate(
            project['config']['ollama_url'], model, prompt, schema)
        write_json(draft_path, draft)
        if any(re.search(r'[()\n\r]|["{}]', label) for label in draft['labels'].values()):
            prompt += '\nUse a plain short noun phrase without brackets, quotes or newlines.'
            continue
        audit_path = root / f'review-{attempt}.json'
        review = json.loads(audit_path.read_text()) if audit_path.exists() else generate(
            project['config']['ollama_url'], model,
            'Verify these short actor labels against the supplied immutable/current descriptions. '
            'Every trait must belong to that actor and be CURRENTLY valid. Reject a removed garment '
            'described as worn, invented species/colours, swapped labels, and labels that cannot distinguish '
            'same-species actors. Ignore harmless synonyms. No story edits.\n' + json.dumps({'cast': cast, 'labels': draft['labels']}), audit_schema)
        write_json(audit_path, review)
        if (not draft['uncertain'] and not draft['issues'] and not review['uncertain'] and not review['issues']
                and all(review[k] for k in ('grounded', 'current_state_correct', 'distinguishing'))):
            write_json(saved, {'source_hash': key, 'labels': draft['labels'], 'review': review})
            return draft['labels']
        prompt += '\nCorrect the prior labels using this review: ' + json.dumps({'draft': draft, 'review': review})
    raise ValueError('Current actor labels could not be verified; evidence saved in ' + str(root))


def qualify_text(text, cast, qualifiers):
    """One replacement pass prevents names inside a label being re-expanded."""
    by_name = {c['name']: qualifiers[c['id']] for c in cast}
    if not by_name:
        return text
    pattern = r'(?<!\w)(' + '|'.join(re.escape(n) for n in sorted(by_name, key=len, reverse=True)) + r')(?!\w|\s*\()'
    return re.sub(pattern, lambda m: m[0] + ' (' + by_name[m[0]] + ')', text)


def qualify_action_clause(project, spec, prompt, generate=None):
    if spec['kind'] != 'scene' or not project['render_settings'].get('actor_label_policy'):
        return prompt
    scene, cast = context(project, spec)
    raw = scene['scene_prompt']
    alternatives = [raw, re.sub(r'\s*\(\d+(?:\.\d+)?\s*cm\)', '', raw, flags=re.I)]
    matching = next((s for s in alternatives if s in prompt), None)
    if matching is None:
        # A protected local background repair contains no action clause.
        return prompt
    return prompt.replace(matching, qualify_text(matching, cast, labels(project, spec, generate)))

"""A local single-image check for accidentally restored/duplicated clothing."""
import json


def review_removed_clothing(project, spec, png, generate):
    from .state_ledger import inactive_additions, obj
    if spec['kind'] != 'scene' or not project.get('art_plan'):
        return None
    scene = project['book']['cover'] if spec['name'] == 'cover.png' else next(
        p for p in project['book']['pages'] if spec['name'] == f"pages/page-{p['page_number']:03d}.png")
    changes = inactive_additions(project, scene)
    if not changes:
        return None
    by_id = {c['id']: c for c in project['book']['characters']}
    requirements = [{'id': c['id'], 'character_id': c['character_id'],
        'character': by_id[c['character_id']], 'surface': c['surface'], 'part': c['part'],
        'baseline_on_this_surface': c['before_state'], 'garment_not_worn': c['after_state']}
        for c in changes]
    ids = [c['id'] for c in changes]
    schema = obj({'items': {'type': 'array', 'items': obj({
        'id': {'type': 'string', 'enum': ids}, 'observation': {'type': 'string', 'minLength': 1},
        'visibility': {'type': 'string', 'enum': ['visible', 'physically_occluded', 'unclear']},
        'garment_worn': {'type': ['boolean', 'null']}})},
        'uncertain': {'type': 'boolean'}, 'issues': {'type': 'array', 'items': {'type': 'string'}},
        'retry_instructions': {'type': 'array', 'items': {'type': 'string'}}})
    prompt = (
        'Inspect this ONE candidate illustration. Observe the named character and physical surface FIRST. '
        'For each requirement, describe what actually covers that surface, then state whether the named '
        'temporary garment is being worn. The approved story timeline requires that garment OFF the '
        'character at this moment. Its detached appearance elsewhere is allowed, but cannot excuse a '
        'second copy still worn by the character. Distinguish clothing attached around a neck/body from '
        'fabric resting on a nearby prop. Follow physical attachment and material continuity, not proximity. '
        'A loose garment on a jar rim may naturally hang near the character without being worn. '
        'Ignore other characters\' clothes, unchanged baseline clothing, foliage and background objects. '
        'Do not invent hidden fabric or demand a front view of a physically hidden surface. Use '
        'physically_occluded with garment_worn=null ONLY if the actual body surface is hidden and there '
        'is no visible evidence of the garment being worn. An observable attached garment still means '
        'garment_worn=true even if part of the body is hidden. Ambiguous visible attachment is unclear, '
        'not a pass. Give exactly one observation per required ID. Report consequential visible '
        'contradictions and affirmative corrections; do not alter character design or the story.\n'
        + json.dumps({'requirements': requirements, 'scene': scene['scene_prompt'], 'prose': scene.get('text', '')}))
    result = generate(project['config']['ollama_url'], project['render_settings']['review_model'],
                      prompt, schema, [png])
    complete = sorted(item['id'] for item in result['items']) == sorted(ids)
    valid = lambda item: ((item['visibility'] == 'visible' and item['garment_worn'] is False)
                          or (item['visibility'] == 'physically_occluded' and item['garment_worn'] is None))
    accepted = complete and not result['uncertain'] and not result['issues'] and all(valid(i) for i in result['items'])
    # Some local responses identify the fault but omit a repair. Supply a
    # ledger-derived correction so the automatic next attempt has useful input.
    for item in result['items']:
        if item['garment_worn'] is True:
            required = next(r for r in requirements if r['id'] == item['id'])
            if project.get('render_settings',{}).get('state_scene_policy',0)>=4:
                from .state_ledger import restored_surface_brief
                change=next(c for c in changes if c['id']==item['id'])
                result['retry_instructions'].append(restored_surface_brief(project,scene,change))
                continue
            result['retry_instructions'].append(
                f"Show {required['character']['name']}'s {required['surface']} following the approved current "
                f"reference without the temporary garment ({required['garment_not_worn']}). "
                "Keep all other character details and active clothes. Place the single detached garment "
                "only at its story-specified prop location.")
    return {**result, 'accepted': accepted, 'requirements': requirements}

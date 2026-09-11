"""Resolve a blind count disagreement without silently deleting extra characters."""
import json


def reconcile_scene_count(project, spec, png, inventory, generate):
    from .quality import expected_scene
    from .story import object_schema
    ids, scene, prose = expected_scene(project, spec)
    cast = [c for c in project['book']['characters'] if c['id'] in ids]
    figures = inventory['visible_figures']
    categories = ['character', 'inanimate_depiction', 'not_present', 'uncertain']
    schema = object_schema({
        'observations': {'type':'array', 'items':object_schema({
            'inventory_index': {'type':'integer','minimum':0},
            'category': {'type':'string','enum':categories},
            'character_id': {'type':'string','enum':[*ids, 'unknown']},
            'evidence': {'type':'string','minLength':1}})},
        'additional_characters': {'type':'array','items':{'type':'string','minLength':1}},
        'uncertain': {'type':'boolean'}})
    prompt = ('Inspect this single candidate image to resolve the blind inventory below. Account for '
              'EVERY indexed entry exactly once; do not remove an extra person/animal to match a target '
              'count. A second copy of the same character remains a second character. Classify a stone '
              'statue, carved face, painting, reflection or ordinary toy as an inanimate depiction only '
              'when the image and story establish that role. A face alone does not make a statue alive. '
              'A statue/toy that IS one of this story\'s named acting characters must count as a character. '
              'Use not_present only for an inventory hallucination that is visibly absent; explain the '
              'specific visual evidence. Use unknown for a real character that does not match the cast. '
              'List additional real characters overlooked by the inventory. Mark uncertainty when the '
              'distinction cannot be established. Judge actual visible material, body, pose and context.\n'
              + json.dumps({'indexed_inventory':dict(enumerate(figures)), 'cast':cast,
                            'scene':scene, 'prose':prose}, ensure_ascii=False))
    result = generate(project['config']['ollama_url'], project['render_settings']['review_model'],
                      prompt, schema, [png])
    observations = result['observations']
    indices = [x['inventory_index'] for x in observations]
    resolved = (not result['uncertain'] and sorted(indices)==list(range(len(figures)))
                and all(x['category']!='uncertain' for x in observations))
    count = sum(x['category']=='character' for x in observations) + len(result['additional_characters'])
    per_character = {cid:sum(x['category']=='character' and x['character_id']==cid for x in observations) for cid in ids}
    # Identity/count disagreements still fail the broad per-character gate.
    # Never turn an unresolved or partial audit into an approval.
    return {**result, 'resolved':resolved,
            'figure_count':count if resolved else inventory['figure_count'],
            'per_character':per_character}

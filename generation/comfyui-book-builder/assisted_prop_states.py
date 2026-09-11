"""Dependencies and scene routing for assembled or changed recurring props."""
from .assisted_references import MAX_REFERENCE_IMAGES

GUIDANCE = '''Track recurring objects through the WHOLE story before assigning scene references.
When an arrangement or physical change persists across pictures, create a prop_state reference:
a tower assembled from pots, a tied bundle, a filled basket, a repaired toy or a decorated vehicle.
source_assets lists the existing prop IDs whose designs it inherits (or an earlier prop_state).
Only prop_state references have source_assets. visible_pages is required for prop_state references;
visibility annotations for ordinary references are optional and do not replace scene asset_refs.
appearance describes the complete resulting object, including part count, arrangement, orientation,
contact/support and relative size. This is ONE reusable assembled object, not extra loose copies.
visible_pages lists the pages whose pictured moment shows that state, including 0 for a matching cover.
Generate components first, then the assembled state using those component images. In each listed
scene use the prop_state instead of its separate components. Before assembly use the original props;
after dismantling use the appropriate later state. Do not show the finished object before it exists.
Do not invent changes or create a state for every pose. If a later page mentions only a component
(such as the smallest pot), retain the whole assembled object and its established support.
'''


def ordered_assets(assets, page_count):
    by_id={a['id']:a for a in assets}
    visiting=set();done=set();result=[]
    def visit(aid):
        if aid in done:return
        if aid in visiting:raise ValueError('Prop state dependencies must not contain a cycle.')
        asset=by_id[aid];visiting.add(aid)
        sources=asset.get('source_assets',[]);pages=asset.get('visible_pages',[])
        if any(p<0 or p>page_count for p in pages):
            raise ValueError('References need valid visible_pages from this book.')
        if asset['kind']=='prop_state':
            if not sources or len(sources)>MAX_REFERENCE_IMAGES:
                raise ValueError('A prop state needs one to six source prop references.')
            if not pages or any(p<0 or p>page_count for p in pages):
                raise ValueError('A prop state needs valid visible_pages from this book.')
            for source in sources:
                if source not in by_id or by_id[source]['kind'] not in ('prop','prop_state'):
                    raise ValueError(f'Unknown or non-prop source {source} for {aid}.')
                visit(source)
        elif sources:
            raise ValueError('Only prop_state references use source_assets.')
        visiting.remove(aid);done.add(aid);result.append(asset)
    for aid in by_id:visit(aid)
    return result


def ancestors(asset_id, assets):
    result=set()
    for source in assets[asset_id].get('source_assets',[]):
        result.add(source);result.update(ancestors(source,assets))
    return result


def validate_scene(scene, assets):
    refs=set(scene['asset_refs'])
    for asset in assets.values():
        if asset['kind']!='prop_state':continue
        shown=asset['id'] in refs
        if shown != (scene['page'] in asset['visible_pages']):
            raise ValueError(f"Page {scene['page']}: {asset['name']} must match its visible_pages schedule.")
        if shown and refs & ancestors(asset['id'],assets):
            raise ValueError(f"Page {scene['page']}: use {asset['name']} instead of separate source props to avoid duplicates.")

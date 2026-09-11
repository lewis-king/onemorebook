"""Saved additions to a reviewed plan without overwriting approved candidates."""
import copy
import json
import uuid

from . import assisted_store as store
from .storage import write_json


def effective_plan(state):
    from . import assisted_engine as engine
    plan=json.loads(engine.approved(state,'plan').read_text())
    for update_id in state.get('reference_updates',[]):
        if len(update_id)!=32 or any(c not in '0123456789abcdef' for c in update_id):
            raise ValueError('Invalid saved reference update ID.')
        update=json.loads((store.root(state['id'])/'creator/plan-updates'/f'{update_id}.json').read_text())
        plan['assets'].append(update['asset'])
        for asset_id,pages in update.get('asset_visibility',{}).items():
            existing=next((a for a in plan['assets'] if a['id']==asset_id),None)
            if existing is not None:
                existing['visible_pages']=pages
        scene=next(s for s in plan['scenes'] if s['page']==update['page'])
        scene.update(moment=update['moment'],asset_refs=update['asset_refs'])
    return plan


def add_prop_state(state, asset, *, scene_id, moment, asset_refs, source_scene=None):
    """Called for an explicitly requested correction, then human review resumes at the new reference."""
    from . import assisted_engine as engine, assisted_plan
    with store.LOCK:
        latest=store.read(state['id']);store.expect_revision(latest,state['revision'])
        current=store.stage(latest)
        if (latest['status'] not in ('ready','awaiting_review') or latest.get('page_revision')
                or current['id']!=scene_id or current['kind']!='scene' or current['status']=='approved'):
            raise store.Conflict('Add a prop state while its page is the current unapproved, idle step.')
        if asset.get('kind')!='prop_state' or asset.get('visible_pages')!=[current['page']]:
            raise ValueError('This addition must be a prop_state for the current page.')
        plan=effective_plan(latest)
        # When a new state supersedes an older state on this page, retire the
        # older state's visibility here while preserving it for earlier scenes.
        asset_visibility={}
        for source_id in asset.get('source_assets',[]):
            source=next((a for a in plan['assets'] if a['id']==source_id),None)
            if source and source.get('kind')=='prop_state' and current['page'] in source.get('visible_pages',[]):
                pages=[p for p in source['visible_pages'] if p!=current['page']]
                if pages:
                    asset_visibility[source_id]=pages
                    source['visible_pages']=pages
        plan['assets'].append(copy.deepcopy(asset))
        scene=next(s for s in plan['scenes'] if s['page']==current['page'])
        scene.update(moment=moment,asset_refs=asset_refs)
        expanded=assisted_plan.stages(engine.package(latest),plan)
        new_stage=next(s for s in expanded if s['id']=='props/'+asset['id']+'.png')
        changed=next(s for s in expanded if s['id']==scene_id)
        if any(s['id']==new_stage['id'] for s in latest['stages']):
            raise ValueError('This prop reference already exists.')
        source=None
        if source_scene:
            source_stage=store.stage(latest,source_scene)
            if source_stage['kind']!='scene' or source_stage.get('page',0)>=current['page']:
                raise ValueError('Use an earlier approved scene as the arrangement source.')
            engine.approved(latest,source_scene)
            candidate=engine.selected(latest,source_scene)
            source={'stage':source_scene,'candidate_id':candidate['id'],'sha256':candidate['sha256']}
            new_stage.update(source_scene=source_scene,references=[source_scene],
                brief=f"Isolate the {asset['name']} from Image 1 on a flat warm ivory background. "
                      'Remove the characters and surrounding scenery. Preserve the existing object arrangement, '
                      'part count, proportions, orientation, colours and painted texture. '
                      'Show the complete object with its base visible. '+asset['appearance'])
        for sid in new_stage['references']:
            engine.approved(latest,sid)
        update_id=uuid.uuid4().hex
        record={'id':update_id,'created_at':store.now(),'asset':asset,'asset_visibility':asset_visibility,
                'page':current['page'],
                'moment':moment,'asset_refs':asset_refs,'source_scene':source,
                'previous_scene':{k:copy.deepcopy(current.get(k)) for k in ('brief','references','prompt_base')},
                'reason':'User-requested reusable prop state','previous_revision':latest['revision']}
        write_json(store.root(latest['id'])/'creator/plan-updates'/f'{update_id}.json',record)
        current.update(brief=changed['brief'],references=changed['references'],reference_revision=update_id)
        # The old prompt has obsolete image numbering and remains in its immutable history.
        current.pop('prompt_base',None)
        index=latest['stages'].index(current)
        latest['stages'].insert(index,new_stage)
        latest.setdefault('reference_updates',[]).append(update_id)
        latest.update(current_stage=new_stage['id'],status='ready',job=None,error=None)
        latest['revision']+=1;store.save(latest)
        return latest

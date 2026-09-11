import copy
import hashlib
import importlib
import json
import unittest
from unittest.mock import patch

import test_assisted_creator as helpers

store=helpers.store;engine=helpers.engine;planning=helpers.planning
updates=importlib.import_module('book_test_pack.assisted_reference_updates')
context=importlib.import_module('book_test_pack.assisted_prompt_context')


class PropStateTests(unittest.TestCase):
    setUp=helpers.AssistedCreatorTests.setUp
    restore_module=helpers.AssistedCreatorTests.restore_module
    state=helpers.AssistedCreatorTests.state
    add=helpers.AssistedCreatorTests.add
    approve=helpers.AssistedCreatorTests.approve
    plan=helpers.AssistedCreatorTests.plan
    prepare=helpers.AssistedCreatorTests.prepare
    png=helpers.AssistedCreatorTests.png

    def assembled_plan(self):
        state=self.approve(self.state());value=self.plan(state)
        # Deliberately list the assembly before its components; staging must sort dependencies.
        value['assets'] += [
            {'id':'tower','kind':'prop_state','name':'Pot tower','appearance':'Three pots, large below medium below small.',
             'source_character':'','source_assets':['large','medium','small'],'visible_pages':[2]},
            *[{'id':p,'kind':'prop','name':p+' pot','appearance':p+' orange pot.','source_character':''} for p in ['large','medium','small']]]
        value['scenes'][1]['asset_refs']+=['large','medium','small']
        value['scenes'][2]['asset_refs']+=['tower']
        return state,value

    def test_assembly_staging_and_actual_reference_inputs(self):
        state,plan=self.assembled_plan();state=self.approve(self.add(state,plan))
        names=[s['id'] for s in state['stages']]
        for part in ['large','medium','small']:self.assertLess(names.index('props/'+part+'.png'),names.index('props/tower.png'))
        while state['current_stage']!='props/tower.png':state=self.approve(self.png(state))
        intent=store.next_attempt(state)
        prompt,refs,hashes=engine.image_inputs(state,store.stage(state),intent)
        self.assertEqual(len(refs),3)
        self.assertEqual(set(hashes),{'props/large.png','props/medium.png','props/small.png'})
        self.assertIn('parts of this single result',prompt)
        for ref in refs:self.assertTrue((store.root(state['id'])/ref['path']).is_file())
        scene=store.stage(state,'pages/page-002.png')
        self.assertIn('props/tower.png',scene['references'])
        self.assertNotIn('props/small.png',scene['references'])
        self.assertNotIn('props/tower.png',store.stage(state,'pages/page-001.png')['references'])

    def test_schedule_and_component_duplication_rejected(self):
        state,plan=self.assembled_plan();package=engine.package(state)
        broken=copy.deepcopy(plan);broken['scenes'][2]['asset_refs'].append('small')
        with self.assertRaisesRegex(ValueError,'instead of separate source props'):planning.validate(package,broken)
        broken=copy.deepcopy(plan);broken['scenes'][2]['asset_refs'].remove('tower')
        with self.assertRaisesRegex(ValueError,'visible_pages'):planning.validate(package,broken)
        broken=copy.deepcopy(plan);broken['scenes'][1]['asset_refs'].append('tower')
        with self.assertRaisesRegex(ValueError,'visible_pages'):planning.validate(package,broken)

    def test_cycles_unknown_sources_and_budget_rejected(self):
        state,plan=self.assembled_plan();package=engine.package(state)
        for sources,message in [(['tower'],'cycle'),(['missing'],'Unknown'),(['garden'],'non-prop')]:
            broken=copy.deepcopy(plan);broken['assets'][1]['source_assets']=sources
            with self.assertRaisesRegex(ValueError,message):planning.validate(package,broken)
        broken=copy.deepcopy(plan);broken['assets'][1]['visible_pages']=[4]
        with self.assertRaisesRegex(ValueError,'valid visible_pages'):planning.validate(package,broken)

    def test_later_state_can_inherit_an_assembly_without_duplicate_ancestors(self):
        state,plan=self.assembled_plan();package=engine.package(state)
        plan['assets'].append({'id':'painted_tower','kind':'prop_state','name':'Painted tower',
            'appearance':'The same tower painted blue.','source_character':'','source_assets':['tower'],'visible_pages':[3]})
        plan['scenes'][3]['asset_refs'].append('painted_tower')
        stages=planning.stages(package,plan)
        self.assertEqual(next(s for s in stages if s['id']=='props/painted_tower.png')['references'],['props/tower.png'])
        plan['scenes'][3]['asset_refs'].append('small')
        with self.assertRaisesRegex(ValueError,'instead of separate source props'):planning.validate(package,plan)

    def test_preparation_receives_prior_events_without_montage_prompting(self):
        current={'id':'page11','kind':'scene','page':11,'text':'Milo stands on the small pot.','references':['tower']}
        stages={'tower':{'kind':'prop_state','title':'Pot tower','brief':'Small above medium above large.'},
                'p9':{'page':9,'text':'They stack the pots.'},'p10':{'page':10,'text':'Milo climbs the tower.'},
                'p12':{'page':12,'text':'Future event must stay out.'}}
        prompt=context.revision_request(current,{'feedback':''},'An old isolated pot.',
                  [{'label':'Pot tower'}],stages,preparing=True)
        self.assertIn('They stack the pots.',prompt);self.assertIn('Milo climbs the tower.',prompt)
        self.assertNotIn('Future event must stay out.',prompt)
        self.assertIn('only one part',prompt);self.assertIn('not a montage',prompt)

    def test_addition_preserves_approved_plan_and_requires_new_reference_review(self):
        state,plan=self.assembled_plan()
        # Existing saved plan did not anticipate the assembly.
        asset=plan['assets'].pop(1);plan['scenes'][2]['asset_refs']=['garden','small']
        state=self.approve(self.add(state,plan))
        while state['current_stage']!='pages/page-002.png':state=self.approve(self.png(state))
        state=self.png(state);before=copy.deepcopy(state)
        original_plan=engine.approved(state,'plan').read_bytes();old_scene=engine.selected(state,state['current_stage'])
        state=updates.add_prop_state(state,asset,scene_id=state['current_stage'],
            moment='Mira stands on the small pot at the top of the three-pot tower.',asset_refs=['garden','tower'],source_scene='pages/page-001.png')
        self.assertEqual(state['current_stage'],'props/tower.png');self.assertEqual(state['status'],'ready')
        self.assertEqual(store.stage(state)['references'],['pages/page-001.png'])
        self.assertEqual(engine.approved(state,'plan').read_bytes(),original_plan)
        self.assertEqual(store.stage(state,'pages/page-001.png'),store.stage(before,'pages/page-001.png'))
        self.assertEqual(store.stage(state,'pages/page-002.png')['candidates'],store.stage(before,'pages/page-002.png')['candidates'])
        self.assertEqual(updates.effective_plan(state)['assets'][-1]['id'],'tower')
        planning.validate(engine.package(state),updates.effective_plan(state))
        with self.assertRaisesRegex(ValueError,'approval first'):engine.approved(state,'props/tower.png')
        state=self.approve(self.png(state)) # fixture-only approval of the new reference
        self.assertEqual(state['current_stage'],'pages/page-002.png');self.assertEqual(state['status'],'ready')
        record=store.decision(state,old_scene,'approve','Fixture should be rejected for obsolete references.')
        with self.assertRaisesRegex(ValueError,'earlier reference set'):engine.advance(state,old_scene,record)
        # Next real preparation consumes the tower, not an old small-pot reference/prompt.
        intent=store.next_attempt(state)
        with patch.object(engine,'draft_json',return_value={'prompt':'Mira stands atop the assembled tower from Image 3.'}):
            prompt,refs,hashes=engine.image_inputs(state,store.stage(state),intent)
        self.assertEqual(len(refs),3)
        self.assertIn('props/tower.png',hashes);self.assertNotIn('props/small.png',hashes)
        self.assertIn('assembled tower',prompt)
        self.assertEqual(store.read(state['id'])['job']['attempt'],2)

    def test_legacy_plan_keeps_identical_stage_structure(self):
        state=self.approve(self.state());plan=self.plan(state)
        paths=[s['id'] for s in planning.stages(engine.package(state),plan)]
        self.assertIn('locations/garden.png',paths)
        self.assertEqual(paths[-3:],['pages/page-001.png','pages/page-002.png','pages/page-003.png'])
        self.assertFalse(any(s['kind']=='prop_state' for s in planning.stages(engine.package(state),plan)))

    def test_non_character_references_need_no_character_source_field(self):
        state,plan=self.assembled_plan()
        for asset in plan['assets']:asset.pop('source_character',None)
        stages=planning.stages(engine.package(state),plan)
        self.assertEqual(next(s for s in stages if s['id']=='props/tower.png')['character_id'],'')

    def test_optional_ordinary_visibility_keeps_state_routing_strict(self):
        state,plan=self.assembled_plan()
        plan['assets'][0]['visible_pages']=[0,1,2,3]
        planning.validate(engine.package(state),plan)
        plan['scenes'][2]['asset_refs'].remove('tower')
        with self.assertRaisesRegex(ValueError,'visible_pages'):planning.validate(engine.package(state),plan)

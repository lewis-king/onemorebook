import copy
import importlib
import unittest
from unittest.mock import patch

import test_book as fixtures
from test_book import story, storage
from test_states import change_fixture

clothing = importlib.import_module('book_test_pack.clothing')
ledger = importlib.import_module('book_test_pack.state_ledger')
quality = importlib.import_module('book_test_pack.quality')
state_quality = importlib.import_module('book_test_pack.state_quality')
pose = importlib.import_module('book_test_pack.pose')
detection = importlib.import_module('book_test_pack.detection')


class ClothingTests(unittest.TestCase):
    setUp = fixtures.BookTests.setUp
    restore_module = fixtures.BookTests.restore_module

    def plan(self):
        change = change_fixture()
        change.update(id='green_scarf', operation='add_clothing', active_pages=[1],
                      before_state='red coat without scarf', after_state='wearing a green scarf')
        self.project['art_plan'] = {'ledger': {'changes': [change]},
            'pages': {'1': {'changes': ['green_scarf'], 'props': []},
                      '2': {'changes': [], 'props': []}, '3': {'changes': [], 'props': []}},
            'cover': {'changes': [], 'props': []}}
        self.project['config']['ollama_url'] = 'http://unused'
        self.project['render_settings']['review_model'] = 'local-test'
        return change

    def test_inactive_intervals_cover_and_offscreen_actors_preserve_contract(self):
        self.plan()
        before = copy.deepcopy(self.project)
        scenes = self.project['book']['pages']
        self.assertEqual(ledger.inactive_additions(self.project, scenes[0]), [])
        self.assertEqual([c['id'] for c in ledger.inactive_additions(self.project, scenes[1])], ['green_scarf'])
        self.assertEqual(ledger.inactive_additions(self.project, scenes[2]), [])
        self.assertEqual(len(ledger.inactive_additions(self.project, self.project['book']['cover'])), 1)
        self.assertEqual(self.project, before)
        self.project['art_plan']['pages']['2']['changes'] = ['green_scarf']
        self.assertEqual(ledger.inactive_additions(self.project, scenes[1]), [])

    def test_removed_clothing_is_a_veto_and_does_not_invent_occluded_proof(self):
        self.plan()
        spec = {'kind':'scene','name':'pages/page-002.png'}
        for visibility,worn,accepted in [('visible',True,False),('visible',False,True),
                ('visible',None,False),('physically_occluded',None,True),
                ('physically_occluded',True,False),('unclear',None,False)]:
            result={'items':[{'id':'green_scarf','observation':'Observed the body surface.',
                              'visibility':visibility,'garment_worn':worn}],
                    'uncertain':False,'issues':[],'retry_instructions':[]}
            with patch.object(clothing,'json',wraps=clothing.json):
                calls=[]
                def generate(*args):
                    calls.append(args)
                    return result
                audit=clothing.review_removed_clothing(self.project,spec,b'candidate',generate)
            self.assertEqual(audit['accepted'],accepted)
            self.assertEqual(calls[0][-1],[b'candidate'])
            broad={'checks':{'scene_matches':True,'anatomy_sound':False},'issues':['Unrelated anatomy failure']}
            state_quality.apply_state_review(broad,audit)
            self.assertFalse(broad['checks']['anatomy_sound'])
            self.assertIn('Unrelated anatomy failure',broad['issues'])
            self.assertEqual(broad['checks']['scene_matches'],accepted)
        for items,uncertain in [([],False),(result['items']*2,False),(result['items'],True)]:
            with self.subTest(items=items,uncertain=uncertain):
                audit=clothing.review_removed_clothing(self.project,spec,b'candidate',
                    lambda *args:{**result,'items':items,'uncertain':uncertain})
                self.assertFalse(audit['accepted'])

    def test_inactive_requirements_enter_new_prompts_without_changing_legacy_prompts(self):
        self.plan()
        scene=self.project['book']['pages'][1]
        for policy in (1,2):
            self.project['render_settings']['state_scene_policy']=policy
            self.assertEqual(ledger.state_brief(self.project,scene),'')
        self.project['render_settings']['state_scene_policy']=3
        self.assertIn('not worn',ledger.state_brief(self.project,scene))
        self.assertIn('one physical copy',ledger.state_brief(self.project,scene))

    def test_otter_and_crab_are_separate_detector_queries(self):
        self.assertEqual(detection.detection_phrase({'appearance':'A brown sea otter in a yellow raincoat.'}),'a otter.')
        self.assertEqual(detection.detection_phrase({'appearance':'A red crab with black eyes and pearls.'}),'a crab.')
        self.assertEqual(detection.detection_phrase({'appearance':'An otter','detection_prompt':'A SEA OTTER'}),'a sea otter.')
        self.assertEqual(detection.detection_phrase({'appearance':'Slow-moving sloth with greyish-brown shaggy fur.'}),'a sloth.')

    def test_removed_baseline_garment_is_absent_from_both_current_prompt_paths(self):
        change=self.plan()
        change.update(operation='modify_existing',after_state='scarf removed')
        actor=self.project['book']['characters'][0]
        actor['appearance']='A child with black curls. Wears a green scarf and red boots.'
        self.project['state_edits']={'green_scarf':{'plan':{
            'desired_region':'bare neck and shoulders',
            'inventory_after':'red boots on the feet',
            'preserved_features':'face and curls'}}}
        for c in self.project['book']['characters']:c['height_cm']=60
        scene=self.project['book']['pages'][0]
        spec={'name':'pages/page-001.png','kind':'scene'}
        before=copy.deepcopy(self.project)
        self.project['render_settings']['state_scene_policy']=5
        for prompt in (story.scene_prompt(self.project,scene),fixtures.render.cast_sheet_prompt(self.project,spec)):
            self.assertNotIn('Wears a green scarf',prompt)
            self.assertIn('bare neck and shoulders',prompt)
            self.assertIn('red boots on the feet',prompt)
        self.project['render_settings']['state_scene_policy']=4
        self.assertIn('Wears a green scarf',story.scene_prompt(self.project,scene))
        self.assertEqual(actor['appearance'],before['book']['characters'][0]['appearance'])

    def test_flowing_asset_selector_preserves_native_seed_and_spec(self):
        nodes=importlib.import_module('book_test_pack.nodes')
        self.project['config']['seed']=2**61+7
        expected=next(s for s in story.asset_specs(self.project) if s['name']=='pages/page-001.png')
        actual=nodes.BookV2SelectAsset().select(self.project,'pages/page-001.png')[0]
        self.assertEqual(actual,expected)
        with self.assertRaises(ValueError):nodes.BookV2SelectAsset().select(self.project,'missing.png')

    def test_restored_surface_is_positive_and_does_not_erase_another_active_garment(self):
        change=self.plan()
        change.update(before_state='bare brown fur',after_state='wearing a green cape',part='neck and back')
        self.project['render_settings']['state_scene_policy']=4
        scene=self.project['book']['pages'][1]
        brief=ledger.state_brief(self.project,scene)
        self.assertIn('bare brown fur',brief)
        self.assertNotIn('wearing a green cape',brief)
        self.assertNotIn('not worn',brief)
        active={**change,'id':'raincoat','after_state':'a yellow raincoat'}
        self.project['art_plan']['ledger']['changes'].append(active)
        self.project['art_plan']['pages']['2']['changes']=['raincoat']
        brief=ledger.restored_surface_brief(self.project,scene,change)
        self.assertIn('a yellow raincoat',brief)
        self.assertNotIn('bare brown fur',brief)
        self.assertNotIn('green cape',brief)

    def test_positive_surface_precedes_scene_and_retry_does_not_quote_unwanted_clothing(self):
        change=self.plan()
        change.update(before_state='bare brown fur',after_state='wearing a green cape',part='neck and back')
        self.project['render_settings'].update(state_scene_policy=4,renderer='flux2',
            **fixtures.render.FLUX_MODELS,flux_steps=28,flux_guidance=4)
        spec=next(s for s in story.asset_specs(self.project) if s['name']=='pages/page-002.png')
        graph=fixtures.render.expand_attempt(self.project,spec,1)['expand']
        prompt=next(n['inputs']['text'] for n in graph.values() if n['class_type']=='CLIPTextEncode')
        self.assertLess(prompt.index('bare brown fur'),prompt.index(self.project['book']['pages'][1]['scene_prompt']))
        self.assertEqual(prompt.count('bare brown fur'),1)
        audit=clothing.review_removed_clothing(self.project,spec,b'candidate',lambda *args:{
            'items':[{'id':'green_scarf','observation':'Cape is still attached.','visibility':'visible','garment_worn':True}],
            'uncertain':False,'issues':['Still attached.'],'retry_instructions':[]})
        self.assertFalse(audit['accepted'])
        self.assertIn('bare brown fur',audit['retry_instructions'][0])
        self.assertNotIn('wearing a green cape',audit['retry_instructions'][0])

    def test_costume_failures_do_not_trigger_pose_repair_or_invent_crab_limbs(self):
        self.assertFalse(pose.pose_action_failed({'story_event_visible':True,'uncertain':False,'essential_issues':[]}))
        self.assertFalse(pose.pose_action_failed(None))
        self.assertFalse(pose.pose_action_failed({'story_event_visible':False,'uncertain':True,'essential_issues':['unclear']}))
        self.assertTrue(pose.pose_action_failed({'story_event_visible':False,'uncertain':False,'essential_issues':['Missing action']}))
        self.assertTrue(pose.supports_pose_diagram(self.project['book']['characters']))
        self.assertFalse(pose.supports_pose_diagram([{'appearance':'A crab with pearls.'}]))
        self.assertFalse(pose.supports_pose_diagram([{'appearance':'A flying jellyfish with a bow.'}]))

    def test_added_garment_description_is_verified_cached_and_kept_out_of_image_references(self):
        assets=importlib.import_module('book_test_pack.state_assets')
        garment=importlib.import_module('book_test_pack.garment_reference')
        render=fixtures.render
        self.plan()
        prop={'id':'scarf_on_peg','source_change_id':'green_scarf','description':'Green scarf on a peg.'}
        self.project['art_plan']['ledger']['detached_props']=[prop]
        self.project['art_plan']['pages']['2']['props']=[prop['id']]
        self.project['render_settings'].update(renderer='flux2',**render.FLUX_MODELS,flux_steps=28,
            flux_guidance=4,reference_strategy='cast_guide',garment_reference_policy=1,state_scene_policy=3)
        for c,h in zip(self.project['book']['characters'],[110,50,55]):c['height_cm']=h
        draft={'description':'A long green woven scarf with a plain fringe.','uncertain':False,'issues':[]}
        review={'faithful':True,'garment_only':True,'uncertain':False,'issues':[],'evidence':'Visible green woven fabric.'}
        with (patch.object(assets,'prop_reference',return_value=(b'approved worn image','worn reference')),
                patch.object(quality,'json_model',side_effect=[draft,review]) as model):
            design=garment.garment_design(self.project,prop)
            self.assertEqual(design,draft['description'])
            self.assertEqual(garment.garment_design(self.project,prop),design)
            self.assertEqual(model.call_count,2)
            spec=next(s for s in story.asset_specs(self.project) if s['name']=='pages/page-002.png')
            graph=render.expand_attempt(self.project,spec,1)['expand']
        kinds=[n['class_type'] for n in graph.values()]
        self.assertNotIn('BookV2LoadPropDetail',kinds)
        self.assertEqual(kinds.count('ReferenceLatent'),1)
        prompt=next(n['inputs']['text'] for n in graph.values() if n['class_type']=='CLIPTextEncode')
        self.assertIn(design,prompt)
        self.assertIn('Green scarf on a peg.',prompt)

    def test_unverified_garment_description_cannot_be_used_for_rendering(self):
        garment=importlib.import_module('book_test_pack.garment_reference')
        assets=importlib.import_module('book_test_pack.state_assets')
        self.plan()
        prop={'id':'scarf','source_change_id':'green_scarf','description':'A green scarf.'}
        draft={'description':'An invented red hat.','uncertain':False,'issues':[]}
        review={'faithful':False,'garment_only':True,'uncertain':False,'issues':['Wrong item.'],'evidence':'Scarf visible.'}
        with (patch.object(assets,'prop_reference',return_value=(b'approved worn image','worn reference')),
                patch.object(quality,'json_model',side_effect=[draft,review,draft,review])):
            with self.assertRaisesRegex(ValueError,'could not be verified'):
                garment.garment_design(self.project,prop)

    def test_removed_garment_uses_checked_item_design_without_former_wearer_pixels(self):
        assets=importlib.import_module('book_test_pack.state_assets')
        garment=importlib.import_module('book_test_pack.garment_reference')
        change=self.plan()
        change.update(operation='modify_existing',before_state='green scarf worn',after_state='bare coat neckline')
        change['reference_edit']['target_query']='a green woven scarf'
        prop={'id':'scarf_on_peg','source_change_id':'green_scarf','description':'Green scarf on a peg.'}
        self.project['art_plan']['ledger']['detached_props']=[prop]
        self.project['art_plan']['pages']['2'].update(props=[prop['id']],changes=['green_scarf'])
        render=fixtures.render
        self.project['render_settings'].update(renderer='flux2',**render.FLUX_MODELS,flux_steps=28,
            flux_guidance=4,reference_strategy='cast_guide',garment_reference_policy=2,state_scene_policy=5)
        for c,h in zip(self.project['book']['characters'],[110,50,55]):c['height_cm']=h
        original=copy.deepcopy(self.project['story'])
        draft={'description':'A long green woven scarf with a plain fringe.','uncertain':False,'issues':[]}
        check={'faithful':True,'garment_only':True,'uncertain':False,'issues':[],'evidence':'Visible green woven fabric.'}
        with (patch.object(assets,'prop_reference',return_value=(b'crop with part of wearer','measured source')),
              patch.object(quality,'json_model',side_effect=[draft,check]) as model):
            spec=next(s for s in story.asset_specs(self.project) if s['name']=='pages/page-002.png')
            graph=render.expand_attempt(self.project,spec,1)['expand']
            self.assertEqual(model.call_count,2)
            self.assertIn('a green woven scarf',model.call_args_list[0].args[2])
            self.assertNotIn('bare coat neckline',model.call_args_list[0].args[2])
        kinds=[n['class_type'] for n in graph.values()]
        self.assertNotIn('BookV2LoadPropDetail',kinds)
        self.assertEqual(kinds.count('ReferenceLatent'),1)
        prompt=next(n['inputs']['text'] for n in graph.values() if n['class_type']=='CLIPTextEncode')
        self.assertIn(draft['description'],prompt)
        self.assertIn('Green scarf on a peg.',prompt)
        self.assertEqual(original,self.project['story'])

    def test_removed_garment_description_containing_body_is_rejected(self):
        assets=importlib.import_module('book_test_pack.state_assets')
        garment=importlib.import_module('book_test_pack.garment_reference')
        change=self.plan();change['operation']='modify_existing'
        self.project['render_settings']['garment_reference_policy']=2
        prop={'id':'scarf','source_change_id':'green_scarf','description':'A green scarf.'}
        draft={'description':'A green scarf around a child’s neck and face.','uncertain':False,'issues':[]}
        check={'faithful':True,'garment_only':False,'uncertain':False,'issues':['Includes wearer.'],'evidence':'Face is context.'}
        with (patch.object(assets,'prop_reference',return_value=(b'approved crop','measured source')),
              patch.object(quality,'json_model',side_effect=[draft,check,draft,check])):
            with self.assertRaisesRegex(ValueError,'could not be verified'):
                garment.garment_design(self.project,prop)


if __name__ == '__main__':
    unittest.main()

import copy
import importlib
import json
from pathlib import Path
from unittest.mock import patch
import test_book as fixtures

contract=importlib.import_module('book_test_pack.scene_contract')
quality=importlib.import_module('book_test_pack.quality')


class SceneContractTests(fixtures.unittest.TestCase):
    setUp=fixtures.BookTests.setUp
    restore_module=fixtures.BookTests.restore_module

    def install(self):
        self.project['render_settings'].update(renderer='flux2',review_model='fixture',reference_strategy='cast_guide')
        self.project['config']['ollama_url']='unused'
        self.project['scene_contract']={'version':1,'objects':[{'id':'bottle','name':'bottle',
            'appearance':'one transparent blue glass bottle','source_pages':[1]}],
            'scenes':{'pages/page-001.png':{'asset_name':'pages/page-001.png',
                'literal_prompt':'Mira holds the bottle containing the silver coin.',
                'object_ids':['bottle'],'checks':[{'id':'contents','requirement':'The coin is visible inside the bottle.',
                    'visibility':'required','source_pages':[1],'reason':'The lost object is trapped.'}]}}}
        return fixtures.story.asset_specs(self.project)[4]

    def test_private_brief_reaches_generation_and_review_without_mutating_story(self):
        original=copy.deepcopy(self.project['story'])
        self.install()
        scene=self.project['book']['pages'][0]
        spec=next(s for s in fixtures.story.asset_specs(self.project) if s['name']=='pages/page-001.png')
        self.assertIn('coin',spec['prompt'])
        self.assertIn('coin',quality.expected_scene(self.project,spec)[1])
        self.assertNotIn('style.png',spec['references'])
        self.assertEqual(self.project['story'],original)
        self.project['scene_contract']['scenes']['pages/page-002.png']={**self.project['scene_contract']['scenes']['pages/page-001.png'],
            'asset_name':'pages/page-002.png','literal_prompt':'Mira, Pip and Fern share the coin.'}
        for c,height in zip(self.project['book']['characters'],[100,10,30]):c['height_cm']=height
        spec=next(s for s in fixtures.story.asset_specs(self.project) if s['name']=='pages/page-002.png')
        self.assertIn('share the coin',fixtures.render.cast_sheet_prompt(self.project,spec))

    def test_missing_contents_veto_cannot_be_cleared_by_other_passed_reviews(self):
        self.install()
        spec={'kind':'scene','name':'pages/page-001.png'}
        def audit(*args):
            return {'items':[{'id':'contents','observation':'The bottle is visibly empty.', 'matches':False,'uncertain':False},
                {'id':'design_bottle','observation':'The blue glass bottle matches.', 'matches':True,'uncertain':False}]}
        result=contract.review_scene_contract(self.project,spec,b'candidate',audit)
        self.assertFalse(result['accepted'])
        report={'checks':{'scene_matches':True},'issues':[]}
        state=importlib.import_module('book_test_pack.state_quality')
        state.apply_state_review(report,result)
        self.assertFalse(report['checks']['scene_matches'])
        self.assertIn('coin',result['retry_instructions'][0])

    def test_routed_synonym_keeps_established_contents_without_recursive_library_lookup(self):
        self.install()
        self.project['render_settings'].update(scene_contract_prompt_policy=1,scene_context_policy=3)
        self.project['scene_contract']['objects'].append({'id':'coin','name':'Silver Coin','appearance':'Small silver disc.'})
        record=self.project['scene_contract']['scenes']['pages/page-001.png']
        record.update(literal_prompt='Mira examines the vessel.',object_ids=[],checks=[])
        self.project['story']['pages'][0]['text']='Mira examines the vessel.'
        self.project['scene_contract']['persistent_facts']=[{'id':'stored_coin','object_ids':['bottle','coin'],
            'from_page':1,'through_page':2,'requirement':'The silver coin remains inside the bottle.',
            'visibility':'conditional'}]
        self.project['visual_library']={'plan':{'entries':[{'source_object_id':'bottle',
            'source_character_id':'','scenes':['pages/page-001.png']}]}}
        objects,checks=contract.scene_render_details(self.project,self.project['book']['pages'][0])
        self.assertEqual({o['id'] for o in objects},{'bottle','coin'})
        self.assertEqual(len(checks),1)
        self.project['scene_contract']['persistent_facts'][0]['through_page']=0
        objects,checks=contract.scene_render_details(self.project,self.project['book']['pages'][0])
        self.assertEqual({o['id'] for o in objects},{'bottle'})
        self.assertFalse(checks)

    def test_incomplete_and_uncertain_reviews_do_not_pass(self):
        self.install();spec={'kind':'scene','name':'pages/page-001.png'}
        for items in [[],[{'id':'contents','observation':'unclear','matches':True,'uncertain':True}]]:
            result=contract.review_scene_contract(self.project,spec,b'candidate',lambda *args:{'items':items})
            self.assertFalse(result['accepted'])

    def test_bind_original_frames_without_adding_incidental_requirements(self):
        scenes=[{'asset_name':'pages/page-001.png','scene_prompt':'Mira holds a red ball by a statue.'},
                {'asset_name':'pages/page-002.png','scene_prompt':'Pip holds a ball.'}]
        objects=[{'id':'red_ball','name':'red ball'}, {'id':'blue_ball','name':'blue ball'},
                 {'id':'stone_statue','name':'grey stone statue'}]
        result=contract.bind_original_scenes(scenes,objects)
        self.assertEqual(result[0]['object_ids'],['red_ball','stone_statue'])
        self.assertEqual(result[1]['object_ids'],[])
        self.assertEqual([r['literal_prompt'] for r in result],[s['scene_prompt'] for s in scenes])
        self.assertTrue(all(r['checks']==[] for r in result))

    def test_pipeline_compiler_checkpoints_and_reuses_exact_approved_plan(self):
        self.install();self.project['book_root']=str(self.output/'books/test')
        calls=[]
        def generate(url,model,prompt,schema,**kwargs):
            calls.append(prompt)
            if 'requirements' in schema['properties']:
                return {'requirements':[]}
            if 'valid' in schema['properties']:
                return {'valid':True,'uncertain':False,'issues':[],'evidence':'Verified against prose.'}
            if 'objects' in schema['properties']:
                return {'objects':[],'persistent_facts':[]}
            names=schema['properties']['scenes']['items']['properties']['asset_name']['enum']
            return {'scenes':[{'asset_name':n,'literal_prompt':'The original moment.','object_ids':[],'checks':[]} for n in names]}
        original=copy.deepcopy(self.project['story'])
        self.project['story']['pages'][0]['imagePrompt']+=' The kit has a decorative purple open lid.'
        original=copy.deepcopy(self.project['story'])
        a=contract.compile_contract(self.project,'fixture',generate)
        count=len(calls);b=contract.compile_contract(self.project,'fixture',generate)
        self.assertEqual(a,b);self.assertEqual(count,len(calls))
        self.assertEqual(len(a['scenes']),4);self.assertEqual(self.project['story'],original)
        self.assertTrue(list(Path(self.project['book_root']).glob('scene-continuity/*/approved.json')))
        scene_audits=[p for p in calls if p.startswith('Independently audit these PRIVATE')]
        self.assertEqual(scene_audits,[])
        self.assertEqual(a['scenes']['pages/page-001.png']['literal_prompt'],self.project['book']['pages'][0]['scene_prompt'])

    def test_persistent_facts_survive_local_omission_and_end_at_the_right_page(self):
        self.install()
        self.project['scene_contract']['persistent_facts']=[{'id':'trapped_coin','object_ids':['bottle'],
            'requirement':'IF the bottle is visible, its coin remains inside.', 'from_page':1,'through_page':2,
            'source_pages':[1],'visibility':'conditional'},
            {'id':'vanished_bottle','object_ids':['bottle'],'requirement':'The vanished bottle is absent.',
             'from_page':3,'through_page':3,'source_pages':[3],'visibility':'absent'}]
        for n in [2,3]:
            self.project['scene_contract']['scenes'][f'pages/page-{n:03d}.png']={
                'asset_name':f'pages/page-{n:03d}.png','literal_prompt':'The friends smile.',
                'object_ids':[],'checks':[]}
        r=contract.effective_record(self.project,'pages/page-002.png')
        self.assertEqual(r['object_ids'],['bottle'])
        self.assertEqual([x['id'] for x in r['checks']],['persistent_trapped_coin'])
        r=contract.effective_record(self.project,'pages/page-003.png')
        self.assertEqual([x['id'] for x in r['checks']],['persistent_vanished_bottle'])
        self.assertIn('absent',contract.scene_brief(self.project,self.project['book']['pages'][2]))

    def test_coverage_cannot_pass_an_omission_or_nonexistent_fact(self):
        required=[{'id':'coin_contained','requirement':'The coin remains in the bottle.'}]
        value={'persistent_facts':[{'id':'bottle_closed','requirement':'The cap stays closed.'}]}
        for rows in [[],[{'requirement_id':'coin_contained','fact_ids':[], 'covered':True,'evidence':'Empty mapping.'}],
                [{'requirement_id':'coin_contained','fact_ids':['invented'], 'covered':True,'evidence':'Unknown mapping.'}]]:
            self.assertTrue(contract.coverage_issues({'coverage':rows},required,value))
        prompt,schema=contract.coverage_request(self.project,value,required)
        self.assertIn('contents',prompt)
        self.assertEqual(schema['properties']['coverage']['items']['properties']['fact_ids']['items']['enum'],['bottle_closed'])

    def test_cover_costume_default_does_not_import_page_one_prop_state(self):
        self.install()
        self.project['art_plan'] = {'cover_moment': {'pageNumber': 1}}
        self.project['scene_contract']['scenes']['cover.png'] = {
            'asset_name': 'cover.png', 'literal_prompt': 'Mira holds the recovered coin.',
            'object_ids': ['bottle'], 'checks': []}
        self.project['scene_contract']['persistent_facts'] = [{
            'id': 'trapped_coin', 'object_ids': ['bottle'],
            'requirement': 'The coin remains inside the bottle.', 'from_page': 1,
            'through_page': 2, 'source_pages': [1], 'visibility': 'conditional'}]
        # Historical projects keep reconstructing their original signatures.
        self.assertEqual(len(contract.effective_record(self.project, 'cover.png')['checks']), 1)
        self.project['render_settings']['scene_context_policy'] = 1
        self.assertEqual(contract.effective_record(self.project, 'cover.png')['checks'], [])
        self.assertEqual(len(contract.effective_record(self.project, 'pages/page-001.png')['checks']), 2)
        requests = []
        def audit(*args):
            requests.append(json.loads(args[2].split('\n')[-1]))
            return {'items': [{'id': 'design_bottle', 'observation': 'A blue bottle.',
                              'matches': True, 'uncertain': False}]}
        result = contract.review_scene_contract(self.project, {'name': 'cover.png', 'kind': 'scene'}, b'png', audit)
        self.assertTrue(result['accepted'])
        self.assertEqual([c['id'] for c in requests[0]['checks']], ['design_bottle'])
        self.assertIn('cover', requests[0]['temporal_context'])

    def test_shared_modifier_does_not_import_a_different_prop(self):
        objects = [{'id': 'rock_crevice', 'name': 'Rock Crevice'},
                   {'id': 'pedestal_rock', 'name': 'Pedestal Rock'},
                   {'id': 'stone_statue', 'name': 'Stone Statue'}]
        self.assertEqual(contract.mentioned_object_ids('Milo is inside the rock crevice.', objects, strict=True), ['rock_crevice'])
        self.assertEqual(contract.mentioned_object_ids('The shell is on the pedestal rock.', objects, strict=True), ['pedestal_rock'])
        self.assertEqual(contract.mentioned_object_ids('Milo touches the statue.', objects, strict=True), ['stone_statue'])
        self.assertEqual(contract.mentioned_object_ids('Smooth rocks on the bank.', objects, strict=True), [])
        self.assertEqual(contract.mentioned_object_ids('Rock crevice.', objects), ['rock_crevice', 'pedestal_rock'])

    def test_page_context_reaches_render_and_review_and_keeps_explicit_checks(self):
        self.install()
        self.project['render_settings']['scene_context_policy'] = 1
        self.assertIn('Story page 1 of 3', contract.scene_brief(self.project, self.project['book']['pages'][0]))
        seen = []
        def audit(*args):
            seen.append(json.loads(args[2].split('\n')[-1]))
            return {'items': [{'id': 'contents', 'observation': 'The bottle is empty.', 'matches': False, 'uncertain': False},
                              {'id': 'design_bottle', 'observation': 'Blue bottle.', 'matches': True, 'uncertain': False}]}
        r = contract.review_scene_contract(self.project, {'name': 'pages/page-001.png', 'kind': 'scene'}, b'png', audit)
        self.assertFalse(r['accepted'])
        self.assertIn('Story page 1 of 3', seen[0]['temporal_context'])
        self.assertIn('coin', r['retry_instructions'][0])

    def test_scene_style_does_not_reintroduce_plot_props_or_change_portraits(self):
        self.project['book']['visual_bible']['palette']='warm red, iridescent tones for the bubble, gentle blue'
        before=fixtures.story.reference_prompt(self.project,self.project['book']['characters'][0])
        original=fixtures.story.scene_style_text(self.project)
        self.project['render_settings'].update(scene_style_policy=1,scene_reference_policy=2)
        self.assertIn('for the bubble',original)
        self.assertNotIn('bubble',fixtures.story.scene_style_text(self.project))
        self.assertEqual(before,fixtures.story.reference_prompt(self.project,self.project['book']['characters'][0]))
        self.assertNotIn('style.png',fixtures.story.scene_references(self.project,self.project['book']['pages'][0]))
        self.assertEqual(['style.png'],fixtures.story.scene_references(self.project,self.project['book']['pages'][2]))

import copy
import importlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_book as fixtures

store=importlib.import_module('book_test_pack.assisted_store')
engine=importlib.import_module('book_test_pack.assisted_engine')
planning=importlib.import_module('book_test_pack.assisted_plan')


class AssistedCreatorTests(unittest.TestCase):
    setUp=fixtures.BookTests.setUp
    restore_module=fixtures.BookTests.restore_module

    def state(self):
        state=store.create({'page_count':3,'max_characters':3,'seed':731003})
        value=fixtures.package_fixture()
        for c,h in zip(value['production']['characters'],[100,50,65]):c['height_cm']=h
        return self.add(state,value)

    def add(self,state,value,metadata=None):
        intent=store.next_attempt(state)
        path=engine.directory(state['id'],state['current_stage'],intent['attempt'])/'candidate.json'
        fixtures.storage.write_json(path,value)
        return store.record_candidate(state['id'],state['current_stage'],intent['attempt'],path,metadata or {'content':value})

    def approve(self,state,candidate=None):
        candidate=candidate or engine.selected(state,state['current_stage'])
        record=store.decision(state,candidate,'approve','Test fixture decision; not a real book.')
        return engine.advance(state,candidate,record)

    def plan(self,state):
        book=fixtures.story.make_render_plan(**engine.package(state))
        return {'assets':[{'id':'garden','kind':'location','name':'Moonlit garden','appearance':'A walled garden with one round gate.','source_character':''}],
                'scenes':[{'page':i,'moment':s['scene_prompt'],'character_refs':s['character_ids'],'asset_refs':['garden']}
                          for i,s in enumerate([book['cover']]+book['pages'])],
                'continuity_notes':'The same garden remains throughout.'}

    def prepare(self):
        state=self.approve(self.state())
        return self.approve(self.add(state,self.plan(state)))

    def png(self,state):
        import torch
        tensor=torch.zeros((1,1024,1024,3));tensor[:,180:900,300:720,:]=.65
        intent=store.next_attempt(state)
        engine.save_image(state['id'],state['current_stage'],intent['attempt'],tensor,
                          json.dumps({'approved_reference_sha256':{},'method':'test_fixture'}))
        return store.read(state['id'])

    def test_candidate_does_not_approve_or_generate_next_stage(self):
        state=self.state()
        self.assertEqual(state['status'],'awaiting_review')
        self.assertEqual(state['current_stage'],'story')
        self.assertEqual(state['stages'][1]['candidates'],[])
        with self.assertRaisesRegex(ValueError,'approval first'):engine.approved(state,'story')
        restored=store.read(state['id'])
        self.assertEqual(state,restored)

    def test_assisted_cover_stage_carries_exact_title_typography_instruction(self):
        state=self.prepare()
        cover=store.stage(state,'cover.png')
        self.assertIn('"The Borrowed Moonlight"',cover['brief'])
        self.assertIn('readable lettering',cover['brief'])
        self.assertIn('display font',cover['brief'])
        self.assertIn('clear negative space',cover['brief'])

    def test_migrated_output_alias_preserves_references_and_comfy_preview(self):
        target=self.output/'generation/output/books';target.mkdir(parents=True)
        (self.output/'books').symlink_to(target,target_is_directory=True)
        state=self.prepare();state=self.png(state)
        candidate=engine.selected(state,state['current_stage'])
        file=store.candidate_path(state,candidate)
        self.assertTrue(file.is_relative_to(target))
        record=fixtures.storage.output_image_record(file)
        self.assertEqual((self.output/record['subfolder']/record['filename']).resolve(),file)
        state=self.approve(state)
        intent=store.next_attempt(state)
        _,refs,_=engine.image_inputs(state,store.stage(state),intent)
        self.assertTrue(refs)
        for ref in refs:
            self.assertTrue((store.root(state['id'])/ref['path']).is_file())

    def reference_budget_plan(self,state):
        value=self.plan(state)
        value['assets'] += [{'id':f'prop_{i}','kind':'prop','name':f'Object {i}',
                            'appearance':f'A small red object {i}.','source_character':''} for i in range(5)]
        value['scenes'][0]['asset_refs']=['garden']+[f'prop_{i}' for i in range(4)]
        value['scenes'][-1]['asset_refs']=['garden']+[f'prop_{i}' for i in range(5)]
        return value

    def test_six_reference_budget_matches_actual_renderer_inputs(self):
        state=self.approve(self.state());value=self.reference_budget_plan(state)
        planning.validate(engine.package(state),value)
        state=self.approve(self.add(state,value))
        while state['current_stage']!='cover.png':state=self.approve(self.png(state))
        intent=store.next_attempt(state)
        with patch.object(engine,'draft_json',return_value={'prompt':'A fixture scene.'}):
            _,refs,_=engine.image_inputs(state,store.stage(state),intent)
        self.assertEqual(len(refs),6)  # one shared cast + five prop/place images
        self.assertTrue(refs[0]['label'].startswith('Cast:'))
        self.assertEqual(len(store.stage(state)['cast_refs']),2)
        # The fixture's last page has no characters: all six assets are retained.
        state['current_stage']='pages/page-003.png';state['job']=None;state['status']='ready';store.save(state)
        intent=store.next_attempt(state)
        with patch.object(engine,'draft_json',return_value={'prompt':'An empty fixture garden.'}):
            _,refs,_=engine.image_inputs(state,store.stage(state),intent)
        self.assertEqual(len(refs),6)
        self.assertEqual([r['label'] for r in refs],['Moonlit garden']+[f'Object {i}' for i in range(5)])

    def test_reference_overflow_and_unknown_asset_have_distinct_errors(self):
        state=self.approve(self.state());value=self.reference_budget_plan(state)
        value['scenes'][0]['asset_refs'].append('prop_4')
        with self.assertRaisesRegex(ValueError,'7 reference images.*1 shared character image.*6 prop/place'):
            planning.validate(engine.package(state),value)
        value=self.reference_budget_plan(state);value['scenes'][0]['asset_refs']=['missing']
        with self.assertRaisesRegex(ValueError,'unknown prop/place references: missing'):
            planning.validate(engine.package(state),value)
        value=self.reference_budget_plan(state)
        value['assets'][-1].update(kind='location')
        with self.assertRaisesRegex(ValueError,'one location reference'):
            planning.validate(engine.package(state),value)

    def test_current_validation_refreshes_without_changing_candidate_or_approval(self):
        api=importlib.import_module('book_test_pack.assisted_web')
        state=self.approve(self.state());value=self.reference_budget_plan(state)
        old_error='A scene can use up to four known prop/place references.'
        state=self.add(state,value,{'content':value,'validation_error':old_error})
        before=(store.root(state['id'])/'creator.json').read_bytes()
        candidate=engine.selected(state,'plan');file=store.candidate_path(state,candidate);original=file.read_bytes()
        decisions=list((store.root(state['id'])/'creator/decisions').glob('*.json'))
        current=api.public_state(state)['stages'][1]['candidates'][0]
        self.assertIsNone(current['metadata']['validation_error'])
        self.assertEqual(current['metadata']['validation_error_at_generation'],old_error)
        self.assertEqual(file.read_bytes(),original)
        self.assertEqual((store.root(state['id'])/'creator.json').read_bytes(),before)
        self.assertEqual(list((store.root(state['id'])/'creator/decisions').glob('*.json')),decisions)

    def test_current_validation_keeps_real_errors_visible(self):
        api=importlib.import_module('book_test_pack.assisted_web')
        state=self.approve(self.state());value=self.reference_budget_plan(state)
        value['scenes'][0]['asset_refs']=['missing']
        state=self.add(state,value,{'content':value,'validation_error':'Old generic error'})
        error=api.public_state(state)['stages'][1]['candidates'][0]['metadata']['validation_error']
        self.assertIn('unknown prop/place references: missing',error)

    def test_reject_keeps_earlier_candidate_selectable_and_feedback_durable(self):
        state=self.state();first=engine.selected(state,'story');original=store.candidate_path(state,first).read_bytes()
        record=store.decision(state,first,'reject','The resolution contradicts page one.')
        state=self.add(state,dict(copy.deepcopy(first['metadata']['content'])))
        self.assertEqual(len(store.stage(state)['candidates']),2)
        state=self.approve(state,first)
        self.assertEqual(engine.approved(state,'story').read_bytes(),original)
        saved=json.loads((store.root(state['id'])/'creator/decisions'/f"{record['id']}.json").read_text())
        self.assertIn('contradicts',saved['feedback'])

    def test_stale_tabs_tampered_files_and_path_traversal_are_rejected(self):
        state=self.state()
        with self.assertRaises(store.Conflict):store.expect_revision(state,state['revision']-1)
        with self.assertRaises(ValueError):store.root('../../etc')
        candidate=engine.selected(state,'story');path=store.candidate_path(state,candidate)
        path.write_text('{}')
        with self.assertRaisesRegex(ValueError,'changed'):self.approve(state,candidate)

    def test_private_plan_keeps_contract_and_checks_cast_and_reference_budget(self):
        state=self.approve(self.state());package=engine.package(state);before=copy.deepcopy(package)
        plan=self.plan(state);planning.validate(package,plan)
        self.assertEqual(package,before)
        plan['scenes'][1]['character_refs'].append('pip')
        with self.assertRaisesRegex(ValueError,'match the approved story'):planning.validate(package,plan)
        plan=self.plan(state);plan['scenes'][1]['asset_refs']=['unknown']
        with self.assertRaisesRegex(ValueError,'known prop'):planning.validate(package,plan)

    def test_generated_name_formatting_is_repaired_without_guessing_identities(self):
        value=fixtures.package_fixture();value['story']['pages'][0]['charactersPresent']=['characters//Mira']
        fixed,repairs=engine.normalize_generated_cast(value)
        self.assertEqual(fixed['story']['pages'][0]['charactersPresent'],['Mira'])
        self.assertEqual(value['story']['pages'][0]['charactersPresent'],['characters//Mira'])
        self.assertEqual(len(repairs),1)
        value['story']['pages'][0]['charactersPresent']=['someone/Mira','Unknown']
        self.assertEqual(engine.normalize_generated_cast(value),(value,[]))

    def test_missing_main_character_prompt_is_repaired_from_canonical_production_design(self):
        value=fixtures.package_fixture();del value['story']['metadata']['mainCharacterDescriptivePrompt']
        fixed,repairs=engine.normalize_generated_metadata(value)
        self.assertEqual(fixed['story']['metadata']['mainCharacterDescriptivePrompt'],
                         value['production']['characters'][0]['appearance'])
        self.assertEqual(repairs[0]['field'],'metadata.mainCharacterDescriptivePrompt')
        self.assertNotIn('mainCharacterDescriptivePrompt',value['story']['metadata'])

    def test_saved_fenced_json_reply_is_reused_without_another_model_call(self):
        state=self.prepare();intent=store.next_attempt(state)
        path=engine.directory(state['id'],state['current_stage'],intent['attempt'])
        (path/'response.txt').write_text('```json\n{"prompt":"Change Image 1 to sunset."}\n```')
        with patch('urllib.request.urlopen',side_effect=AssertionError('Must reuse the saved reply')):
            result=engine.draft_json(state,state['current_stage'],intent['attempt'],'Rewrite prompt',{'type':'object'})
        self.assertEqual(result,{'prompt':'Change Image 1 to sunset.'})

    def test_interrupted_image_uses_saved_native_graph_without_recompiling_prompt(self):
        nodes=importlib.import_module('book_test_pack.assisted_nodes')
        state=self.prepare();intent=store.next_attempt(state)
        data={'saved-final':{'class_type':'BookAssistedSaveCandidate','inputs':{
              'session_id':state['id'],'stage_id':state['current_stage'],'attempt':intent['attempt'],'metadata':'{}'}}}
        fixtures.storage.write_json(engine.directory(state['id'],state['current_stage'],intent['attempt'])/'native.api.json',data)
        with patch.object(engine,'image_graph',side_effect=AssertionError('Must not recompile saved attempt')):
            result=nodes.BookAssistedStep().run(state['id'],state['current_stage'],intent['attempt'])
        self.assertEqual(result['expand'],data)
        self.assertEqual(result['result'],(['saved-final',0],))

    def test_end_to_end_fixture_exports_only_after_every_human_decision(self):
        state=self.prepare();before=engine.package(state)['story']
        with self.assertRaisesRegex(ValueError,'approval first'):engine.export_session(state)
        while state['status']!='exporting':state=self.approve(self.png(state))
        state=engine.export_session(state)
        self.assertEqual(state['status'],'complete')
        root=store.root(state['id'])/'export'
        self.assertEqual(json.loads((root/'story.json').read_text()),before)
        manifest=json.loads((root/'manifest.json').read_text())
        self.assertEqual(manifest['approval_mode'],'human')
        self.assertEqual(len(manifest['approvals']),len(state['stages']))
        self.assertTrue((root/'book.html').is_file())
        self.assertTrue((root/'contact-sheet.png').is_file())

    def test_native_graph_uses_exact_seed_and_only_current_approved_references(self):
        import folder_paths
        state=self.prepare()
        while store.stage(state)['kind']!='scene':state=self.approve(self.png(state))
        intent=store.next_attempt(state)
        folder_paths.get_full_path=lambda category,name:'/models/'+name
        with patch.object(engine,'draft_json',side_effect=lambda *a:{'prompt':a[3].split('\nOriginal prompt: ',1)[1].split('\nHuman feedback:',1)[0]}):
            result=engine.image_graph(state,intent);graph=result['expand']
        self.assertFalse(any(n['class_type']=='BookV2ReviewAsset' for n in graph.values()))
        refs=[n for n in graph.values() if n['class_type']=='BookAssistedReference']
        self.assertEqual(len(refs),2) # one two-character guide + the location
        text=next(n['inputs']['text'] for n in graph.values() if n['class_type']=='CLIPTextEncode')
        self.assertIn('Image 1: Cast: Mira, Pip',text)
        self.assertIn('Image 2: Moonlit garden',text)
        self.assertNotIn('Fern',text)
        self.assertEqual(next(n['inputs']['noise_seed'] for n in graph.values() if n['class_type']=='RandomNoise'),
                         fixtures.story.asset_seed(731003,'cover.png:1'))
        self.assertEqual(next(n['inputs']['steps'] for n in graph.values() if n['class_type']=='Flux2Scheduler'),8)

    def test_shutdown_between_file_save_and_state_update_recovers_without_rendering(self):
        state=self.state();candidate=engine.selected(state,'story')
        before=store.candidate_path(state,candidate).read_bytes()
        state['stages'][0]['candidates']=[];state['stages'][0]['selected']=None
        state['status']='generating';store.save(state)
        self.assertTrue(engine.recover_candidate(state,state['job']))
        recovered=store.read(state['id'])
        self.assertEqual(recovered['status'],'awaiting_review')
        self.assertEqual(store.candidate_path(recovered,engine.selected(recovered,'story')).read_bytes(),before)

    def test_edit_has_only_selected_source_and_preserves_originals(self):
        state=self.prepare();state=self.png(state)
        current=store.stage(state);first=engine.selected(state,current['id'])
        intent=store.next_attempt(state,'Remove the extra tree.',mode='edit',source_candidate=first['id'],
                                  prompt_override='Remove the rightmost tree from Image 1. Keep the rest unchanged.')
        prompt,refs,_=engine.image_inputs(state,current,intent)
        self.assertEqual(len(refs),1)
        self.assertEqual(refs[0]['sha256'],first['sha256'])
        self.assertTrue(prompt.startswith('Remove the rightmost'))
        self.assertTrue(store.candidate_path(state,first).exists())

    def test_feedback_receives_only_current_designs_and_actual_reference_numbers(self):
        state=self.prepare()
        while store.stage(state)['kind']!='scene':state=self.approve(self.png(state))
        current=store.stage(state)
        # Stand in for an already-approved current costume variant. The rewrite
        # must use this stage's design, not a fresh lookup of the base costume.
        store.stage(state,current['cast_refs'][0])['brief']='A blue coat with one badge on the left sleeve.'
        current['text']='The lantern remains attached to the boat while it glows.'
        before=copy.deepcopy(state)
        intent={'attempt':17,'feedback':'Keep the badge on the sleeve and the light on the lantern.'}
        with patch.object(engine,'draft_json',return_value={'prompt':'A corrected scene.'}) as writer:
            prompt,refs,_=engine.image_inputs(state,current,intent)
        request=writer.call_args.args[3]
        context=json.loads(request.split('\nScene context JSON:\n',1)[1])
        self.assertEqual(context['page_text'],current['text'])
        self.assertEqual(context['image_inputs'],[{'image':i+1,'role':r['label']} for i,r in enumerate(refs)])
        notes=context['reference_design_notes']
        self.assertEqual([n['stage'] for n in notes],current['references'])
        self.assertEqual(notes[0]['design_brief'],'A blue coat with one badge on the left sleeve.')
        self.assertNotIn('characters/fern.png',[n['stage'] for n in notes])
        self.assertEqual(prompt,'A corrected scene.')
        self.assertEqual(state,before)

    def test_edit_rewrite_does_not_turn_design_notes_into_additional_image_inputs(self):
        state=self.prepare()
        while store.stage(state)['kind']!='scene':state=self.approve(self.png(state))
        state=self.png(state);current=store.stage(state);candidate=engine.selected(state,current['id'])
        intent=store.next_attempt(state,'Keep the badge on the left sleeve.',mode='edit',source_candidate=candidate['id'])
        with patch.object(engine,'draft_json',return_value={'prompt':'Adjust the badge in Image 1.'}) as writer:
            _,refs,_=engine.image_inputs(state,current,intent)
        context=json.loads(writer.call_args.args[3].split('\nScene context JSON:\n',1)[1])
        self.assertEqual(context['image_inputs'],[{'image':1,'role':'Selected illustration to edit'}])
        self.assertEqual(refs[0]['sha256'],candidate['sha256'])
        self.assertGreater(len(context['reference_design_notes']),1)
        intent['prompt_override']='My exact edit wording.'
        with patch.object(engine,'draft_json',side_effect=AssertionError('Override must be verbatim')):
            prompt,_,_=engine.image_inputs(state,current,intent)
        self.assertEqual(prompt,intent['prompt_override'])


class AssistedAPITests(AssistedCreatorTests,unittest.IsolatedAsyncioTestCase):
    async def test_regenerate_api_with_empty_feedback_pins_corrected_scene_base(self):
        import hashlib
        from aiohttp import web
        from aiohttp.test_utils import TestClient,TestServer
        bases=importlib.import_module('book_test_pack.assisted_prompt_base')
        api=importlib.import_module('book_test_pack.assisted_web')
        state=self.prepare()
        while store.stage(state)['kind']!='scene':state=self.approve(self.png(state))
        state=self.png(state);current=store.stage(state)
        hashes={r:hashlib.sha256(engine.approved(state,r).read_bytes()).hexdigest() for r in current['references']}
        base=bases.install(state,current['id'],'The corrected full scene.',bases.signature(state,current,hashes),
                           reason='Fixture correction',source={'kind':'test_fixture'})
        state=store.read(state['id']);candidate=engine.selected(state,current['id'])
        original=store.candidate_path(state,candidate).read_bytes()
        app=web.Application();app.router.add_post('/api/{sid}',api.api)
        async with TestClient(TestServer(app)) as client:
            with patch.object(api,'launch') as launch:
                response=await client.post('/api/'+state['id'],headers={'X-Book-Creator':'1'},json={
                    'action':'regenerate','revision':state['revision'],'candidate_id':candidate['id'],
                    'feedback':'','prompt_override':''})
                self.assertEqual(response.status,200,await response.text())
                saved=store.read(state['id'])
                self.assertEqual(saved['job']['prompt_base'],base)
                self.assertEqual(saved['job']['feedback'],'')
                self.assertEqual(saved['job']['mode'],'fresh')
                self.assertEqual(store.candidate_path(saved,candidate).read_bytes(),original)
                launch.assert_called_once()

    async def test_resume_during_first_validation_cannot_submit_same_attempt_twice(self):
        import asyncio
        from unittest.mock import AsyncMock
        api=importlib.import_module('book_test_pack.assisted_web')
        state=store.create({'page_count':3,'max_characters':3,'seed':731003});sid=state['id']
        entered=asyncio.Event();release=asyncio.Event();calls=[]
        async def fake_mcp(name,args):
            calls.append(name)
            if name=='validate_workflow':
                entered.set();await release.wait();return {'valid':True}
            if name=='run_workflow':
                live=store.read(sid);intent=live['job']
                path=engine.directory(sid,'story',intent['attempt'])/'candidate.json'
                fixtures.storage.write_json(path,fixtures.package_fixture())
                store.record_candidate(sid,'story',intent['attempt'],path)
                return {'prompt_id':'fixture-job'}
            return {}
        with patch.object(api,'mcp',side_effect=fake_mcp),patch.object(api,'locate',new=AsyncMock(return_value=(None,None))):
            try:
                api.launch(sid)
                await asyncio.wait_for(entered.wait(),2)
                api.launch(sid,resume=True)
                await asyncio.sleep(0)
                self.assertEqual(calls.count('validate_workflow'),1)
            finally:
                release.set()
                await asyncio.gather(*list(api.ACTIVE.values()))
        self.assertEqual(calls.count('run_workflow'),1)
        self.assertEqual(store.read(sid)['status'],'awaiting_review')

    async def test_api_requires_same_origin_and_blocks_stale_approval(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient,TestServer
        api=importlib.import_module('book_test_pack.assisted_web')
        state=self.state();sid=state['id'];revision=state['revision']
        app=web.Application();app.router.add_post('/api/{sid}',api.api)
        async with TestClient(TestServer(app)) as client:
            response=await client.post('/api/'+sid,json={'action':'approve'})
            self.assertEqual(response.status,403)
            headers={'X-Book-Creator':'1'}
            body={'action':'approve','revision':revision,'candidate_id':'story:1'}
            with patch.object(api,'launch') as launch:
                response=await client.post('/api/'+sid,json=body,headers=headers)
                self.assertEqual(response.status,200,await response.text())
                self.assertEqual((await response.json())['current_stage'],'plan')
                launch.assert_called_once()
                response=await client.post('/api/'+sid,json=body,headers=headers)
                self.assertEqual(response.status,409)
                self.assertEqual(launch.call_count,1)

    async def test_publish_api_runs_resumable_publisher_after_export(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient,TestServer
        from unittest.mock import AsyncMock
        api=importlib.import_module('book_test_pack.assisted_web')
        state=self.prepare()
        while state['status']!='exporting':
            state=self.approve(self.png(state))
        state=engine.export_session(state);sid=state['id']
        public_url='https://onemorebook.pages.dev/book/test-publication'
        app=web.Application();app.router.add_post('/api/{sid}',api.api)
        async with TestClient(TestServer(app)) as client:
            with patch.object(api,'run_publisher',new=AsyncMock(return_value=public_url)) as publisher:
                response=await client.post('/api/'+sid,headers={'X-Book-Creator':'1'},json={
                    'action':'publish','revision':state['revision']})
                self.assertEqual(response.status,200,await response.text())
                self.assertEqual((await response.json())['publication']['url'],public_url)
                publisher.assert_awaited_once()
        saved=store.read(sid)
        self.assertEqual(saved['status'],'complete')
        self.assertEqual(saved['publication']['status'],'complete')


if __name__=='__main__':unittest.main()

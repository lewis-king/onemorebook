import copy
import importlib
import json
from pathlib import Path
from unittest.mock import patch
import unittest

import test_book as fixtures
from test_book import story, render, storage

ledger = importlib.import_module('book_test_pack.state_ledger')
assets = importlib.import_module('book_test_pack.state_assets')
quality = importlib.import_module('book_test_pack.state_quality')


def change_fixture():
    return {'id':'lost_fastening', 'character_id':'mira', 'part':'button', 'surface':'front of red coat',
            'before_state':'topmost button attached', 'after_state':'topmost button absent',
            'from_page':1,'through_page':2,'onset':'on_page',
            'evidence':[{'pageNumber':1,'quote':'Mira found a ribbon of moonlight in the garden.'}],
            'reference_edit':{'target_query':'a red button.','selection':'topmost',
                              'instruction':'Remove the upper front button; preserve all other fastenings'}}


class StateTests(unittest.TestCase):
    setUp = fixtures.BookTests.setUp
    restore_module = fixtures.BookTests.restore_module

    def plan(self):
        value = {'changes':[change_fixture()], 'detached_props':[], 'uncertain':False,'issues':[]}
        self.project['art_plan'] = {'version':1,'ledger':value,
            'pages':ledger.requirements(value,self.project['story'],self.project['book']['characters']),
            'cover':{'changes':[],'props':[]}}
        return value

    def test_routes_active_variants_without_changing_public_story_or_baseline(self):
        before = copy.deepcopy(self.project['story'])
        baseline = copy.deepcopy(self.project['book']['characters'])
        self.plan()
        specs = story.asset_specs(self.project)
        states = [s for s in specs if s['kind']=='state']
        self.assertEqual(len(states),1)
        pages = {s['name']:s for s in specs if s['kind']=='scene'}
        self.assertIn(states[0]['name'],pages['pages/page-001.png']['references'])
        self.assertIn(states[0]['name'],pages['pages/page-002.png']['references'])
        self.assertNotIn(states[0]['name'],pages['cover.png']['references'])
        self.assertEqual(before,self.project['story'])
        self.assertEqual(baseline,self.project['book']['characters'])

    def test_restored_and_offscreen_states_do_not_leak_to_other_pages(self):
        value=self.plan();value['changes'][0]['through_page']=1
        result=ledger.requirements(value,self.project['story'],self.project['book']['characters'])
        self.assertEqual(result[1]['changes'],['lost_fastening'])
        self.assertEqual(result[2]['changes'],[])
        value['changes'][0]['character_id']='pip'
        self.assertEqual(ledger.requirements(value,self.project['story'],self.project['book']['characters'])[1]['changes'],[])

    def test_fabricated_quote_and_invalid_interval_fail(self):
        value=self.plan();value['changes'][0]['evidence'][0]['quote']='This event was never written.'
        with self.assertRaises(ValueError):ledger.validate(value,self.project['story'],self.project['book']['characters'])
        value=self.plan();value['changes'][0].update(from_page=3,through_page=1)
        with self.assertRaises(ValueError):ledger.validate(value,self.project['story'],self.project['book']['characters'])

    def test_generated_evidence_is_bound_to_matching_prose_page(self):
        import jsonschema
        value=self.plan()
        change=value['changes'][0]
        change.update(operation='modify_existing',active_pages=[1,2])
        prompt,schema=ledger.request(self.project['story'],self.project['book']['characters'],
                                     constrain_evidence=True)
        jsonschema.validate(value,schema)
        # An art brief cannot masquerade as an event in the page text.
        bad=copy.deepcopy(value)
        bad['changes'][0]['evidence'][0]['quote']=self.project['story']['pages'][0]['imagePrompt']
        with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(bad,schema)
        bad=copy.deepcopy(value);bad['changes'][0]['evidence'][0]['pageNumber']=2
        with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(bad,schema)
        # Existing approved ledgers retain short exact quotation compatibility.
        old=copy.deepcopy(value);old['changes'][0]['evidence'][0]['quote']='ribbon of moonlight'
        ledger.validate(old,self.project['story'],self.project['book']['characters'])
        self.assertIn('imagePrompt is NOT',prompt)

    def test_invalid_evidence_reports_item_page_and_source(self):
        value=self.plan();fact=value['changes'][0]['evidence'][0]
        fact['quote']=self.project['story']['pages'][0]['imagePrompt']
        with self.assertRaisesRegex(ValueError,'lost_fastening on page 1.*illustration prompt'):
            ledger.validate(value,self.project['story'],self.project['book']['characters'])

    def test_removed_then_reworn_garment_routes_one_variant_with_a_gap(self):
        value=self.plan();change=value['changes'][0]
        change.update(operation='add_clothing',from_page=1,through_page=3,active_pages=[1,3],
                      part='shoulders',surface='upper back',before_state='ordinary coat',
                      after_state='a green scarf over the coat')
        for page in self.project['story']['pages']:
            page['charactersPresent']=['Mira'];page['isMainCharacterPresent']=True
        before=copy.deepcopy(self.project['story'])
        coverage=ledger.requirements(value,self.project['story'],self.project['book']['characters'])
        self.assertEqual(coverage[1]['changes'],['lost_fastening'])
        self.assertEqual(coverage[2]['changes'],[])
        self.assertEqual(coverage[3]['changes'],['lost_fastening'])
        self.project['art_plan']['pages']=coverage
        # Use corresponding internal scenes for reference routing.
        for page in self.project['book']['pages']:page['character_ids']=['mira']
        variants=ledger.variant_specs(self.project)
        self.assertEqual(len(variants),1)
        self.assertEqual(variants[0]['edit_mode'],'clothing_addition')
        self.assertEqual(before,self.project['story'])
        change['active_pages']=[1,2]
        with self.assertRaises(ValueError):ledger.validate(value,self.project['story'],self.project['book']['characters'])

    def test_added_clothes_use_reviewed_reference_edit_without_existing_part_mask(self):
        self.plan();self.project['art_plan']['ledger']['changes'][0].update(operation='add_clothing')
        self.project['render_settings'].update(renderer='flux2',**render.FLUX_MODELS,flux_steps=28,flux_guidance=4)
        spec=next(s for s in story.asset_specs(self.project) if s['kind']=='state')
        for attempt in (1,2):
            graph=render.expand_attempt(self.project,spec,attempt,'Add the scarf.',correction_attempt=1)['expand']
            kinds=[n['class_type'] for n in graph.values()]
            self.assertIn('BookV2LoadReference',kinds)
            self.assertIn('BookV2ReviewAsset',kinds)
            self.assertNotIn('BookV2LoadStateEdit',kinds)
            self.assertNotIn('SetLatentNoiseMask',kinds)
            self.assertNotIn('ImageCompositeMasked',kinds)

    def test_added_garment_preparation_never_measures_an_absent_item(self):
        self.plan();self.project['art_plan']['ledger']['changes'][0].update(operation='add_clothing')
        with patch('book_test_pack.storage.valid_asset',return_value=True),patch.object(assets,'measure_part') as measure:
            assets.prepare_details(self.project)
        measure.assert_not_called()

    def test_addition_audit_cannot_claim_protected_pixels_or_pass_a_missing_garment(self):
        from PIL import Image
        self.plan();self.project['art_plan']['ledger']['changes'][0].update(operation='add_clothing')
        self.project['config']['ollama_url']='http://example.invalid'
        self.project['render_settings']['review_model']='fixture-model'
        spec=next(s for s in story.asset_specs(self.project) if s['kind']=='state')
        png=assets.png_bytes(Image.new('RGB',(64,64),'red'))
        path=storage.asset_path(self.project,spec['references'][0]);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(png)
        for matches in (True,False):
            report={'items':[{'id':'lost_fastening','observation':'Fixture clothing observation',
                             'visibility':'visible','matches':matches}],
                    'uncertain':False,'issues':[] if matches else ['Missing new scarf.'],'retry_instructions':[]}
            with patch.object(quality,'observe_surface',return_value={'observation':{}}),patch.object(assets,'variant_inputs',side_effect=AssertionError('No mask for addition')):
                result=quality.review_states(self.project,spec,png,lambda *a,**k:report)
            self.assertEqual(result['accepted'],matches)
            self.assertIsNone(result['outside_pixels_unchanged'])

    def test_detached_new_garment_requires_approved_worn_variant(self):
        self.plan();self.project['art_plan']['ledger']['changes'][0].update(operation='add_clothing')
        prop={'id':'scarf_on_peg','source_change_id':'lost_fastening','description':'The same green scarf.'}
        with patch('book_test_pack.storage.valid_asset',return_value=False):
            with self.assertRaisesRegex(ValueError,'approved worn reference'):
                assets.prop_reference(self.project,prop)
    def test_overlapping_independent_changes_get_a_combined_variant(self):
        value=self.plan();second=copy.deepcopy(value['changes'][0]);second.update(id='stained_ear',part='ear')
        value['changes'].append(second)
        self.project['art_plan']['pages']=ledger.requirements(value,self.project['story'],self.project['book']['characters'])
        variants=ledger.variant_specs(self.project)
        self.assertEqual(len(variants),1)
        self.assertEqual(len(variants[0]['changes']),2)

    def test_unsafe_state_names_are_rejected(self):
        for name in ['states/../../story.png','states/mira.png','states/mira-12345678901g.png']:
            with self.assertRaises(ValueError):story.safe_asset_name(name)

    def test_ambiguous_single_part_is_rejected_and_position_selection_is_stable(self):
        boxes=[{'bbox':[10,50,30,70],'score':.8},{'bbox':[10,10,30,30],'score':.6}]
        self.assertEqual(assets.select_boxes(boxes,'topmost')[0]['bbox'],[10,10,30,30])
        with self.assertRaises(ValueError):assets.select_boxes(boxes,'single')
        with self.assertRaises(ValueError):assets.select_boxes([{'bbox':[0,0,10,10],'score':.2}],'topmost')

    def test_mask_protects_neighbouring_fastening(self):
        import numpy as np
        proposals=[{'bbox':[40,40,60,60],'score':.9},{'bbox':[40,64,60,84],'score':.8}]
        mask=np.asarray(assets.region_mask((128,128),[proposals[0]],proposals))
        self.assertTrue(mask[45:55,45:55].all())
        self.assertFalse(mask[64:84,40:60].any())
        self.assertFalse(mask[:20].any())

    def test_actual_button_proposals_do_not_select_the_enclosing_waistcoat(self):
        import numpy as np
        proposals=json.loads((Path(__file__).parent/'fixtures/state-button-proposals.json').read_text())['proposals']
        selected=assets.select_boxes(proposals,'topmost')
        self.assertLess(selected[0]['bbox'][2]-selected[0]['bbox'][0],40)
        self.assertGreater(selected[0]['bbox'][1],600)
        mask=np.asarray(assets.region_mask((1024,1024),selected,proposals))
        self.assertTrue(mask[615:630,475:490].all())
        self.assertFalse(mask[657:685,467:495].any())
        self.assertLess(np.count_nonzero(mask),5000)

    def test_local_surface_restoration_preserves_other_fastening_and_all_unmasked_pixels(self):
        import numpy as np
        import torch
        from PIL import Image,ImageDraw
        nodes=importlib.import_module('book_test_pack.nodes')
        image=Image.new('RGB',(100,100),(40,85,145));draw=ImageDraw.Draw(image)
        draw.ellipse((46,26,52,32),fill=(8,12,20));draw.ellipse((46,66,52,72),fill=(8,12,20))
        pixels=np.array(image);mask=np.zeros((100,100),dtype=np.float32);mask[24:35,44:55]=1
        result=nodes.BookV2RestoreLocalSurface().restore(torch.from_numpy(pixels.astype(np.float32)/255)[None],torch.from_numpy(mask)[None])[0]
        restored=(result[0].numpy()*255).round().astype(np.uint8)
        self.assertTrue(np.array_equal(restored[mask==0],pixels[mask==0]))
        self.assertGreater(restored[29,49,2],120)
        self.assertTrue(np.array_equal(restored[69,49],pixels[69,49]))

    def test_supported_fill_does_not_pull_adjacent_fur_into_blue_cloth(self):
        import numpy as np
        import torch
        nodes = importlib.import_module('book_test_pack.nodes')
        pixels = np.full((100,100,3), (245,230,190), dtype=np.uint8)
        pixels[:,50:] = (40,85,145)
        pixels[46:53,50:55] = (8,12,20)
        selected = np.zeros((100,100), dtype=np.float32);selected[44:55,50:58] = 1
        support = np.zeros_like(selected);support[:,50:] = 1
        image = torch.from_numpy(pixels.astype(np.float32)/255)[None]
        result = nodes.BookV2RestoreLocalSurfaceWithSupport().restore(
            image, torch.from_numpy(selected)[None], torch.from_numpy(support)[None])[0]
        restored = (result[0].numpy()*255).round().astype(np.uint8)
        self.assertTrue(np.array_equal(restored[selected==0],pixels[selected==0]))
        self.assertLess(np.abs(restored[selected>0].astype(int)-[40,85,145]).max(),8)

    def test_supported_fill_rejects_wrong_surface_missing_material_and_misalignment(self):
        import torch
        nodes = importlib.import_module('book_test_pack.nodes')
        restore = nodes.BookV2RestoreLocalSurfaceWithSupport().restore
        image = torch.zeros((1,100,100,3));mask = torch.zeros((1,100,100));mask[:,45:50,45:50] = 1
        for support in (torch.zeros_like(mask), mask.clone(), torch.ones((1,50,50))):
            with self.subTest(shape=support.shape):
                with self.assertRaises(ValueError):restore(image,mask,support)
        with self.assertRaises(ValueError):restore(image,torch.ones_like(mask),torch.ones_like(mask))
        image[0,0,0,0] = float('nan')
        with self.assertRaises(ValueError):restore(image,mask,torch.ones_like(mask))

    def test_blind_material_results_reject_actual_restored_buttons_and_ambiguous_dots(self):
        material=importlib.import_module('book_test_pack.material')
        cases=json.loads((Path(__file__).parent/'fixtures/button-material-calibration.json').read_text())
        for case in cases:
            with self.subTest(case=case['name']):
                self.assertEqual(material.clear_replacement_material(case['result']),case['expected_material_approval'])

    def test_material_veto_survives_a_focused_state_pass(self):
        material=importlib.import_module('book_test_pack.material')
        report={'checks':{'scene_matches':True},'issues':[],'uncertain':False}
        rejected={'accepted':False,'patches':[{'change_id':'lost_button','accepted':False,
                   'result':{'kind':'sewing_button','observed_shape':'a round solid disc'}}]}
        material.apply_material_review(report,rejected)
        quality.apply_state_review(report,{'accepted':True})
        self.assertFalse(report['checks']['scene_matches'])
        self.assertTrue(report['issues'])

    def test_targeted_failure_vetoes_broad_pass_and_success_cannot_clear_failure(self):
        broad={'checks':{'scene_matches':True},'issues':[],'uncertain':False}
        quality.apply_state_review(broad,{'accepted':False,'issues':['The missing button reappeared.']})
        self.assertFalse(broad['checks']['scene_matches'])
        quality.apply_state_review(broad,{'accepted':True,'issues':[]})
        self.assertFalse(broad['checks']['scene_matches'])
        self.assertEqual(broad['issues'],['The missing button reappeared.'])

    def test_state_edits_mask_sampling_and_restore_pixels_on_every_retry(self):
        self.plan()
        self.project['render_settings'].update(renderer='flux2',**render.FLUX_MODELS,flux_steps=28,flux_guidance=4)
        spec=next(s for s in story.asset_specs(self.project) if s['kind']=='state')
        graph=render.expand_attempt(self.project,spec,2,'Remove that front button.',correction_attempt=1)['expand']
        kinds=[n['class_type'] for n in graph.values()]
        self.assertIn('BookV2LoadStateEdit',kinds)
        self.assertIn('SetLatentNoiseMask',kinds)
        self.assertIn('ImageCompositeMasked',kinds)
        self.assertNotIn('BookV2LoadCandidate',kinds)
        prepared=next(k for k,n in graph.items() if n['class_type']=='BookV2LoadStateEdit')
        composite=next(n for n in graph.values() if n['class_type']=='ImageCompositeMasked')
        self.assertEqual(composite['inputs']['destination'],[prepared,0])
        encoded=[n for n in graph.values() if n['class_type']=='VAEEncode']
        self.assertTrue(any(n['inputs']['pixels']==[prepared,2] for n in encoded))

    def test_saved_edit_recipe_changes_state_and_scene_signatures_without_changing_baseline(self):
        self.plan()
        plan={'desired_region':'Blue cloth with loose threads.','preserved_features':'Lower button.',
              'inventory_after':'One lower button.','evidence':'Fixture measured baseline.','uncertain':False}
        self.project['state_edits']={'lost_fastening':{'hash':'first','plan':plan}}
        first={s['name']:s['signature'] for s in story.asset_specs(self.project)}
        self.project['state_edits']['lost_fastening']['hash']='changed'
        second={s['name']:s['signature'] for s in story.asset_specs(self.project)}
        self.assertEqual(first['characters/mira.png'],second['characters/mira.png'])
        self.assertNotEqual(first['pages/page-001.png'],second['pages/page-001.png'])
        state=next(n for n in first if n.startswith('states/'))
        self.assertNotEqual(first[state],second[state])

    def test_current_state_review_uses_paint_recipe_and_requires_pixel_proof(self):
        from PIL import Image
        broad=importlib.import_module('book_test_pack.quality')
        self.plan()
        self.project['render_settings']['quality_required']=True
        self.project['art_plan']['ledger']['changes'][0]['after_state']='topmost button missing'
        self.project['state_edits']={'lost_fastening':{'hash':'recipe','plan':{
            'desired_region':'Red cloth with loose thread.', 'preserved_features':'Lower button.',
            'inventory_after':'One lower button.', 'evidence':'Measured fixture.', 'uncertain':False}}}
        spec=next(s for s in story.asset_specs(self.project) if s['kind']=='state')
        expected=broad.expected_scene(self.project,spec)[1]
        self.assertIn('One lower button.',expected)
        self.assertNotIn('Remove the upper',expected)
        png=assets.png_bytes(Image.new('RGB',(1024,1024),'red'))
        baseline=storage.asset_path(self.project,spec['references'][0]);baseline.parent.mkdir(parents=True)
        baseline.write_bytes(png)
        mask=Image.new('L',(1024,1024));mask.paste(255,(480,480,510,510))
        with patch.object(storage,'valid_asset',return_value=True),patch.object(assets,'variant_inputs',return_value=(Image.open(baseline),mask)):
            context=quality.protected_review_context(self.project,spec,png)
            self.assertTrue(context['proof']['outside_pixels_unchanged'])
            altered=Image.open(baseline).copy();altered.putpixel((0,0),(0,0,0))
            self.assertIsNone(quality.protected_review_context(self.project,spec,assets.png_bytes(altered)))
        with patch.object(storage,'valid_asset',return_value=False):
            self.assertIsNone(quality.protected_review_context(self.project,spec,png))

    def test_scene_render_uses_current_material_once_for_single_and_shared_cast(self):
        self.plan()
        self.project['render_settings'].update(renderer='flux2',**render.FLUX_MODELS,flux_steps=28,
            flux_guidance=4,state_scene_policy=1,reference_strategy='cast_guide')
        for character,height in zip(self.project['book']['characters'],(110,50,55)):
            character['height_cm']=height
        self.project['state_edits']={'lost_fastening':{'hash':'recipe','plan':{
            'desired_region':'Red cloth with fine sewing threads.','preserved_features':'Lower button.',
            'inventory_after':'One lower button.','evidence':'Measured source.','uncertain':False}}}
        original=copy.deepcopy(self.project['story'])
        for name in ('pages/page-001.png','pages/page-002.png'):
            spec=next(s for s in story.asset_specs(self.project) if s['name']==name)
            for attempt in (1,2):
                graph=render.expand_attempt(self.project,spec,attempt,'',correction_attempt=1 if attempt==2 else None)['expand']
                text=next(n['inputs']['text'] for n in graph.values() if n['class_type']=='CLIPTextEncode')
                self.assertEqual(text.count('Current appearance in this story moment:'),1)
                self.assertIn('Red cloth with fine sewing threads.',text)
                self.assertIn('Current inventory: One lower button.',text)
                self.assertNotIn('Remove the upper front button',text)
        self.assertEqual(original,self.project['story'])

    def test_legacy_state_briefs_remain_stable_and_restored_pages_have_no_recipe(self):
        value=self.plan();scene=self.project['book']['pages'][0]
        legacy=ledger.state_brief(self.project,scene)
        self.assertIn('Reference edit: Remove the upper front button',legacy)
        self.project['state_edits']={'lost_fastening':{'hash':'new','plan':{'desired_region':'new material'}}}
        self.assertEqual(legacy,ledger.state_brief(self.project,scene))
        self.project['render_settings']['state_scene_policy']=1
        value['changes'][0]['through_page']=1
        self.project['art_plan']['pages']=ledger.requirements(value,self.project['story'],self.project['book']['characters'])
        self.assertEqual('',ledger.state_brief(self.project,self.project['book']['pages'][1]))

    def test_scene_policy_two_scopes_portrait_preservation_without_changing_old_prompts(self):
        self.plan()
        plan={'desired_region':'Red cloth with fine sewing threads.',
              'inventory_after':'One lower button.',
              'preserved_features':'His pose, background, face and lower button.'}
        self.project['state_edits']={'lost_fastening':{'hash':'recipe','plan':plan}}
        scene=self.project['book']['pages'][0]
        original=copy.deepcopy(self.project['story'])
        self.project['render_settings']['state_scene_policy']=1
        old=ledger.state_brief(self.project,scene)
        self.assertIn('Preserve: His pose, background, face and lower button.',old)
        self.project['render_settings']['state_scene_policy']=2
        new=ledger.state_brief(self.project,scene)
        self.assertNotIn('His pose',new)
        self.assertNotIn('background',new)
        self.assertIn('Current inventory: One lower button.',new)
        self.assertIn('Red cloth with fine sewing threads.',new)
        self.assertEqual(plan['preserved_features'],'His pose, background, face and lower button.')
        self.assertEqual(original,self.project['story'])
        self.project['render_settings']['state_scene_policy']=1
        self.assertEqual(old,ledger.state_brief(self.project,scene))

    def test_state_pixel_reuse_reads_prepared_recipe_and_rejects_changed_instructions(self):
        import hashlib
        import torch
        from test_quality import visual_report
        self.plan()
        self.project['book_root']=str(self.output/'books/state-reuse')
        self.project['render_root']=str(Path(self.project['book_root'])/'renders/old')
        self.project['render_settings'].update(quality_required=True,qa_version='old')
        storage.write_json(Path(self.project['render_root'])/'project.json',self.project)
        self.project['state_edits']={'lost_fastening':{'hash':'old-hash','plan':{
            'desired_region':'Red cloth with thread.','preserved_features':'Lower button.',
            'inventory_after':'One lower button.','evidence':'Measured fixture.','uncertain':False}}}
        storage.write_json(Path(self.project['render_root'])/'prepared-state-project.json',self.project)
        target=copy.deepcopy(self.project)
        target['render_root']=str(Path(target['book_root'])/'renders/new')
        target['render_settings']['qa_version']='new'
        target['state_edits']['lost_fastening']['hash']='new-provenance'
        pixels=torch.rand((1,1024,1024,3),generator=torch.Generator().manual_seed(1))
        for project in (self.project,target):
            for spec in story.asset_specs(project):
                if spec['kind'] not in ('style','character') and project is target:continue
                if spec['kind'] == 'scene':continue
                png=storage.image_bytes(spec,pixels)
                report=visual_report(project,spec)
                report.update(png_sha256=hashlib.sha256(png).hexdigest(),seed=spec['seed'],prompt=spec['prompt'])
                storage.publish_reviewed_asset(project,spec,png,report)
        spec=next(s for s in story.asset_specs(target) if s['kind']=='state')
        self.assertTrue(storage.reuse_candidate_pixels(target,spec))
        self.assertFalse(storage.approval_path(target,spec).exists())
        changed=copy.deepcopy(target);changed['render_root']=str(Path(target['book_root'])/'renders/changed')
        changed['state_edits']['lost_fastening']['plan']['desired_region']='Red fabric with an open tear.'
        for baseline in (s for s in story.asset_specs(changed) if s['kind'] in ('style','character')):
            import shutil
            destination=storage.asset_path(changed,baseline['name']);destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(storage.asset_path(target,baseline['name']),destination)
            approval=storage.approval_path(changed,baseline);approval.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(storage.approval_path(target,baseline),approval)
        changed_spec=next(s for s in story.asset_specs(changed) if s['kind']=='state')
        self.assertFalse(storage.reuse_candidate_pixels(changed,changed_spec))

    def test_unaffected_page_reuses_pixels_after_state_policy_but_changed_prop_does_not(self):
        import hashlib,torch
        from test_quality import visual_report
        source=copy.deepcopy(self.project)
        source['book_root']=str(self.output/'books/unaffected-scene')
        source['render_root']=str(Path(source['book_root'])/'renders/old')
        source['render_settings'].update(quality_required=True,qa_version='old')
        storage.write_json(Path(source['render_root'])/'project.json',source)
        self.plan()
        target=copy.deepcopy(self.project)
        target['book_root']=source['book_root'];target['render_root']=str(Path(source['book_root'])/'renders/new')
        target['render_settings'].update(quality_required=True,qa_version='new',state_plan_version=1,
            state_plan_hash='new-plan',state_edit_policy=2,state_scene_policy=1)
        pixels=torch.rand((1,1024,1024,3),generator=torch.Generator().manual_seed(4))
        for project in (source,target):
            for spec in story.asset_specs(project):
                if spec['name']!='style.png' and not (project is source and spec['name']=='pages/page-003.png'):continue
                png=storage.image_bytes(spec,pixels);report=visual_report(project,spec)
                report.update(png_sha256=hashlib.sha256(png).hexdigest(),seed=spec['seed'],prompt=spec['prompt'])
                storage.publish_reviewed_asset(project,spec,png,report)
        spec=next(s for s in story.asset_specs(target) if s['name']=='pages/page-003.png')
        with_prop=copy.deepcopy(spec);with_prop['props']=[{'id':'new-visible-object'}]
        self.assertFalse(storage.reuse_candidate_pixels(target,with_prop))
        self.assertTrue(storage.reuse_candidate_pixels(target,spec))
        self.assertFalse(storage.approval_path(target,spec).exists())
        self.assertFalse(storage.asset_path(target,spec['name']).exists())

    def test_plan_resume_uses_saved_model_output_and_preserves_prose(self):
        self.project['book_root']=str(self.output/'books/test')
        self.project['config']['ollama_url']='http://example.invalid'
        value={'changes':[],'detached_props':[],'uncertain':False,'issues':[]}
        audit={'valid':True,'issues':[],'evidence':'Unchanged clothes throughout.'}
        before=copy.deepcopy(self.project['story'])
        with patch('book_test_pack.quality.json_model',side_effect=[value,audit]) as model:
            first=ledger.compile_plan(self.project,'test-model')
            second=ledger.compile_plan(self.project,'test-model')
        self.assertEqual(first,second)
        self.assertEqual(model.call_count,2)
        self.assertEqual(before,self.project['story'])

    def test_state_review_revision_uses_new_records_and_preserves_old_results(self):
        self.project['book_root']=str(self.output/'books/scope-review')
        self.project['config']['ollama_url']='http://example.invalid'
        value={'changes':[],'detached_props':[],'uncertain':False,'issues':[]}
        audit={'valid':True,'issues':[],'evidence':'Only ordinary objects move.',
               'body_or_clothing_changes':[],'ordinary_object_events':['A basket is carried.']}
        before=copy.deepcopy(self.project['story'])
        with patch('book_test_pack.quality.json_model',side_effect=[value,audit,value,audit]) as model:
            with patch.object(ledger,'STATE_REVIEW_VERSION',1):
                old=ledger.compile_plan(self.project,'test-model')
            paths=list((Path(self.project['book_root'])/'visual-state').rglob('*.json'))
            saved={p:p.read_bytes() for p in paths}
            with patch.object(ledger,'STATE_REVIEW_VERSION',2):
                current=ledger.compile_plan(self.project,'test-model')
                resumed=ledger.compile_plan(self.project,'test-model')
        self.assertNotEqual(old['source_hash'],current['source_hash'])
        self.assertEqual(current,resumed)
        self.assertEqual(current['review_version'],2)
        self.assertEqual(model.call_count,4)
        self.assertEqual(before,self.project['story'])
        self.assertTrue(all(p.read_bytes()==data for p,data in saved.items()))

    def test_new_resize_policy_reuses_unrepaired_pixels_but_not_old_cutouts(self):
        import hashlib,torch
        from test_quality import visual_report
        for repaired in (False,True):
            with self.subTest(repaired=repaired):
                source=copy.deepcopy(self.project)
                source['book_root']=str(self.output/f'books/resize-reuse-{repaired}')
                source['render_root']=str(Path(source['book_root'])/'renders/old')
                source['render_settings'].update(quality_required=True,qa_version='old')
                storage.write_json(Path(source['render_root'])/'project.json',source)
                target=copy.deepcopy(source)
                target['render_root']=str(Path(source['book_root'])/'renders/new')
                target['render_settings'].update(qa_version='new',scale_repair_policy=2)
                pixels=torch.rand((1,1024,1024,3),generator=torch.Generator().manual_seed(5))
                for project in (source,target):
                    for spec in story.asset_specs(project):
                        if spec['name']!='style.png' and not (project is source and spec['name']=='pages/page-003.png'):continue
                        png=storage.image_bytes(spec,pixels);report=visual_report(project,spec)
                        report.update(png_sha256=hashlib.sha256(png).hexdigest(),seed=spec['seed'],prompt=spec['prompt'])
                        if repaired and spec['kind']=='scene':report['preserved_geometry']={'mira':{'identity_source':'verified_preserved_cutout'}}
                        storage.publish_reviewed_asset(project,spec,png,report)
                spec=next(s for s in story.asset_specs(target) if s['name']=='pages/page-003.png')
                self.assertEqual(storage.reuse_candidate_pixels(target,spec),not repaired)
                self.assertFalse(storage.approval_path(target,spec).exists())

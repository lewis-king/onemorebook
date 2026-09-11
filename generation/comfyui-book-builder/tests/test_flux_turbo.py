import copy
import importlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import test_book as fixtures
class FluxTurboTests(unittest.TestCase):
    setUp = fixtures.BookTests.setUp
    restore_module = fixtures.BookTests.restore_module

    def prepare(self):
        self.project['render_settings'].update(renderer='flux2', reference_strategy='cast_guide', review_model='gemma4:31b')
        for c, height in zip(self.project['book']['characters'], [110, 50, 55]):
            c['height_cm'] = height
        page = self.project['book']['pages'][1]
        page['scene_prompt'] = 'Mira carries the lamp. Pip holds its handle while Fern points toward the gate.'
        return next((s for s in fixtures.story.asset_specs(self.project) if s['name'] == 'pages/page-002.png'))

    def test_opt_in_compilation_reaches_actual_render_text(self):
        spec = self.prepare()
        self.project['render_settings'].update(fixtures.render.FLUX_MODELS)
        self.project['render_settings'].update(flux_steps=28, flux_guidance=4, compact_prompt_policy=1)
        compiler = importlib.import_module('book_test_pack.flux_prompt')
        with patch.object(compiler, 'compile_prompt', return_value='VERIFIED COMPACT TEXT') as call:
            graph = fixtures.render.expand_attempt(self.project, spec, 1)['expand']
        texts = [n['inputs']['text'] for n in graph.values() if n['class_type'] == 'CLIPTextEncode']
        self.assertEqual(texts, ['VERIFIED COMPACT TEXT'])
        self.assertIn('carries the lamp', call.call_args.args[2])
        self.assertEqual(call.call_args.args[3], 1)

    def test_single_actor_uses_compiler_with_one_portrait_and_retry_context(self):
        self.prepare()
        self.project['book']['pages'][1]['character_ids'] = ['mira']
        self.project['render_settings'].update(fixtures.render.FLUX_MODELS)
        self.project['render_settings'].update(flux_steps=28,flux_guidance=4,compact_prompt_policy=7,scene_reference_policy=2)
        spec=next(s for s in fixtures.story.asset_specs(self.project) if s['name']=='pages/page-002.png')
        compiler=importlib.import_module('book_test_pack.flux_prompt')
        with patch.object(compiler,'compile_prompt',return_value='SINGLE ACTOR CURRENT MOMENT') as call:
            graph=fixtures.render.expand_attempt(self.project,spec,2,feedback='Keep her hand on the lamp')['expand']
        self.assertEqual([n['inputs']['text'] for n in graph.values() if n['class_type']=='CLIPTextEncode'],
                         ['SINGLE ACTOR CURRENT MOMENT'])
        self.assertEqual(call.call_args.args[3],1)
        self.assertEqual(call.call_args.kwargs['feedback'],'Keep her hand on the lamp')
        self.assertFalse(any(n['class_type']=='BookV2ScaleGuide' for n in graph.values()))

    def test_structured_compiler_rejects_bad_rewrite_before_sampling(self):
        compiler,spec,generate,calls=self.compiler_fixture(semantic_ok=False)
        self.project['render_settings']['compact_prompt_policy']=7
        with patch.object(compiler,'scene_source',return_value={'page_prose':'Mira carries one lamp.'}):
            with self.assertRaisesRegex(ValueError,'before spending image retries'):
                compiler.compile_prompt(self.project,spec,'LEGACY CONFLICTING PROMPT',1,generate)
        self.assertNotIn('LEGACY CONFLICTING PROMPT',calls[0])
        self.assertIn('Mira carries one lamp.',calls[0])

    def test_empty_scene_uses_style_reference_without_inventing_cast_or_heights(self):
        compiler,_,generate,_=self.compiler_fixture()
        self.project['render_settings'].update(compact_prompt_policy=10,scene_reference_policy=2)
        spec=next(s for s in fixtures.story.asset_specs(self.project) if s['name']=='pages/page-003.png')
        def empty(url,model,prompt,schema,**kw):
            value=generate(url,model,prompt,schema,**kw)
            if 'actors' in value:value['actors']={}
            return value
        result=compiler.compile_prompt(self.project,spec,'The empty garden.',1,empty)
        self.assertIn('unpopulated picture-book scene',result)
        self.assertIn('Image 1 supplies style and palette',result)
        self.assertNotIn('physical heights',result)
        self.assertNotIn('figure 1 from left',result)

    def test_affirmative_scene_keeps_action_first_and_changed_surface(self):
        compiler,spec,generate,_=self.compiler_fixture()
        self.project['render_settings']['compact_prompt_policy']=11
        change={'id':'scarf_off','character_id':'pip','after_state':'not wearing the blue scarf','surface':'neck'}
        self.project['art_plan']={'ledger':{'changes':[change]},'cover':{'changes':[],'props':[]},
                                 'pages':{'2':{'changes':['scarf_off'],'props':[]}}}
        def positive(*args,**kw):
            value=generate(*args,**kw)
            for cid,actor in value.get('actors',{}).items():
                actor['current_surface']='exposed grey neck fur' if cid=='pip' else ''
            return value
        with patch.object(compiler,'scene_source',return_value={'page_prose':'Pip shares the lamp after taking off his scarf.'}):
            result=compiler.compile_prompt(self.project,spec,'old brief',1,positive)
        self.assertLess(result.index('shares the light'),result.index('moonlit garden'))
        self.assertIn('exposed grey neck fur',result)
        self.assertNotIn('not wearing',result)
        self.assertNotIn('no lettering',result)
        self.assertIn('Image 1',result)

    def test_affirmative_missing_current_surface_blocks_sampling(self):
        compiler,spec,generate,_=self.compiler_fixture()
        self.project['render_settings']['compact_prompt_policy']=11
        change={'id':'scarf_off','character_id':'pip','after_state':'not wearing the blue scarf','surface':'neck'}
        self.project['art_plan']={'ledger':{'changes':[change]},'cover':{'changes':[],'props':[]},
                                 'pages':{'2':{'changes':['scarf_off'],'props':[]}}}
        def missing(*args,**kw):
            value=generate(*args,**kw)
            for actor in value.get('actors',{}).values():actor['current_surface']=''
            return value
        with patch.object(compiler,'scene_source',return_value={'page_prose':'Pip has removed his scarf.'}):
            with self.assertRaisesRegex(ValueError,'before spending image retries'):
                compiler.compile_prompt(self.project,spec,'old brief',1,missing)

    def test_unrequested_cutaway_cannot_pass_a_permissive_semantic_reviewer(self):
        compiler,spec,generate,calls=self.compiler_fixture()
        self.project['render_settings']['compact_prompt_policy']=11
        def cutaway(*args,**kw):
            value=generate(*args,**kw)
            for actor in value.get('actors',{}).values():actor['current_surface']=''
            if 'objects_and_relationships' in value:value['objects_and_relationships']='A cutaway view of the garden wall.'
            return value
        with patch.object(compiler,'scene_source',return_value={'page_prose':'Mira holds a lamp.'}):
            with self.assertRaisesRegex(ValueError,'before spending image retries'):
                compiler.compile_prompt(self.project,spec,'old',1,cutaway)
        self.assertEqual(len(calls),2)
        self.project['config']['art_style']='A cutaway educational picture book'
        result=compiler.compile_prompt(self.project,spec,'old',1,cutaway)
        self.assertIn('cutaway view',result)

    def test_camera_translation_preserves_all_action_clauses_and_source(self):
        compiler,spec,generate,calls=self.compiler_fixture()
        self.project['render_settings']['compact_prompt_policy']=11
        source={'page_prose':'Mira reaches for the lamp inside the wall.',
                'illustration_brief':'A cutaway view of the wall. Mira reaches for the brass lamp.'}
        def positive(*args,**kw):
            value=generate(*args,**kw)
            for actor in value.get('actors',{}).values():actor['current_surface']=''
            return value
        with patch.object(compiler,'scene_source',side_effect=lambda *args:copy.deepcopy(source)):
            compiler.compile_prompt(self.project,spec,'old',1,positive)
        request=json.loads(calls[0].split('Correctness takes priority over brevity. Report irreconcilable requirements as uncertainty.\n')[1].split('\nDescribe the desired')[0])
        self.assertEqual(request['source_prompt']['illustration_brief'],
                         'A close view of the wall. Mira reaches for the brass lamp.')
        self.assertEqual(source['illustration_brief'],'A cutaway view of the wall. Mira reaches for the brass lamp.')

    def test_reference_policy_changes_signature_without_mutating_story(self):
        self.prepare()
        original=copy.deepcopy(self.project['book'])
        before={s['name']:s for s in fixtures.story.asset_specs(self.project)}
        self.project['render_settings']['positive_flux_prompts']=1
        after={s['name']:s for s in fixtures.story.asset_specs(self.project)}
        self.assertEqual(self.project['book'],original)
        self.assertNotEqual(before['characters/mira.png']['signature'],after['characters/mira.png']['signature'])
        self.assertEqual(before['characters/mira.png']['seed'],after['characters/mira.png']['seed'])
        self.assertIn('Image 1 supplies painting style',after['characters/mira.png']['prompt'])
        self.assertNotIn('no lettering',after['characters/mira.png']['prompt'])

    def test_structured_source_keeps_prose_and_routed_canonical_geometry(self):
        spec=self.prepare()
        compiler=importlib.import_module('book_test_pack.flux_prompt')
        contracts=importlib.import_module('book_test_pack.scene_contract')
        library=importlib.import_module('book_test_pack.visual_library')
        spec['visual_references']=['props/gate.png']
        with patch.object(contracts,'scene_render_details',return_value=([],[])), patch.object(
                library,'entries',return_value=[{'id':'gate','name':'Gate','appearance':'Upright wooden gate.'}]):
            context=compiler.scene_source(self.project,spec)
        self.assertEqual(context['page_prose'],self.project['book']['pages'][1]['text'])
        self.assertEqual(context['canonical_designs'][0]['appearance'],'Upright wooden gate.')
        self.assertIn('holds its handle',context['illustration_brief'])

    def test_turbo_recipe_changes_fresh_scene_sampler_but_preserves_seed(self):
        spec = self.prepare()
        self.project['render_settings'].update(fixtures.render.FLUX_MODELS)
        self.project['render_settings'].update(flux_steps=28, flux_guidance=4, flux_scene_recipe='turbo8_native')
        graph = fixtures.render.expand_attempt(self.project, spec, 1)['expand']
        by_type = {node['class_type']: node['inputs'] for node in graph.values()}
        self.assertEqual(by_type['Flux2Scheduler']['steps'], 8)
        self.assertEqual(by_type['FluxGuidance']['guidance'], 2.5)
        self.assertEqual(by_type['LoraLoaderModelOnly']['lora_name'], fixtures.render.FLUX_TURBO_LORA)
        self.assertEqual(by_type['LoraLoaderModelOnly']['strength_model'], 1)
        self.assertEqual(by_type['RandomNoise']['noise_seed'], spec['seed'])
        self.assertEqual(by_type['BookV2ReviewAsset']['actual_seed'], spec['seed'])

    def test_turbo_does_not_change_reference_or_repair_recipes(self):
        spec = self.prepare()
        self.project['render_settings'].update(fixtures.render.FLUX_MODELS)
        self.project['render_settings'].update(flux_steps=28, flux_guidance=4, flux_scene_recipe='turbo8_native')
        reference = next((s for s in fixtures.story.asset_specs(self.project) if s['kind'] == 'style'))
        for asset, options in [(reference, {}), (spec, {'correction_attempt': 1}), (spec, {'scale_repair': True}), (spec, {'correction_attempt': 1, 'pose_guide': True})]:
            with self.subTest(kind=asset['kind'], options=options):
                graph = fixtures.render.expand_attempt(self.project, asset, 2, **options)['expand']
                by_type = {node['class_type']: node['inputs'] for node in graph.values()}
                self.assertNotIn('LoraLoaderModelOnly', by_type)
                self.assertEqual(by_type['Flux2Scheduler']['steps'], 28)
                self.assertEqual(by_type['FluxGuidance']['guidance'], 4)

    def model_fixture(self):
        self.prepare()
        self.project['book_root'] = str(self.output / 'books/test')
        folder_paths = sys.modules['folder_paths']
        model = self.output / 'model-fixture'
        model.write_bytes(b'test model metadata only')
        folder_paths.get_full_path = lambda category, name: str(model)
        return ({**fixtures.render.FLUX_MODELS, 'renderer': 'flux2', 'flux_steps': 28, 'flux_guidance': 4}, folder_paths)

    def test_default_recipe_widget_does_not_invalidate_old_rendition(self):
        settings, _ = self.model_fixture()
        old = fixtures.render.configure_render(self.project, settings)
        reopened = fixtures.render.configure_render(self.project, {**settings, 'flux_scene_recipe': 'standard'})
        self.assertEqual(old, reopened)
        turbo = fixtures.render.configure_render(self.project, {**settings, 'flux_scene_recipe': 'turbo8_native'})
        self.assertNotEqual(old['render_root'], turbo['render_root'])
        self.assertIn('flux_turbo_lora', turbo['render_settings']['model_files'])

    def test_missing_turbo_lora_fails_before_creating_rendition(self):
        settings, folder_paths = self.model_fixture()
        resolve = folder_paths.get_full_path
        folder_paths.get_full_path = lambda category, name: None if category == 'loras' else resolve(category, name)
        with self.assertRaisesRegex(ValueError, 'Missing loras model'):
            fixtures.render.configure_render(self.project, {**settings, 'flux_scene_recipe': 'turbo8_native'})
        self.assertFalse(Path(self.project['book_root']).exists())

    def compiler_fixture(self, *, roles='', semantic_ok=True):
        spec = self.prepare()
        self.project['config']['ollama_url'] = 'http://local-test.invalid'
        compiler = importlib.import_module('book_test_pack.flux_prompt')
        calls = []

        def generate(url, model, prompt, schema, **kwargs):
            calls.append(prompt)
            if 'actors' in schema['properties']:
                return {'setting': 'A moonlit garden.', 'actors': {cid: {'identity': cid, 'action': 'shares the light.', 'contact_geometry': ''} for cid in ('mira', 'pip', 'fern')}, 'objects_and_relationships': 'The friends share one lamp.', 'object_counts': 'One lamp.', 'style': 'Soft gouache.', 'other_reference_roles': roles, 'uncertain': False, 'issues': []}
            return {'checks': {key: semantic_ok for key in schema['properties']['checks']['properties']}, 'uncertain': False, 'issues': [] if semantic_ok else ['The action changed.'], 'evidence': 'Fixture audit.'}
        return (compiler, spec, generate, calls)

    def test_compiler_resumes_verified_prompt_and_rejects_cache_tampering(self):
        compiler, spec, generate, calls = self.compiler_fixture()
        result = compiler.compile_prompt(self.project, spec, 'Original source', 1, generate)
        self.assertEqual(len(calls), 2)
        self.assertEqual(compiler.compile_prompt(self.project, spec, 'Original source', 1, generate), result)
        self.assertEqual(len(calls), 2, 'Resume must reuse completed local generation and review.')
        approved = next(Path(self.project['render_root']).glob('prompt-compilation/*/approved.json'))
        compiler.compile_prompt(self.project, spec, 'Changed source', 1, generate)
        self.assertEqual(len(calls), 4, 'Changed story instructions require a fresh compilation.')
        saved = json.loads(approved.read_text())
        saved['prompt'] += ' Altered actor.'
        approved.write_text(json.dumps(saved))
        with self.assertRaisesRegex(ValueError, 'provenance mismatch'):
            compiler.compile_prompt(self.project, spec, 'Original source', 1, generate)

    def test_compiler_never_uses_rewrite_with_missing_reference_role(self):
        compiler, spec, generate, calls = self.compiler_fixture()
        result = compiler.compile_prompt(self.project, spec, 'Source also describes Image 2.', 2, generate)
        self.assertEqual(result, 'Source also describes Image 2.')
        self.assertEqual(len(calls), 2, 'Structural rejection must not call the semantic reviewer.')
        self.assertFalse(list(Path(self.project['render_root']).glob('prompt-compilation/*/approved.json')))

    def test_semantic_rejection_retains_source_and_failed_drafts_for_resume(self):
        compiler, spec, generate, calls = self.compiler_fixture(semantic_ok=False)
        self.assertEqual(compiler.compile_prompt(self.project, spec, 'Keep required action.', 1, generate), 'Keep required action.')
        self.assertEqual(len(calls), 4)
        self.assertEqual(compiler.compile_prompt(self.project, spec, 'Keep required action.', 1, generate), 'Keep required action.')
        self.assertEqual(len(calls), 4, 'A restart must not lose failed attempts or spend their budget again.')

    def test_fixed_reference_roles_cannot_be_dropped_by_local_rewriter(self):
        compiler, spec, generate, calls = self.compiler_fixture()
        def fixed(*args, **kwargs):
            draft=generate(*args,**kwargs)
            draft.pop('other_reference_roles',None)
            return draft
        result=compiler.compile_prompt(self.project,spec,'An action with Image 2 and Image 3.',3,fixed,
            reference_roles={2:'the exact blue lamp design.',3:'the canonical garden setting.'})
        self.assertIn('Image 2: the exact blue lamp design.',result)
        self.assertIn('Image 3: the canonical garden setting.',result)
        self.assertEqual(len(calls),2)

    def test_missing_caller_reference_role_is_rejected_before_model_call(self):
        compiler, spec, generate, calls = self.compiler_fixture()
        with self.assertRaisesRegex(ValueError,'exactly the additional'):
            compiler.compile_prompt(self.project,spec,'Source',3,generate,reference_roles={2:'lamp'})
        self.assertFalse(calls)

    def test_removed_costume_state_survives_rewriter_omission(self):
        compiler, spec, generate, calls = self.compiler_fixture()
        change={'id':'scarf_off','character_id':'pip','after_state':'not wearing the blue scarf','surface':'neck'}
        self.project['art_plan']={'ledger':{'changes':[change]},'cover':{'changes':[],'props':[]},
                                 'pages':{'2':{'changes':['scarf_off'],'props':[]}}}
        result=compiler.compile_prompt(self.project,spec,'The mouse has removed its scarf.',1,generate)
        self.assertIn('Current appearance: not wearing the blue scarf on neck.',result)

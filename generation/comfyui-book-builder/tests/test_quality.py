import copy
import hashlib
import importlib
import itertools
import json
from pathlib import Path
from unittest.mock import patch
import unittest

import test_book as fixtures
from test_book import story, storage, render, export

quality = importlib.import_module('book_test_pack.quality')
nodes = importlib.import_module('book_test_pack.nodes')


def visual_report(project, spec, accepted=True):
    ids = quality.expected_scene(project, spec)[0]
    report = {'checks': {k: True for k in quality.VISUAL_CHECKS}, 'evidence': 'Each requested character is visibly distinct.',
              'issues': [], 'uncertain': False, 'unexpected_character_count': 0,
              'characters': [{'id': cid, 'count': 1, 'identity_matches': True, 'appearance_matches': True,
                              'scale_matches': True, 'evidence': 'Visible with matching features.'} for cid in ids]}
    if not accepted:
        report['issues'] = ['The mouse is missing and the girl is duplicated.']
        report['unexpected_character_count'] = 1
    return {'accepted': accepted, 'signature': spec['signature'], 'review': report}


class QualityTests(unittest.TestCase):
    setUp = fixtures.BookTests.setUp
    restore_module = fixtures.BookTests.restore_module

    def continuity_fixture(self, canonical, accepted=True):
        return {'facts': {'ending_cause':'The friend caused the event before the opening.',
                'earlier_actions_of_revealed_participants':'The friend then helped investigate.',
                'required_missing_transitions':'The friend needs an explained return trip.',
                'visible_changed_objects_or_clothing':'No changed clothes in this fixture.',
                'timeline':[{'pageNumber':p['pageNumber'],'events_and_locations':p['text'],
                             'knowledge_and_object_changes':'Fixture state.'} for p in canonical['pages']]},
                'issues':[] if accepted else [{'pages':[1,2],'kind':'sequence',
                    'evidence':'The friend changes location without a required transition.',
                    'repair_direction':'Explain the return trip in the prose.'}],
                'uncertain':False,'verdict':'pass' if accepted else 'revise'}

    def test_continuity_veto_overrides_successful_broad_and_page_reviews(self):
        package=fixtures.package_fixture()
        names={c['name']:c['id'] for c in package['production']['characters']}
        broad={'checks':{k:True for k in quality.TEXT_CHECKS},'issues':[],
               'evidence':'Broad review passed.','uncertain':False}
        pages=[{'pageNumber':p['pageNumber'],'checks':{'moment_matches':True},'issues':[],
                'evidence':'Page moment is correct.','uncertain':False,
                'illustrated_figures':[{'description':n,'cast_id':names[n],'is_character':True}
                                      for n in p['charactersPresent']]} for p in package['story']['pages']]
        focused=self.continuity_fixture(package['story'],False)
        with patch.object(quality,'json_model',side_effect=[broad,{'pages':pages},focused]) as model:
            result=quality.review_story(package,{'age_range':'4-6','story_idea':'test',
                'ollama_url':'http://unused','review_model':'test'},generate=model)
        self.assertEqual(model.call_count,3)
        self.assertFalse(result['accepted'])
        self.assertFalse(result['review']['checks']['continuity'])
        self.assertIn('Explain the return trip',result['review']['issues'][0])
        self.assertEqual(result['continuity_audit'],focused)

    def test_continuity_pass_never_clears_prior_failure_and_uncertainty_vetoes(self):
        continuity=importlib.import_module('book_test_pack.continuity')
        canonical=self.project['story']
        report={'checks':{k:True for k in quality.TEXT_CHECKS},'issues':['Existing failure'],
                'evidence':'Existing review.','uncertain':False}
        report['checks']['age_appropriate']=False
        original=copy.deepcopy(report)
        audit=self.continuity_fixture(canonical)
        continuity.apply_audit(report,audit,canonical)
        self.assertEqual(report,original)
        audit['uncertain']=True
        continuity.apply_audit(report,audit,canonical)
        self.assertFalse(quality.passed(report))
        self.assertFalse(report['checks']['continuity'])
        self.assertTrue(report['uncertain'])
        self.assertIn('Existing failure',report['issues'])

    def test_continuity_cannot_approve_missing_duplicate_or_unknown_pages(self):
        continuity=importlib.import_module('book_test_pack.continuity')
        canonical=self.project['story']
        valid=self.continuity_fixture(canonical)
        for numbers in ([1,2],[1,1,3],[1,2,99]):
            audit=copy.deepcopy(valid)
            audit['facts']['timeline']=[{**valid['facts']['timeline'][0],'pageNumber':n} for n in numbers]
            with self.assertRaisesRegex(ValueError,'omitted or duplicated'):
                continuity.validate_audit(audit,canonical)
        audit=copy.deepcopy(valid)
        audit['issues']=[{'pages':[99],'kind':'sequence','evidence':'Unknown page','repair_direction':'Fix'}]
        with self.assertRaisesRegex(ValueError,'unknown page'):
            continuity.validate_audit(audit,canonical)

    def test_independent_tail_failure_blocks_broad_visual_approval(self):
        spec=story.asset_specs(self.project)[-2]
        report=visual_report(self.project,spec)['review']
        ids=quality.expected_scene(self.project,spec)[0]
        self.assertTrue(quality.passed(report,ids))
        review={'checks':{'tails_plausible':False},'uncertain':False,
                'issues':['The fox holds a detached tail while another tail is attached behind it.'],
                'evidence':'Two separate full tail silhouettes.', 'observed_tails':['Behind rump','Held over tub']}
        quality.apply_tail_review(report,review)
        self.assertFalse(quality.passed(report,ids))
        self.assertFalse(report['checks']['anatomy_sound'])
        self.assertEqual(report['issues'],review['issues'])
        self.assertTrue(report['retry_instructions'])
        passing={'checks':{'tails_plausible':True},'uncertain':False,'issues':[],
                 'evidence':'One connected tail per animal.','observed_tails':['Fox tail']}
        quality.apply_tail_review(report,passing)
        self.assertFalse(quality.passed(report,ids), 'A later pass cannot clear another rejection')

    def test_uncertain_tail_audit_cannot_publish_an_image(self):
        spec=story.asset_specs(self.project)[-2]
        report=visual_report(self.project,spec)['review']
        quality.apply_tail_review(report,{'checks':{'tails_plausible':True},'uncertain':True,
                                         'issues':[],'evidence':'Connection unclear.','observed_tails':[]})
        self.assertTrue(report['uncertain'])
        self.assertFalse(quality.passed(report,quality.expected_scene(self.project,spec)[0]))

    def test_fenced_model_json_keeps_document_and_rejects_surrounding_prose(self):
        value = {'accepted': False, 'issues': ['Pip is not pulling the rope.']}
        raw = json.dumps(value)
        for text in (raw, '```json\n'+raw+'\n```', '```\n'+raw+'\n```'):
            self.assertEqual(quality.parse_model_json(text), value)
        for text in ('Explanation\n'+raw, raw+'\n'+raw, '```json\n'+raw+'\n```\nApproved!'):
            with self.assertRaises(json.JSONDecodeError):
                quality.parse_model_json(text)

    def test_scene_budget_rejects_excess_group_pages_before_editor_model_call(self):
        package={k:copy.deepcopy(self.project[k]) for k in ('story','production')}
        original=copy.deepcopy(package)
        with patch.object(quality,'json_model',side_effect=AssertionError('No GPU call needed')) as model:
            result=quality.review_story(package,{'max_ensemble_pages':0,'review_model':'test'},generate=model)
        self.assertFalse(result['accepted'])
        self.assertEqual(result['stage'],'scene_budget')
        self.assertIn('Pages [2]',result['review']['issues'][0])
        self.assertEqual(package,original)

    def test_scene_recheck_considers_grip_semantics_but_cannot_clear_other_failures(self):
        spec=story.asset_specs(self.project)[-2]
        report=visual_report(self.project,spec)['review']
        report['checks']['scene_matches']=False
        report['issues']=['Pip and Fern are positioned on opposite sides of the tub.']
        self.assertTrue(quality.may_recheck_layout(report))
        for issue in ['Pip is pointing at Mira rather than the stones.',
                      'Mira holds the wrong object on the left.',
                      'The rope is disconnected from the load.',
                      'Pip has a missing paw on the right.']:
            changed=copy.deepcopy(report);changed['issues']=[issue]
            # Eligibility means inspect its story meaning, never auto-approve.
            self.assertTrue(quality.may_recheck_layout(changed))
        changed=copy.deepcopy(report);changed['checks']['no_unwanted_text']=False
        self.assertFalse(quality.may_recheck_layout(changed))
        changed=copy.deepcopy(report);changed['characters'][0]['count']=2
        self.assertFalse(quality.may_recheck_layout(changed))

    def test_optional_staging_requires_complete_grounding_and_cannot_clear_story_requirements(self):
        audit = {'story_event_visible': True, 'uncertain': False, 'essential_issues': [],
                 'observed_event': 'Maya arrives holding the stick in her hand.',
                 'required_story_event': 'Maya carries a stick to help reach the bowl.',
                 'prior_issues': [{'issue_index': 0, 'kind': 'incidental_grip',
                    'required_by': 'illustration_only', 'evidence': 'The prose requires carrying, not a finger trick.',
                    'story_impact': 'The useful tool and intention remain clear.'}]}
        prior = ['Maya holds the stick in her whole hand rather than balancing it on one finger.']
        self.assertTrue(quality.scene_objections_are_optional(audit, prior))
        for source in ('prose', 'explicit_user', 'continuity'):
            changed = copy.deepcopy(audit)
            changed['prior_issues'][0]['required_by'] = source
            self.assertFalse(quality.scene_objections_are_optional(changed, prior))
        for kind in ('essential_action', 'identity_or_count', 'required_prop_state', 'required_emotion', 'other'):
            changed = copy.deepcopy(audit)
            changed['prior_issues'][0]['kind'] = kind
            self.assertFalse(quality.scene_objections_are_optional(changed, prior))
        for key, value in [('uncertain', True), ('story_event_visible', False),
                           ('essential_issues', ['The stick does not reach the load.']), ('prior_issues', [])]:
            changed = copy.deepcopy(audit); changed[key] = value
            self.assertFalse(quality.scene_objections_are_optional(changed, prior))
        self.assertFalse(quality.scene_objections_are_optional(audit, prior + ['A second objection.']))
        changed = copy.deepcopy(audit)
        changed['prior_issues'] *= 2
        self.assertFalse(quality.scene_objections_are_optional(changed, prior + ['A second objection.']))

    def test_punctuation_pass_preserves_words_and_resumes_without_model_call(self):
        prose=importlib.import_module('book_test_pack.prose')
        package={k:copy.deepcopy(self.project[k]) for k in ('story','production')}
        package['story']['pages'][0]['text']='That is loud, Mira said. The birds slept.'
        texts=[p['text'] for p in package['story']['pages']]
        texts[0]='“That is loud,” Mira said. The birds slept.'
        config={'ollama_url':'http://unused','review_model':'test'}
        root=self.output/'books/punctuation'
        with patch.object(quality,'json_model',return_value={'texts':texts}) as model:
            result=prose.punctuate_generated_prose(package,config,root,generate=model)
            resumed=prose.punctuate_generated_prose(package,config,root,generate=model)
        self.assertEqual(model.call_count,1)
        self.assertEqual(result,resumed)
        self.assertEqual(result['story']['pages'][0]['text'],texts[0])
        self.assertEqual(result['production'],package['production'])
        self.assertEqual(result['story']['pages'][0]['imagePrompt'],package['story']['pages'][0]['imagePrompt'])
        changed=copy.deepcopy(texts);changed[0]='“That is quiet,” Mira said. The birds slept.'
        with patch.object(quality,'json_model',return_value={'texts':changed}) as model:
            with self.assertRaisesRegex(ValueError,'changed story words'):
                prose.punctuate_generated_prose(package,config,self.output/'books/bad-punctuation',generate=model)

    def test_palette_keeps_colours_without_prompting_clothes_in_empty_style(self):
        self.project['book']['visual_bible']['palette']='sage greens, pale yellows, soft corals, and bright pops of red and yellow for clothing.'
        canonical=copy.deepcopy(self.project['book']['characters'])
        legacy=story.style_text(self.project)
        self.assertIn('for clothing',legacy)
        self.project['render_settings']['style_prompt_version']=2
        prompt=story.asset_specs(self.project)[0]['prompt']
        self.assertIn('bright pops of red and yellow',prompt)
        self.assertNotIn('clothing',prompt)
        self.assertEqual(self.project['book']['characters'],canonical)
        self.project['render_settings']['style_prompt_version']=1
        self.assertEqual(story.style_text(self.project),legacy)

    def enable_quality(self):
        self.project['render_settings'].update(renderer='flux2', **render.FLUX_MODELS,
            flux_steps=28, flux_guidance=4.0, quality_required=True, review_model='test-reviewer', art_attempts=2)
        self.project['config']['ollama_url'] = 'http://unused.invalid'
        self.project['story_quality'] = {'accepted': True,
            'package_hash': story.digest({k:self.project[k] for k in ['story','production']}),
            'review': {'checks': {k:True for k in quality.TEXT_CHECKS}, 'evidence':'Story is coherent.', 'issues':[], 'uncertain':False}}

    def test_new_output_root_and_legacy_access(self):
        self.assertEqual(storage.books_root(), self.output/'books')
        self.assertEqual(storage.checked_root(self.project), Path(self.project['render_root']))
        self.project['render_root'] = str(self.output/'books/new/renders/test')
        self.assertEqual(storage.checked_root(self.project), Path(self.project['render_root']))

    def test_checkpoint_restores_actual_seed_and_preserves_original_canvas(self):
        root = self.output/'books/checkpoint-test'
        prompt = {'17': {'class_type': 'BookV2Story', 'inputs': {'seed': 42}}}
        defaults = ['idea','4-6',12,3,'style',999,'randomize','http://unused','writer']
        canvas = {'nodes': [{'id': 17, 'type': 'BookV2Story',
                            'widgets_values': defaults}],
                  'groups': [{'title': 'Keep my layout'}]}
        original = copy.deepcopy(canvas)
        storage.save_workflow_checkpoint(root, prompt, {'workflow': canvas})
        storage.save_workflow_checkpoint(root, prompt, {'workflow': canvas})
        files = list((root/'checkpoints').glob('*.workflow.json'))
        self.assertEqual(len(files), 1)
        saved = json.loads(files[0].read_text())
        seed_index = list(nodes.BookV2Story.INPUT_TYPES()['required']).index('seed')
        self.assertEqual(saved['nodes'][0]['widgets_values'][seed_index:seed_index+2], [42, 'fixed'])
        self.assertEqual(saved['nodes'][0]['widgets_values'][7:], defaults[7:])
        self.assertEqual(saved['groups'], canvas['groups'])
        self.assertEqual(canvas, original)
        self.assertEqual(json.loads(next((root/'checkpoints').glob('*.api.json')).read_text()), prompt)

    def test_editor_inventory_rejects_an_unregistered_beetle_even_if_other_checks_pass(self):
        package={k:self.project[k] for k in ('story','production')}
        global_review={'checks':{k:True for k in quality.TEXT_CHECKS},'evidence':'A coherent story.',
                       'issues':[],'uncertain':False}
        by_name={c['name']:c['id'] for c in package['production']['characters']}
        audits=[]
        for page in package['story']['pages']:
            audits.append({'pageNumber':page['pageNumber'],'prose_event':'An event.','image_event':'An event.',
                'illustrated_figures':[{'description':name,'cast_id':by_name[name]} for name in page['charactersPresent']],
                'checks':{k:True for k in ('moment_matches','cast_consistent','action_and_props_match',
                                         'location_and_scale_consistent','prose_reads_well','costume_consistent')},
                'evidence':'Visible cast extracted from the scene.','issues':[],'uncertain':False})
        audits[0]['illustrated_figures'].append({'description':'An unnamed beetle wearing a top hat','cast_id':None})
        replies=iter([global_review,{'pages':audits}])
        result=quality.review_story(package,{'age_range':'4-6','story_idea':'test','ollama_url':'http://unused','review_model':'test'},
                                    generate=lambda *args:next(replies))
        self.assertFalse(result['accepted'])
        self.assertIn('beetle',json.dumps(result['review']['issues']))

    def test_saved_project_preserves_large_integers_and_asset_signatures(self):
        project=copy.deepcopy(self.project)
        project['config'].update(page_count=3,max_characters=3)
        project['render_settings']['model_files']={'example':{'mtime_ns':1767011861545792026}}
        project['render_root']=str(self.output/'books/saved/renders/one')
        path=Path(project['render_root'])/'project.json'
        storage.write_json(path,project)
        name='characters/mira.png'
        before=next(s for s in story.asset_specs(project) if s['name']==name)
        restored,spec=nodes.BookV2LoadAssetProject().load(str(path),name)
        self.assertEqual(restored,project)
        self.assertEqual(spec,before)
        self.assertEqual(restored['render_settings']['model_files']['example']['mtime_ns'],1767011861545792026)
        with self.assertRaisesRegex(ValueError,'book output'):
            nodes.BookV2LoadAssetProject().load('/tmp/outside-project.json',name)

    def test_generated_plain_prose_preserves_contract_and_original_draft(self):
        package={k:copy.deepcopy(self.project[k]) for k in ('story','production')}
        package['story']['pages'][0]['text']='*Splat!* "Oops," said Mira. **What a splash!** A lone * stays.'
        original=copy.deepcopy(package)
        normalized=story.plain_generated_prose(package)
        self.assertEqual(normalized['story']['pages'][0]['text'],'Splat! "Oops," said Mira. What a splash! A lone * stays.')
        self.assertEqual(package,original)
        normalized['story']['pages'][0]['text']=original['story']['pages'][0]['text']
        self.assertEqual(normalized,original)
        self.assertEqual(story.plain_generated_prose({'bad':'response'}),{'bad':'response'})

    def test_canonical_portraits_separate_permanent_design_from_later_plot_events(self):
        self.enable_quality()
        character=self.project['book']['characters'][1]
        character['personality']='Cheerful; later gets strawberry jam on both ears.'
        original=copy.deepcopy(self.project)
        legacy=story.reference_prompt(self.project,character)
        self.project['render_settings']['portrait_prompt_version']=2
        prompt=story.reference_prompt(self.project,character)
        self.assertIn(character['appearance'],prompt)
        self.assertNotIn('strawberry jam',prompt)
        self.assertEqual(self.project['book'],original['book'])
        self.assertEqual(self.project['story'],original['story'])
        self.assertIn('strawberry jam',legacy)  # old signatures remain reconstructible
        spec=next(s for s in story.asset_specs(self.project) if s['name']=='characters/pip.png')
        storage.write_exclusive(storage.asset_path(self.project,'style.png'),b'reference')
        prompts=[]
        def review(*args):
            prompts.append(args[2])
            if len(prompts)==1:
                return {'figure_count':1,'visible_figures':['one mouse'],'description':'One mouse.'}
            if 'tails_plausible' in args[3]['properties']['checks']['properties']:
                return {'checks':{'tails_plausible':True},'uncertain':False,'issues':[],
                        'observed_tails':['One mouse tail.'],'evidence':'One connected tail.'}
            return visual_report(self.project,spec)['review']
        quality.review_art(self.project,spec,b'candidate',generate=review)
        self.assertNotIn('strawberry jam','\n'.join(prompts))
        self.assertIn('baseline permanent appearance',prompts[1])

    def test_imported_story_text_is_never_normalized(self):
        import sys,types
        mm=types.ModuleType('comfy.model_management')
        mm.unload_all_models=lambda:None;mm.soft_empty_cache=lambda:None
        package=fixtures.package_fixture()
        for c,h in zip(package['production']['characters'],[105,8,35]):c['height_cm']=h
        package['story']['pages'][0]['text']='Mira said, "Keep my *exact* text."'
        def verdict(p,config):
            return {'accepted':True,'package_hash':story.digest(p),'review':{'checks':{k:True for k in quality.TEXT_CHECKS},
                'evidence':'The imported story is coherent.','issues':[],'uncertain':False}}
        with patch.dict(sys.modules,{'comfy.model_management':mm}),patch.object(nodes,'ollama_generate',return_value=json.dumps(package['production'])),patch.object(nodes,'review_story',side_effect=verdict):
            project,public=nodes.BookV2Story().write(story_idea='Existing story',age_range='4-6',page_count=3,max_characters=3,
                art_style=story.DEFAULT_STYLE,seed=987,ollama_url='http://unused',ollama_model='writer',story_json=json.dumps(package['story']))
        self.assertEqual(json.loads(public),package['story'])
        self.assertIsNone(project['config']['prose_format'])

    def test_editor_update_reuses_only_matching_stories_after_a_fresh_approval(self):
        package={k:self.project[k] for k in ('story','production')}
        config={'seed':100,'page_count':3,'max_characters':3,'story_idea':'same premise','qa_version':'old'}
        source=storage.books_root()/'book-100-old'/'plan.json'
        storage.write_json(source,{'config':config,'package':package})
        before=source.read_bytes()
        current={**config,'qa_version':quality.STORY_QA_VERSION}
        approval={'qa_version':quality.STORY_QA_VERSION,'package_hash':story.digest(package),'accepted':True}
        target=storage.books_root()/'book-100-new'
        with patch.object(nodes,'review_story',return_value=approval) as review:
            self.assertTrue(nodes.reuse_story_after_review_change(target,current))
            self.assertEqual(review.call_count,1)
        self.assertEqual(json.loads((target/'plan.json').read_text())['package'],package)
        self.assertEqual(source.read_bytes(),before)
        changed=storage.books_root()/'book-100-other'
        with patch.object(nodes,'review_story',side_effect=AssertionError('Unrelated premise must not be reused')):
            self.assertFalse(nodes.reuse_story_after_review_change(changed,{**current,'story_idea':'new premise'}))

    def test_failed_editorial_draft_survives_review_revision_without_rewriting(self):
        package={k:self.project[k] for k in ('story','production')}
        previous={'seed':100,'page_count':3,'max_characters':3,'story_idea':'same premise','qa_version':'old'}
        source=storage.books_root()/f"book-100-{story.digest(previous)[:10]}"/'quality/story/attempt-05.json'
        storage.write_json(source,{'package':package,'approval':{
            'qa_version':'old','package_hash':story.digest(package),'accepted':False,
            'review':{'issues':['An offscreen friend was incorrectly demanded in the frame.']}}})
        before=source.read_bytes();current={**previous,'qa_version':quality.STORY_QA_VERSION}
        target=storage.books_root()/f"book-100-{story.digest(current)[:10]}"
        approval={'qa_version':quality.STORY_QA_VERSION,'package_hash':story.digest(package),'accepted':True}
        with patch.object(nodes,'review_story',return_value=approval) as review,patch.object(nodes,'ollama_generate',side_effect=AssertionError('Do not rewrite saved prose')):
            self.assertTrue(nodes.reuse_story_after_review_change(target,current))
            self.assertEqual(review.call_count,1)
        self.assertEqual(source.read_bytes(),before)
        self.assertEqual(json.loads((target/'plan.json').read_text())['package'],package)
        with patch.object(nodes,'review_story',side_effect=AssertionError('A changed premise has a different legacy directory digest')):
            self.assertFalse(nodes.reuse_story_after_review_change(storage.books_root()/'different',{**current,'story_idea':'a different premise'}))

    def test_failed_draft_with_changed_bytes_cannot_be_reused(self):
        package={k:self.project[k] for k in ('story','production')}
        previous={'seed':100,'page_count':3,'max_characters':3,'story_idea':'same premise','qa_version':'old'}
        source=storage.books_root()/f"book-100-{story.digest(previous)[:10]}"/'quality/story/attempt-05.json'
        storage.write_json(source,{'package':package,'approval':{'qa_version':'old','package_hash':'incorrect','accepted':False}})
        with patch.object(nodes,'review_story',side_effect=AssertionError('Changed saved draft must not be reused')):
            self.assertFalse(nodes.reuse_story_after_review_change(storage.books_root()/'new',{**previous,'qa_version':quality.STORY_QA_VERSION}))

    def test_quality_revision_reuses_pixels_but_never_reuses_the_old_approval(self):
        import torch
        from PIL import Image
        self.enable_quality()
        source=copy.deepcopy(self.project)
        source['book_root']=str(self.output/'books/pixel-reuse')
        source['render_root']=str(Path(source['book_root'])/'renders/old')
        source['render_settings']['qa_version']='old'
        oldspec=story.asset_specs(source)[0]
        data=storage.image_bytes(oldspec,torch.rand((1,1024,1024,3)))
        report=visual_report(source,oldspec)
        report.update(png_sha256=hashlib.sha256(data).hexdigest(),seed=oldspec['seed'],prompt=oldspec['prompt'])
        storage.publish_reviewed_asset(source,oldspec,data,report)
        storage.write_json(Path(source['render_root'])/'project.json',source)
        target=copy.deepcopy(source);target['render_root']=str(Path(source['book_root'])/'renders/new')
        target['render_settings']['qa_version']='new'
        target['render_settings']['reference_strategy']='cast_guide'
        spec=story.asset_specs(target)[0]
        self.assertTrue(storage.reuse_candidate_pixels(target,spec))
        candidate=storage.review_directory(target,spec)/'attempt-01.png'
        self.assertEqual(Image.open(candidate).tobytes(),Image.open(storage.asset_path(source,oldspec['name'])).tobytes())
        self.assertFalse(storage.approval_path(target,spec).exists())
        self.assertFalse(storage.asset_path(target,spec['name']).exists())
        with patch.object(nodes,'review_art',return_value=visual_report(target,spec)),patch.object(nodes,'expand_attempt',side_effect=AssertionError('must not render')):
            nodes.BookV2RenderAsset().run(target,spec,'')
        self.assertTrue(storage.valid_asset(target,spec))
        self.assertEqual(storage.asset_path(source,oldspec['name']).read_bytes(),data)
        changed=copy.deepcopy(target);changed['render_root']=str(Path(source['book_root'])/'renders/changed')
        changed['render_settings']['flux_guidance']=8
        self.assertFalse(storage.reuse_candidate_pixels(changed,story.asset_specs(changed)[0]))

    def test_compared_failed_candidate_is_reused_but_still_unapproved(self):
        import torch
        from PIL import Image
        self.enable_quality()
        source=copy.deepcopy(self.project)
        source['book_root']=str(self.output/'books/compared-pixel-reuse')
        source['render_root']=str(Path(source['book_root'])/'renders/old')
        source['render_settings']['qa_version']='old'
        oldspec=story.asset_specs(source)[0]
        directory=storage.review_directory(source,oldspec)
        for n in (1,2):
            data=storage.image_bytes(oldspec,torch.rand((1,1024,1024,3)))
            report=visual_report(source,oldspec)
            report.update(accepted=False,png_sha256=hashlib.sha256(data).hexdigest(),seed=oldspec['seed'],prompt=oldspec['prompt'])
            report['review']['issues']=['A recorded objection']*n
            storage.write_exclusive(directory/f'attempt-{n:02d}.png',data)
            storage.write_json(directory/f'attempt-{n:02d}-review.json',report)
        storage.write_json(Path(source['render_root'])/'project.json',source)
        target=copy.deepcopy(source)
        target['render_root']=str(Path(source['book_root'])/'renders/new')
        target['render_settings']['qa_version']='new'
        chosen=directory/'attempt-02.png'
        with patch('book_test_pack.draft_selection.selected_draft_candidate',return_value={'path':str(chosen)}):
            spec=story.asset_specs(target)[0]
            self.assertTrue(storage.reuse_candidate_pixels(target,spec))
        candidate=storage.review_directory(target,spec)/'attempt-01.png'
        self.assertEqual(Image.open(candidate).tobytes(),Image.open(chosen).tobytes())
        self.assertFalse(storage.valid_asset(target,spec))
        self.assertFalse(storage.approval_path(target,spec).exists())

    def test_scene_context_includes_only_preceding_prose_without_adding_cast(self):
        specs=story.asset_specs(self.project)
        target=next(s for s in specs if s['name']=='pages/page-002.png')
        before=copy.deepcopy(self.project)
        context=quality.prior_scene_context(self.project,target)
        self.assertEqual(context,[{'page':1,'text':self.project['book']['pages'][0]['text']}])
        self.assertEqual(quality.prior_scene_context(self.project,next(s for s in specs if s['name']=='cover.png')),[])
        self.assertEqual(self.project,before)

    def test_ambiguous_detector_labels_keep_boxes_for_reference_identification(self):
        detection=importlib.import_module('book_test_pack.detection')
        boxes=[[374,241,646,942],[625,381,1007,925],[133,344,362,940]]
        known,ambiguous=detection.partition_detections(boxes,[.77,.45,.46],
            ['a child','a rabbit a fox','a rabbit a fox'],{'mia':'a child.','pip':'a rabbit.','barnaby':'a fox.'},[1024,1024])
        self.assertEqual(set(known),{'mia'})
        self.assertEqual(len(ambiguous),2)
        self.assertEqual({tuple(c['bbox']) for c in ambiguous},{tuple(b) for b in boxes[1:]})
        self.assertEqual(set(ambiguous[0]['possible_ids']),{'pip','barnaby'})
        known,ambiguous=detection.partition_detections(boxes[1:],[.8,.8],['fox','rabbit'],
            {'pip':'a rabbit.','barnaby':'a fox.'},[1024,1024])
        self.assertEqual(set(known),{'pip','barnaby'})
        self.assertEqual(ambiguous,[])
        known,ambiguous=detection.partition_detections([boxes[2]],[.28],['rabbit'],{'pip':'a rabbit.'},[1024,1024])
        self.assertEqual(known,{})
        self.assertEqual(ambiguous[0]['possible_ids'],['pip'])

    def test_highest_confidence_whole_figure_survives_proposal_order(self):
        detection=importlib.import_module('book_test_pack.detection')
        raw=json.loads((Path(__file__).parent/'fixtures/repair-coverage/page6-cast.json').read_text())
        proposals=list(zip(raw['boxes'],raw['scores'],raw['labels']))
        best=max((p for p in proposals if p[2]=='a fox'),key=lambda p:p[1])
        for order in itertools.permutations(proposals):
            boxes,scores,labels=zip(*order)
            known,unknown=detection.partition_detections(boxes,scores,labels,
                {'mia':'a girl.','barnaby':'a fox.'},[1024,1024])
            self.assertEqual(unknown,[])
            self.assertEqual(known['barnaby']['bbox'],best[0])
            self.assertEqual(known['barnaby']['score'],best[1])
            self.assertGreater(known['barnaby']['bbox'][2],1000)

    def test_confidence_sort_does_not_resolve_ambiguous_species(self):
        detection=importlib.import_module('book_test_pack.detection')
        known,unknown=detection.partition_detections([[10,10,100,100],[12,12,101,101]],
            [.4,.8],['a rabbit','a rabbit a fox'],{'pip':'a rabbit.','barnaby':'a fox.'},[128,128])
        self.assertEqual(known,{})
        self.assertEqual(set(unknown[0]['possible_ids']),{'pip','barnaby'})

    def test_actual_disconnected_paw_mask_refuses_cutout_resize(self):
        import numpy as np
        from PIL import Image
        repair=importlib.import_module('book_test_pack.repair')
        mask=np.array(Image.open(Path(__file__).parent/'fixtures/repair-coverage/highest-score-components.png').convert('L'))
        with self.assertRaisesRegex(ValueError,'disconnected'):
            repair.validate_mask_connectivity(mask)

    def test_actual_connected_mask_remains_eligible_for_cutout(self):
        import numpy as np
        from PIL import Image
        repair=importlib.import_module('book_test_pack.repair')
        mask=np.array(Image.open(Path(__file__).parent/'fixtures/repair-coverage/connected-control-components.png').convert('L'))
        result=repair.validate_mask_connectivity(mask)
        self.assertGreater(result['largest_fraction'],.99)

    def test_gate_rejects_counts_species_uncertainty_and_missing_checks(self):
        spec = story.asset_specs(self.project)[-2]
        report = visual_report(self.project, spec)['review']
        ids = quality.expected_scene(self.project, spec)[0]
        self.assertTrue(quality.passed(report, ids))
        for change in [lambda r:r.update(uncertain=True), lambda r:r.update(unexpected_character_count=1),
                       lambda r:r['characters'][0].update(count=2), lambda r:r['characters'][0].update(count=0),
                       lambda r:r['characters'][0].update(identity_matches=False),
                       lambda r:r['characters'][0].update(scale_matches=False),
                       lambda r:r['checks'].pop('scene_matches'), lambda r:r['characters'].pop()]:
            bad = copy.deepcopy(report); change(bad)
            self.assertFalse(quality.passed(bad, ids))

    def test_review_required_assets_cannot_be_saved_without_approval(self):
        self.enable_quality()
        with self.assertRaisesRegex(ValueError, 'visual approval'):
            storage.save_asset(self.project, story.asset_specs(self.project)[0], None)

    def test_flux_native_reference_conditioning_and_bounded_retry_seed(self):
        self.enable_quality()
        spec = story.asset_specs(self.project)[-2]
        a = render.expand_attempt(self.project, spec, 1)['expand']
        b = render.expand_attempt(self.project, spec, 2, 'Missing mouse; include it beside the girl.')['expand']
        self.assertEqual(len([n for n in a.values() if n['class_type']=='ReferenceLatent']), 3)
        self.assertEqual(len([n for n in a.values() if n['class_type']=='BookV2ReviewAsset']), 1)
        self.assertNotEqual(next(n['inputs']['noise_seed'] for n in a.values() if n['class_type']=='RandomNoise'),
                            next(n['inputs']['noise_seed'] for n in b.values() if n['class_type']=='RandomNoise'))
        self.assertIn('Missing mouse', next(n['inputs']['text'] for n in b.values() if n['class_type']=='CLIPTextEncode'))

    def test_failed_candidate_retries_then_stops_without_publishing(self):
        import torch
        comparison=patch('book_test_pack.draft_selection.select_review_candidate',return_value=None)
        comparison.start()
        self.addCleanup(comparison.stop)
        self.enable_quality()
        spec = story.asset_specs(self.project)[0]
        pixels = torch.rand((1,1024,1024,3))
        with patch.object(nodes, 'review_art', return_value=visual_report(self.project, spec, False)):
            for attempt in (1,2):
                result = nodes.BookV2ReviewAsset().review(self.project, spec, pixels, attempt, attempt, 'test')
                self.assertTrue(result['expand'])
        self.assertFalse(storage.asset_path(self.project, spec['name']).exists())
        with self.assertRaisesRegex(ValueError, 'Visual quality failed after 2 attempts'):
            nodes.BookV2RenderAsset().run(self.project, spec, '')
        self.assertEqual(len(list(storage.review_directory(self.project,spec).glob('attempt-*.png'))),2)
        with self.assertRaisesRegex(ValueError,'Book is incomplete'):
            export.export_book(self.project,False)

    def test_failed_scene_allows_next_page_but_never_exports_as_complete(self):
        self.enable_quality()
        scenes=[s for s in story.asset_specs(self.project) if s['kind']=='scene']
        failed=scenes[0]
        for attempt in (1,2):
            storage.write_json(storage.review_directory(self.project,failed)/f'attempt-{attempt:02d}-review.json',
                               visual_report(self.project,failed,False))
        result=nodes.BookV2RenderAsset().run(self.project,failed,'')
        self.assertEqual(result,('UNAPPROVED: cover.png',))
        self.assertFalse(storage.valid_asset(self.project,failed))
        with patch.object(nodes,'expand_attempt',return_value={'expand':{}}) as expand:
            nodes.BookV2RenderAsset().run(self.project,scenes[1],result[0])
        self.assertEqual(expand.call_args.args[1]['name'],'pages/page-001.png')
        self.assertEqual(expand.call_args.args[2],1)
        with self.assertRaisesRegex(ValueError,'Book is incomplete'):
            export.export_book(self.project,False)
        self.assertFalse((storage.checked_root(self.project)/'manifest.json').exists())
        progress=json.loads(next((storage.checked_root(self.project)/'quality').glob('incomplete-*.json')).read_text())
        self.assertEqual(progress['status'],'incomplete')
        self.assertIn('cover.png',progress['unapproved_assets'])

    def test_reviewer_outage_resumes_saved_candidate_without_rendering(self):
        import torch
        self.enable_quality()
        spec = story.asset_specs(self.project)[0]
        pixels = torch.rand((1,1024,1024,3))
        with patch.object(nodes,'review_art',side_effect=RuntimeError('Reviewer offline')):
            with self.assertRaisesRegex(RuntimeError,'Reviewer offline'):
                nodes.BookV2ReviewAsset().review(self.project,spec,pixels,1,42,'test')
        candidate = storage.review_directory(self.project,spec)/'attempt-01.png'
        before = candidate.read_bytes()
        with patch.object(nodes,'review_art',return_value=visual_report(self.project,spec)), patch.object(nodes,'expand_attempt',side_effect=AssertionError('must not render')):
            nodes.BookV2RenderAsset().run(self.project,spec,'')
        self.assertEqual(candidate.read_bytes(),before)
        self.assertTrue(storage.valid_asset(self.project,spec))
        self.assertEqual(storage.asset_path(self.project,spec['name']).read_bytes(),before)
        # An approved file cannot silently be changed after review.
        report = json.loads(storage.approval_path(self.project,spec).read_text())
        report['png_sha256']='wrong'
        storage.approval_path(self.project,spec).write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError,'approval'):
            storage.valid_asset(self.project,spec)

    def test_export_checks_exact_editorial_content(self):
        self.enable_quality()
        self.project['story']['pages'][0]['text']='Different unreviewed story.'
        with self.assertRaisesRegex(ValueError,'editorial approval'):
            export.export_book(self.project,False)

    def test_empty_style_does_not_append_world_or_faces(self):
        self.project['book']['visual_bible']['world']='A girl in a pink dress standing in the garden.'
        self.project['book']['visual_bible']['style']='Soft gouache, expressive friendly faces, pale colours.'
        text=story.asset_specs(self.project)[0]['prompt']
        self.assertNotIn('pink dress',text)
        self.assertNotIn('expressive friendly faces',text)

    def test_editorial_failure_repairs_and_preserves_contract(self):
        import sys
        import types
        fake_mm = types.ModuleType('comfy.model_management')
        fake_mm.unload_all_models = lambda: None
        fake_mm.soft_empty_cache = lambda: None
        fake_mm.throw_exception_if_processing_interrupted = lambda: None
        package = fixtures.package_fixture()
        for c,h in zip(package['production']['characters'],[105,8,35]):
            c['height_cm']=h
        def verdict(p,config):
            bad = p['story']['pages'][0]['text'].startswith('BAD')
            report = {'checks':{k:True for k in quality.TEXT_CHECKS},'evidence':'Reviewed all pages.',
                      'issues':['Page 1 is unreadable.'] if bad else [],'uncertain':False}
            return {'accepted':not bad,'package_hash':story.digest(p),'review':report}
        bad = copy.deepcopy(package);bad['story']['pages'][0]['text']='BAD disconnected words.'
        args=dict(story_idea='Sharing light',age_range='4-6',page_count=3,max_characters=3,
                  art_style=story.DEFAULT_STYLE,seed=123,ollama_url='http://unused',ollama_model='writer')
        prose=importlib.import_module('book_test_pack.prose')
        with patch.dict(sys.modules,{'comfy.model_management':fake_mm}), patch.object(nodes,'narrative_outline',return_value={"test":"outline"}), patch.object(nodes,'ollama_generate',side_effect=[json.dumps(bad),json.dumps(package)]) as writer, patch.object(nodes,'review_story',side_effect=verdict), patch.object(prose,'punctuate_generated_prose',side_effect=lambda p,*args:p):
            project,public=nodes.BookV2Story().write(**args)
            self.assertEqual(writer.call_count,2)
            self.assertIn('Page 1 is unreadable',writer.call_args.args[2])
            self.assertEqual(set(json.loads(public)),{'id','pages','metadata'})
            self.assertTrue(project['story_quality']['accepted'])
            # A repeated run reuses the approved story without contacting either model.
            nodes.BookV2Story().write(**args)
            self.assertEqual(writer.call_count,2)

    def test_visual_state_failure_returns_to_writer_before_publication_and_resumes(self):
        import sys
        import types
        ledger = importlib.import_module('book_test_pack.state_ledger')
        prose = importlib.import_module('book_test_pack.prose')
        fake_mm = types.ModuleType('comfy.model_management')
        for name in ('unload_all_models','soft_empty_cache','throw_exception_if_processing_interrupted'):
            setattr(fake_mm,name,lambda:None)
        package = fixtures.package_fixture()
        for c,h in zip(package['production']['characters'],[105,8,35]):c['height_cm']=h
        bad = copy.deepcopy(package);bad['story']['pages'][0]['text']='An unresolved costume change happened.'
        def editorial(p,config):
            return {'accepted':True,'package_hash':story.digest(p),'review':{'issues':[]}}
        state_outputs = [
            {'changes':[],'detached_props':[],'uncertain':True,'issues':['The stain has no clear restoration event.']},
        ] * 3 + [
            {'changes':[],'detached_props':[],'uncertain':False,'issues':[]},
            {'valid':True,'issues':[],'evidence':'No consequential appearance changes.'},
        ]
        args = dict(story_idea='Sharing light',age_range='4-6',page_count=3,max_characters=3,
                    art_style=story.DEFAULT_STYLE,seed=128,ollama_url='http://unused',ollama_model='writer',
                    review_model='test',story_attempts=2,plan_visual_state=True)
        # Interruption between drafts must retain the failed draft/ledger but
        # must not produce an accepted plan or public story from it.
        with patch.dict(sys.modules,{'comfy.model_management':fake_mm}), patch.object(nodes,'narrative_outline',return_value={}), patch.object(nodes,'review_story',side_effect=editorial), patch.object(prose,'punctuate_generated_prose',side_effect=lambda p,*args:p), patch.object(quality,'json_model',side_effect=state_outputs) as planner:
            with patch.object(nodes,'ollama_generate',side_effect=[json.dumps(bad),RuntimeError('shutdown')]):
                with self.assertRaisesRegex(RuntimeError,'shutdown'):nodes.BookV2Story().write(**args)
            root = next(storage.books_root().glob('book-128-*'))
            self.assertFalse((root/'plan.json').exists())
            self.assertFalse((root/'story.json').exists())
            self.assertEqual(planner.call_count,3)
            with patch.object(nodes,'ollama_generate',return_value=json.dumps(package)) as writer:
                project,public = nodes.BookV2Story().write(**args)
                self.assertEqual(writer.call_count,1)
                self.assertIn('no clear restoration event',writer.call_args.args[2])
                self.assertEqual(planner.call_count,5)
                self.assertEqual(project['art_plan']['ledger']['changes'],[])
                self.assertEqual(set(json.loads(public)),{'id','pages','metadata'})
                self.assertEqual(project['story']['pages'],package['story']['pages'])
                self.assertTrue((root/'quality/story/attempt-01-draft.txt').exists())
                again,_ = nodes.BookV2Story().write(**args)
                self.assertEqual(writer.call_count,1)
                self.assertEqual(planner.call_count,5)
                self.assertEqual(project['art_plan'],again['art_plan'])

    def test_visual_state_failure_does_not_rewrite_a_supplied_story(self):
        import sys,types
        ledger = importlib.import_module('book_test_pack.state_ledger')
        fake_mm = types.ModuleType('comfy.model_management')
        fake_mm.unload_all_models=lambda:None;fake_mm.soft_empty_cache=lambda:None
        package=fixtures.package_fixture()
        for c,h in zip(package['production']['characters'],[105,8,35]):c['height_cm']=h
        supplied=json.dumps(package['story'])
        with patch.dict(sys.modules,{'comfy.model_management':fake_mm}), patch.object(nodes,'ollama_generate',return_value=json.dumps(package['production'])) as writer, patch.object(nodes,'review_story',return_value={'accepted':True}), patch.object(ledger,'compile_plan',side_effect=ledger.StatePlanningError('Ambiguous stain restoration')):
            with self.assertRaisesRegex(ledger.StatePlanningError,'Ambiguous stain'):
                nodes.BookV2Story().write(story_idea='Existing story',age_range='4-6',page_count=3,max_characters=3,
                    art_style=story.DEFAULT_STYLE,seed=129,ollama_url='http://unused',ollama_model='writer',
                    story_json=supplied,plan_visual_state=True)
            self.assertEqual(writer.call_count,1)
        root=next(storage.books_root().glob('book-129-*'))
        self.assertFalse((root/'plan.json').exists())
        self.assertFalse((root/'story.json').exists())
        self.assertEqual(json.loads(supplied),package['story'])

    def test_page_contradiction_overrides_broad_editorial_approval(self):
        package=fixtures.package_fixture()
        global_review={'checks':{k:True for k in quality.TEXT_CHECKS},'evidence':'Broad review passed.',
                       'issues':[],'uncertain':False}
        audits=[]
        for page in package['story']['pages']:
            audits.append({'pageNumber':page['pageNumber'],'prose_event':'Mouse on palm.','image_event':'Mouse on grass.',
                'checks':{'moment_matches':False,'cast_consistent':True,'action_and_props_match':False,
                          'location_and_scale_consistent':False,'prose_reads_well':True},
                'evidence':'The illustrated position contradicts the prose.','issues':['Mouse is on a palm in prose but grass in art.'],'uncertain':False})
        with patch.object(quality,'json_model',side_effect=[global_review,{'pages':audits}]) as model:
            result=quality.review_story(package,{'age_range':'4-6','story_idea':'test','ollama_url':'http://unused','review_model':'test'},generate=model)
        self.assertFalse(result['accepted'])
        self.assertEqual(len(result['page_audits']),3)

    def test_correction_keeps_reference_indices_and_adds_size_guide(self):
        self.enable_quality()
        self.project['render_settings']['scale_guide']=True
        for c,h in zip(self.project['book']['characters'],[105,8,35]):
            c['height_cm']=h
        spec=story.asset_specs(self.project)[-2]
        graph=render.expand_attempt(self.project,spec,2,'Shrink the rabbit.',1)['expand']
        self.assertEqual(len([n for n in graph.values() if n['class_type']=='ReferenceLatent']),5)
        self.assertEqual(len([n for n in graph.values() if n['class_type']=='BookV2LoadCandidate']),1)
        self.assertEqual(len([n for n in graph.values() if n['class_type']=='BookV2ScaleGuide']),1)
        prompt=next(n['inputs']['text'] for n in graph.values() if n['class_type']=='CLIPTextEncode')
        self.assertIn('Edit image 1',prompt)
        self.assertIn('Image 2: Mira',prompt)
        self.assertIn('Image 5 is a SIZE GUIDE',prompt)

    def test_scale_repair_masks_sampling_and_restores_unmasked_pixels(self):
        self.enable_quality()
        spec=story.asset_specs(self.project)[-2]
        graph=render.expand_attempt(self.project,spec,2,scale_repair=True)['expand']
        types=[n['class_type'] for n in graph.values()]
        self.assertIn('SetLatentNoiseMask',types)
        self.assertIn('ImageCompositeMasked',types)
        self.assertNotIn('EmptyFlux2LatentImage',types)
        self.assertEqual(types.count('ReferenceLatent'),1)
        composite=next((key,n) for key,n in graph.items() if n['class_type']=='ImageCompositeMasked')
        review=next(n for n in graph.values() if n['class_type']=='BookV2ReviewAsset')
        self.assertEqual(review['inputs']['images'],[composite[0],0])
        self.assertEqual(composite[1]['inputs']['destination'][0],composite[1]['inputs']['mask'][0])

    def test_shared_cast_sheet_routes_one_reference_and_keeps_correction_labels(self):
        self.enable_quality()
        self.project['render_settings']['reference_strategy']='cast_guide'
        for c,h in zip(self.project['book']['characters'],[110,50,55]):
            c['height_cm']=h
        spec=story.asset_specs(self.project)[-2]
        for correction,reference_count,label in [(None,1,'characters in Image 1'),(1,1,'Edit Image 1')]:
            graph=render.expand_attempt(self.project,spec,2,'Fix the scene.',correction)['expand']
            types=[n['class_type'] for n in graph.values()]
            self.assertEqual(types.count('ReferenceLatent'),reference_count)
            self.assertEqual(types.count('BookV2ScaleGuide'),0 if correction else 1)
            self.assertNotIn('BookV2LoadReference',types)
            prompt=next(n['inputs']['text'] for n in graph.values() if n['class_type']=='CLIPTextEncode')
            self.assertIn(label,prompt)
            self.assertNotIn('Picture 4',prompt)
            self.assertNotIn('from left to right in the order below',prompt)
            if correction:
                self.assertEqual(types.count('BookV2LoadCandidate'),1)
                self.assertNotIn('Image 2',prompt)
            else:
                self.assertIn('about 2.2 times as tall as Pip',prompt)
        single=story.asset_specs(self.project)[-3]
        graph=render.expand_attempt(self.project,single,1)['expand']
        self.assertNotIn('BookV2ScaleGuide',[n['class_type'] for n in graph.values()])
        self.assertEqual(single['references'],['characters/mira.png','style.png'])

    def test_scene_recomposition_preserves_original_brief_and_reference_count(self):
        self.enable_quality()
        self.project['render_settings'].update(reference_strategy='cast_guide',scene_edit_version=3)
        for c,h in zip(self.project['book']['characters'],[110,50,55]):
            c['height_cm']=h
        spec=next(s for s in story.asset_specs(self.project) if s['name']=='pages/page-002.png')
        graph=render.expand_attempt(self.project,spec,2,'Move Pip to the other side.',1)['expand']
        prompt=next(n['inputs']['text'] for n in graph.values() if n['class_type']=='CLIPTextEncode')
        self.assertIn(self.project['book']['pages'][1]['scene_prompt'],prompt)
        self.assertNotIn(self.project['book']['pages'][1]['text'],prompt)
        self.assertNotIn('Page prose:',prompt)
        self.assertIn('no lettering',prompt)
        self.assertNotIn('Keep the existing composition',prompt)
        self.assertEqual(sum(n['class_type']=='ReferenceLatent' for n in graph.values()),1)
        self.assertEqual(sum(n['class_type']=='BookV2ReviewAsset' for n in graph.values()),1)

    def test_shared_sheet_retry_does_not_reintroduce_the_previous_cast_as_extra_references(self):
        self.enable_quality()
        self.project['render_settings'].update(reference_strategy='cast_guide',art_attempts=5,pose_guide_version=1)
        for c,h in zip(self.project['book']['characters'],[110,50,55]):c['height_cm']=h
        spec=story.asset_specs(self.project)[-2]
        report=visual_report(self.project,spec)
        report['accepted']=False
        report['review']['checks']['scene_matches']=False
        report['review']['issues']=['The rabbit must point toward the pebbles.']
        report['review']['retry_instructions']=['Pip points DOWN toward the pebbles.']
        report['review']['retry_scene']='The cream rabbit lowers its arm toward the stones. Mira rests her hands on her knees.'
        storage.write_json(storage.review_directory(self.project,spec)/'attempt-01-review.json',report)
        repair=importlib.import_module('book_test_pack.repair')
        with patch.object(repair,'try_scale_repair',return_value=False),patch.object(nodes,'expand_attempt',return_value={}) as expand:
            nodes.BookV2RenderAsset().run(self.project,spec,'')
        self.assertEqual(expand.call_args.args[4],1)
        self.assertEqual(expand.call_args.args[2],2)
        self.assertEqual(expand.call_args.args[3],report['review']['retry_scene']+'\nPip points DOWN toward the pebbles.')
        storage.write_json(storage.review_directory(self.project,spec)/'attempt-02-review.json',report)
        pose=importlib.import_module('book_test_pack.pose')
        with patch.object(repair,'try_scale_repair',return_value=False),patch.object(pose,'try_pose_guide',return_value=True) as prepare,patch.object(nodes,'expand_attempt',return_value={}) as expand:
            nodes.BookV2RenderAsset().run(self.project,spec,'')
        self.assertEqual(prepare.call_args.args[2:4],(2,3))
        self.assertEqual(expand.call_args.kwargs,{'pose_guide':True})

    def test_pose_edit_uses_previous_scene_and_diagram_without_extra_portraits(self):
        self.enable_quality()
        self.project['render_settings']['reference_strategy']='cast_guide'
        for c,h in zip(self.project['book']['characters'],[110,50,55]):c['height_cm']=h
        spec=story.asset_specs(self.project)[-2]
        graph=render.expand_attempt(self.project,spec,3,'Point at the stone.',2,pose_guide=True)['expand']
        types=[n['class_type'] for n in graph.values()]
        self.assertEqual(types.count('ReferenceLatent'),2)
        self.assertEqual(types.count('BookV2LoadCandidate'),1)
        self.assertEqual(types.count('BookV2LoadPoseGuide'),1)
        self.assertNotIn('BookV2ScaleGuide',types)
        self.assertNotIn('BookV2LoadReference',types)
        with self.assertRaisesRegex(ValueError,'existing shared-cast scene'):
            render.expand_attempt(self.project,spec,3,pose_guide=True)

    def test_pose_plan_rejects_duplicate_cast_and_resumes_without_replanning(self):
        pose=importlib.import_module('book_test_pack.pose')
        self.enable_quality()
        spec=story.asset_specs(self.project)[-2]
        ids=quality.expected_scene(self.project,spec)[0]
        figures=[]
        for i,cid in enumerate(ids):
            x=200+i*280
            figures.append({'id':cid,'shape':'human','head':[x,280],'head_radius':55,
                'shoulders':[x,370],'hips':[x,550],'left_elbow':[x-60,450],'left_hand':[x-80,530],
                'right_elbow':[x+60,450],'right_hand':[x+80,530],'left_knee':[x-25,630],
                'left_foot':[x-30,740],'right_knee':[x+25,630],'right_foot':[x+30,740],
                'target':[500,900],'pointing_hand':'neither','head_color':'#eac49f','body_color':'#cd4545',
                'legs_color':'#407abe','foot_color':'#ebcd30','accent_color':'#73523b'})
        layout={'intent':'Three friends in distinct poses.','figures':figures,'props':[]}
        pose.validate_layout(layout,ids)
        bad=copy.deepcopy(layout);bad['figures'][1]['id']=ids[0]
        with self.assertRaisesRegex(ValueError,'exactly once'):pose.validate_layout(bad,ids)
        bad=copy.deepcopy(layout);bad['figures'][1]['left_hand']=[100,700]
        with self.assertRaisesRegex(ValueError,'long diagram limb'):pose.validate_layout(bad,ids)
        directory=storage.review_directory(self.project,spec)
        source=b'original candidate';storage.write_exclusive(directory/'attempt-02.png',source)
        report=visual_report(self.project,spec);report['png_sha256']=hashlib.sha256(source).hexdigest()
        report['layout_review']={'story_event_visible':False,'uncertain':False,
            'essential_issues':['The required pointing action is absent.'],
            'retry_instructions':['Point toward the object.'],'retry_scene':'The friends point toward the object.'}
        calls=[]
        def generate(*args):calls.append(args);return layout
        self.assertTrue(pose.try_pose_guide(self.project,spec,2,3,report,generate=generate))
        png=(directory/'attempt-03-pose.png').read_bytes()
        (directory/'attempt-03-pose.png').unlink()  # interrupted between plan publication and PNG publication
        self.assertTrue(pose.try_pose_guide(self.project,spec,2,3,report,generate=generate))
        self.assertEqual(len(calls),1)
        self.assertEqual((directory/'attempt-03-pose.png').read_bytes(),png)
        (directory/'attempt-03-pose.png').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'pixels differ'):
            pose.try_pose_guide(self.project,spec,2,3,report,generate=generate)

    def test_resize_locations_require_preserved_pixels_and_survive_exact_pixel_reuse(self):
        import io
        import numpy as np
        from PIL import Image,PngImagePlugin
        preserved=importlib.import_module('book_test_pack.preserved')
        self.enable_quality()
        spec=story.asset_specs(self.project)[-2]
        directory=storage.review_directory(self.project,spec)
        def png(array,source=None):
            info=PngImagePlugin.PngInfo();info.add_text('book_asset',json.dumps(spec))
            if source:info.add_text('book_source',json.dumps(source))
            data=io.BytesIO();Image.fromarray(array).save(data,format='PNG',pnginfo=info);return data.getvalue()
        original=png(np.full((1024,1024,3),100,dtype='uint8'))
        prepared=np.full((1024,1024,3),120,dtype='uint8');prepared[300:400,200:300]=200
        mask=np.full((1024,1024),255,dtype='uint8');mask[300:400,200:300]=0
        prepared_data=png(prepared);mask_data=png(mask)
        final=np.full((1024,1024,3),150,dtype='uint8');final[300:400,200:300]=200
        data=png(final)
        for name,value in [('attempt-01.png',original),('attempt-02.png',data),
                           ('attempt-02-repair-image.png',prepared_data),('attempt-02-repair-mask.png',mask_data)]:
            storage.write_exclusive(directory/name,value)
        storage.write_json(directory/'attempt-02-repair.json',{'prepared':True,'signature':spec['signature'],
            'target':'pip','source_attempt':1,'source_sha256':hashlib.sha256(original).hexdigest(),
            'image_sha256':hashlib.sha256(prepared_data).hexdigest(),'mask_sha256':hashlib.sha256(mask_data).hexdigest(),
            'geometry':{'position':[200,300],'source_bbox':[100,100,300,300],'factor':.5}})
        self.assertEqual(preserved.preserved_boxes(self.project,spec,data,2)['pip']['bbox'],[200,300,300,400])
        cached=png(final,{'path':str(directory/'attempt-02.png'),'png_sha256':hashlib.sha256(data).hexdigest()})
        storage.write_exclusive(directory/'attempt-03.png',cached)
        self.assertIn('pip',preserved.preserved_boxes(self.project,spec,cached,3))
        final[350,250]=210;changed=png(final)
        (directory/'attempt-02.png').write_bytes(changed)
        self.assertEqual(preserved.preserved_boxes(self.project,spec,changed,2),{})
        self.assertEqual(preserved.preserved_boxes(self.project,spec,cached,3),{})

    def test_scale_repair_cannot_salvage_wrong_identity_or_missing_cast(self):
        repair=importlib.import_module('book_test_pack.repair')
        spec=story.asset_specs(self.project)[-2]
        report=visual_report(self.project,spec)
        report['review']['characters'][0]['scale_matches']=False
        self.assertTrue(repair.eligible_scale_repair(report))
        multiple=copy.deepcopy(report)
        multiple['review']['characters'][1]['scale_matches']=False
        self.assertTrue(repair.eligible_scale_repair(multiple))
        for field,value in [('count',0),('identity_matches',False),('appearance_matches',False)]:
            bad=copy.deepcopy(report);bad['review']['characters'][1][field]=value
            self.assertFalse(repair.eligible_scale_repair(bad))
        bad=copy.deepcopy(report);bad['review']['checks']['scene_matches']=False
        self.assertFalse(repair.eligible_scale_repair(bad))

    def test_outline_editor_rejects_a_time_paradox_before_story_writing(self):
        planning=importlib.import_module('book_test_pack.planning')
        report={'checks':{'causal_plot':False,'clear_original_problem':True,'character_agency':True,
            'earned_resolution':False,'continuity':False,'engaging_page_turns':True,'age_appropriate':True},
            'evidence':'The letter thanks a repair before that repair happened.',
            'issues':['Beat 12 contains a time paradox.'],'uncertain':False}
        result=planning.review_outline({'title':'Impossible thank-you'},
            {'ollama_url':'http://unused','review_model':'test','age_range':'4-6','story_idea':'post office'},
            generate=lambda *args:report)
        self.assertFalse(result['accepted'])

    def test_detector_geometry_distinguishes_oversized_and_repaired_fox(self):
        detection=importlib.import_module('book_test_pack.detection')
        anchor=[175,120,611,940]
        bad=detection.relative_size([585,521,929,958],anchor,30,105)
        fixed=detection.relative_size([658,714,856,958],anchor,30,105)
        self.assertFalse(bad['scale_matches'])
        self.assertTrue(fixed['scale_matches'])
        self.assertGreater(bad['relative_factor'],1.8)
        self.assertAlmostEqual(fixed['relative_factor'],1.04,places=2)

    def test_book_heights_are_numeric_ratios_not_guessed_waist_landmarks(self):
        detection=importlib.import_module('book_test_pack.detection')
        scale=importlib.import_module('book_test_pack.scale')
        cast=[{'id':'pip','height_cm':60,'appearance':'Small anthropomorphic panda.'},
              {'id':'maya','height_cm':50,'appearance':'Slender anthropomorphic monkey.'},
              {'id':'leo','height_cm':90,'appearance':'Sturdy lion.'}]
        ratios={r['id']:r for r in scale.height_targets(cast)}
        self.assertAlmostEqual(ratios['pip']['standing_height_ratio'],2/3)
        self.assertAlmostEqual(ratios['maya']['standing_height_ratio'],5/9)
        self.assertEqual(detection.detection_phrase(cast[0]),'a panda.')
        self.assertEqual(detection.detection_phrase(cast[1]),'a monkey.')
        boxes={'leo':{'bbox':[300,100,700,900]},'pip':{'bbox':[30,375,250,915]},
               'maya':{'bbox':[720,466,930,916]}}
        poses={c['id']:{'pose':'standing_upright','full_body_visible':True,'same_depth_as_largest':True,
                        'independent_ground_contact':True,'scale_matches':False} for c in cast}
        measured=detection.measure_cast_scale(cast,boxes,poses)
        self.assertTrue(all(r['measurement_decisive'] and r['scale_matches'] for r in measured.values()))
        boxes['maya']['bbox']=[720,180,930,916]
        self.assertFalse(detection.measure_cast_scale(cast,boxes,poses)['maya']['scale_matches'])

    def test_compressed_and_held_figures_have_a_size_ceiling_but_distinct_repair_rules(self):
        detection=importlib.import_module('book_test_pack.detection')
        cast=[{'id':'child','height_cm':110},{'id':'mouse','height_cm':8}]
        boxes={'child':{'bbox':[200,100,600,900]},'mouse':{'bbox':[20,600,170,800]}}
        poses={'child':{'pose':'standing_upright','full_body_visible':True},
               'mouse':{'pose':'jumping','full_body_visible':True,'same_depth_as_largest':True,
                        'independent_ground_contact':True,'scale_matches':True}}
        result=detection.measure_cast_scale(cast,boxes,poses)['mouse']
        self.assertFalse(result['scale_matches'])
        self.assertTrue(result['safe_to_resize'])
        poses['mouse']['pose']='held'
        held=detection.measure_cast_scale(cast,boxes,poses)['mouse']
        self.assertTrue(held['measurement_decisive'])
        self.assertTrue(held['safe_to_resize'])
        self.assertTrue(held['requires_supported_contact'])
        poses['mouse']['pose']='crouching'
        boxes['mouse']['bbox']=[20,780,60,800]
        small=detection.measure_cast_scale(cast,boxes,poses)['mouse']
        self.assertFalse(small['measurement_decisive'])
        self.assertFalse(small['safe_to_resize'])
        poses['mouse']['pose']='sitting'
        self.assertFalse(detection.measure_cast_scale(cast,boxes,poses)['mouse']['measurement_decisive'])
        poses['mouse']['same_depth_as_largest']=False
        self.assertEqual(detection.measure_cast_scale(cast,boxes,poses),{})
        poses['mouse']['same_depth_as_largest']=True
        poses['child'].update(pose='jumping',body_extended=False)
        self.assertEqual(detection.measure_cast_scale(cast,boxes,poses),{})
        poses['child']['body_extended']=True
        self.assertIn('mouse',detection.measure_cast_scale(cast,boxes,poses))

    def test_held_resize_requires_contact_only_at_the_base(self):
        import numpy as np
        repair=importlib.import_module('book_test_pack.repair')
        target=np.zeros((100,100),dtype=np.uint8);target[20:60,40:60]=255
        palm=np.zeros_like(target);palm[60:70,25:75]=255
        repair.validate_support_contact(target,palm)
        torso=np.zeros_like(target);torso[10:80,30:40]=255
        with self.assertRaisesRegex(ValueError,'base contact'):
            repair.validate_support_contact(target,torso)
        with self.assertRaisesRegex(ValueError,'base contact'):
            repair.validate_support_contact(target,np.zeros_like(target))

    def test_transient_writer_disconnect_retries_without_changing_request(self):
        with patch.object(nodes,'_ollama_generate_once',side_effect=[RuntimeError('Disconnected'),'{"title":"Done"}']) as request:
            value=nodes.ollama_generate('http://unused','writer','prompt',{},42)
        self.assertEqual(value,'{"title":"Done"}')
        self.assertEqual(request.call_count,2)
        self.assertEqual(request.call_args_list[0],request.call_args_list[1])
        with patch.object(nodes,'_ollama_generate_once',side_effect=RuntimeError('Offline')) as request:
            with self.assertRaisesRegex(RuntimeError,'Offline'):
                nodes.ollama_generate('http://unused','writer','prompt',{},42)
        self.assertEqual(request.call_count,3)

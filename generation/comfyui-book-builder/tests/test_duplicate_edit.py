import copy, hashlib, importlib, json
from unittest.mock import patch
import unittest
import test_book as fixtures
from test_quality import visual_report

policy=importlib.import_module('book_test_pack.duplicate_edit')


class DuplicateEditTests(unittest.TestCase):
    setUp=fixtures.BookTests.setUp
    restore_module=fixtures.BookTests.restore_module

    def case(self):
        self.project['config']['ollama_url']='http://test-unused'
        self.project['render_settings'].update(renderer='flux2', reference_strategy='cast_guide',
            flux_scene_recipe='turbo8_native', flux_guidance=4., flux_steps=28, scene_edit_version=6,
            duplicate_edit_policy=1, review_model='test-unused', **fixtures.render.FLUX_MODELS)
        spec=next(s for s in fixtures.story.asset_specs(self.project) if s['name']=='pages/page-002.png')
        report=visual_report(self.project,spec,False)
        report['review']['issues']=['One extra mouse.']
        report['png_sha256']=hashlib.sha256(b'candidate').hexdigest()
        directory=fixtures.storage.review_directory(self.project,spec);directory.mkdir(parents=True,exist_ok=True)
        (directory/'attempt-01.png').write_bytes(b'candidate')
        (directory/'attempt-01-review.json').write_text(json.dumps(report))
        plan={'decision':'remove_duplicate','character_id':'pip',
            'keep':{'location':'the left mouse in the blue scarf','gaze_and_interaction':'Looks at Mira holding the light.',
                    'effect_of_removing_this_copy':'Mira would address an empty patch of ground.'},
            'remove':{'location':'the right mouse in the blue scarf','gaze_and_interaction':'Faces the edge of the garden.',
                      'effect_of_removing_this_copy':'Reveals garden foliage.'},
            'reason':'Preserve the shared light interaction.',
            'preserve':['Mira looks down at the left mouse','Fern holds the ribbon of moonlight'],
            'fill':'the surrounding garden foliage',
            'remaining_defects_after_removal':[],
            'checks':{k:True for k in policy.PLAN_SCHEMA['properties']['checks']['properties']}}
        return spec,report,plan,directory

    def test_missing_or_merged_cast_cannot_use_duplicate_removal(self):
        spec,r,_,_=self.case();ids=['mira','pip','fern']
        self.assertTrue(policy.eligible(r,ids))
        for key,value in [('count',0),('identity_matches',False),('appearance_matches',False),('scale_matches',False)]:
            bad=copy.deepcopy(r);bad['review']['characters'][0][key]=value
            self.assertFalse(policy.eligible(bad,ids))
        r['review']['unexpected_character_count']=2;self.assertFalse(policy.eligible(r,ids))

    def test_unresolved_gaze_or_identical_locations_cannot_authorize_edit(self):
        spec,r,plan,_=self.case()
        plan['checks']['other_characters_keep_meaningful_gaze']=False
        value=policy.plan_edit(self.project,spec,b'candidate',r,lambda *a,**k:copy.deepcopy(plan))
        self.assertEqual(value['decision'],'uncertain')
        plan['checks']['other_characters_keep_meaningful_gaze']=True
        plan['remove']['location']=plan['keep']['location']
        value=policy.plan_edit(self.project,spec,b'candidate',r,lambda *a,**k:copy.deepcopy(plan))
        self.assertEqual(value['decision'],'uncertain')

    def test_recovery_reuses_exact_plan_but_never_repeats_a_failed_removal(self):
        spec,r,plan,d=self.case()
        record=policy.prepare_edit(self.project,spec,1,2,r,lambda *a,**k:plan)
        strategy={'signature':spec['signature'],'strategy':'duplicate_removal','source_attempt':1}
        (d/'attempt-02-strategy.json').write_text(json.dumps(strategy))
        self.assertEqual(policy.prepare_edit(self.project,spec,1,2,r,lambda *a,**k:self.fail('Must resume')),record)
        self.assertIsNone(policy.prepare_edit(self.project,spec,1,3,r,lambda *a,**k:self.fail('One removal only')))
        (d/'attempt-01.png').write_bytes(b'changed');self.assertIsNone(policy.prepare_edit(self.project,spec,1,2,r))

    def test_sampler_gets_single_saved_scene_and_only_the_targeted_prompt(self):
        spec,r,plan,d=self.case();record=policy.prepare_edit(self.project,spec,1,2,r,lambda *a,**k:plan)
        graph=fixtures.render.expand_attempt(self.project,spec,2,correction_attempt=1,duplicate_plan=record)['expand']
        self.assertEqual(sum(n['class_type']=='ReferenceLatent' for n in graph.values()),1)
        self.assertFalse(any(n['class_type']=='LoraLoaderModelOnly' for n in graph.values()))
        text=next(n['inputs']['text'] for n in graph.values() if n['class_type']=='CLIPTextEncode')
        self.assertEqual(text,record['prompt']);self.assertIn('Mira looks down at the left mouse',text)
        self.assertEqual(next(n['inputs']['steps'] for n in graph.values() if n['class_type']=='Flux2Scheduler'),28)
        provenance=json.loads(next(n['inputs']['generation_info'] for n in graph.values() if n['class_type']=='BookV2ReviewAsset'))
        self.assertEqual(provenance['method'],'image_edit')
        self.assertEqual(provenance['steps'],28)
        self.assertEqual(provenance['loras'],[])

    def test_location_only_plan_still_names_the_character_in_executed_prompt(self):
        spec,r,plan,d=self.case()
        plan['remove']['location']='right side of the rock crevice'
        plan['keep']['location']='left side of the rock crevice'
        record=policy.prepare_edit(self.project,spec,1,2,r,lambda *a,**k:plan)
        graph=fixtures.render.expand_attempt(self.project,spec,2,correction_attempt=1,duplicate_plan=record)['expand']
        prompt=next(n['inputs']['text'] for n in graph.values() if n['class_type']=='CLIPTextEncode')
        character=next(c for c in self.project['book']['characters'] if c['id']==plan['character_id'])
        self.assertIn('Remove the extra '+character['name'],prompt)
        self.assertIn(character['appearance'].split('.')[0],prompt)
        self.assertIn('Its location is: right side of the rock crevice',prompt)
        self.assertNotIn('Remove only right side of the rock crevice',prompt)

    def test_other_remaining_story_defects_prevent_removal_only_repair(self):
        spec,r,plan,_=self.case()
        plan['remaining_defects_after_removal']=['A second copy of the story prop remains.']
        result=policy.plan_edit(self.project,spec,b'candidate',r,lambda *a,**k:plan)
        self.assertNotEqual(result['decision'],'remove_duplicate')

    def test_changed_interaction_vetoes_otherwise_approved_art(self):
        spec,r,plan,d=self.case();policy.prepare_edit(self.project,spec,1,2,r,lambda *a,**k:plan)
        (d/'attempt-02-strategy.json').write_text(json.dumps({'signature':spec['signature'],'strategy':'duplicate_removal'}))
        compare={'checks':{k:True for k in policy.PRESERVATION_CHECKS},'uncertain':False,
                 'issues':['Mira now looks away from the surviving mouse.'],'evidence':'Gaze changed.'}
        compare['checks']['gaze_and_interactions_preserved']=False
        report=visual_report(self.project,spec,True)
        result=policy.apply_edit_review(self.project,spec,2,b'edited',report,lambda *a,**k:compare)
        self.assertFalse(result['accepted']);self.assertFalse(result['review']['checks']['scene_matches'])

    def test_turbo_controller_can_choose_bounded_interaction_preserving_edit(self):
        spec,r,plan,d=self.case();self.project['render_settings']['art_attempts']=5
        nodes=importlib.import_module('book_test_pack.nodes')
        record=policy.prepare_edit(self.project,spec,1,2,r,lambda *a,**k:plan)
        with patch.object(policy,'prepare_edit',return_value=record),patch.object(nodes,'expand_attempt',return_value={}) as expand:
            nodes.BookV2RenderAsset().run(self.project,spec,'')
        self.assertEqual(expand.call_args.kwargs['duplicate_plan'],record)
        self.assertEqual(expand.call_args.kwargs['correction_attempt'],1)
        self.assertEqual(json.loads((d/'attempt-02-strategy.json').read_text())['strategy'],'duplicate_removal')

    def test_retry_policy_preserves_existing_state_checkpoint_and_asset_signatures(self):
        self.case()
        state=importlib.import_module('book_test_pack.state_edit')
        first=state.attach_edits(self.project,{})
        path=fixtures.storage.checked_root(first)/'prepared-state-project.json'
        original=path.read_bytes();signatures=fixtures.story.asset_specs(first)
        resumed={**first,'runtime_retry_policy':{'duplicate_edit_policy':1}}
        result=state.attach_edits(resumed,{})
        self.assertEqual(result['runtime_retry_policy'],resumed['runtime_retry_policy'])
        self.assertEqual(path.read_bytes(),original)
        self.assertEqual(fixtures.story.asset_specs(result),signatures)

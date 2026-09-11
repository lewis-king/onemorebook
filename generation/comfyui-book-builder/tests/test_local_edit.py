"""Regression coverage for retaining story constraints during focused corrections."""
import importlib
import json
import unittest
from unittest.mock import patch

import test_book as fixtures
from test_quality import visual_report


class LocalEditTests(unittest.TestCase):
    setUp = fixtures.BookTests.setUp
    restore_module = fixtures.BookTests.restore_module

    def scene(self, version=5):
        self.project['render_settings'].update(renderer='flux2', reference_strategy='cast_guide',
            scene_edit_version=version, flux_guidance=4.0, flux_steps=28, art_attempts=5)
        self.project['render_settings'].update(fixtures.render.FLUX_MODELS)
        for c,h in zip(self.project['book']['characters'],[110,50,55]):
            c['height_cm']=h
        return next(s for s in fixtures.story.asset_specs(self.project) if s['name']=='pages/page-002.png')

    def test_action_correction_keeps_original_actor_roles_without_replacing_whole_scene(self):
        spec=self.scene()
        graph=fixtures.render.expand_attempt(self.project,spec,2,'Aim the pointing paw at the stones.',1)['expand']
        prompt=next(n['inputs']['text'] for n in graph.values() if n['class_type']=='CLIPTextEncode')
        self.assertIn('Aim the pointing paw at the stones.',prompt)
        self.assertIn(self.project['book']['pages'][1]['scene_prompt'],prompt)
        self.assertIn('Keep every already-correct pose, prop and interaction unchanged.',prompt)
        self.assertNotIn('Reposition the characters and props',prompt)
        self.assertEqual(sum(n['class_type']=='ReferenceLatent' for n in graph.values()),1)
        self.assertEqual(sum(n['class_type']=='BookV2ReviewAsset' for n in graph.values()),1)

    def test_controller_retains_specific_corrections_and_avoids_duplicate_scene_description(self):
        nodes=importlib.import_module('book_test_pack.nodes')
        repair=importlib.import_module('book_test_pack.repair')
        spec=self.scene()
        report=visual_report(self.project,spec)
        report['accepted']=False
        report['review']['checks']['scene_matches']=False
        report['review']['retry_instructions']=['Restore the required ball inside the bubble.']
        report['review']['retry_scene']='A repeated complete description of every character.'
        directory=fixtures.storage.review_directory(self.project,spec)
        directory.mkdir(parents=True,exist_ok=True)
        (directory/'attempt-01-review.json').write_text(json.dumps(report))
        with patch.object(repair,'try_scale_repair',return_value=False), patch.object(nodes,'expand_attempt',return_value={}) as expand:
            nodes.BookV2RenderAsset().run(self.project,spec,'')
        self.assertEqual(expand.call_args.args[3],'Restore the required ball inside the bubble.')
        self.assertEqual(expand.call_args.args[4],1)
        report['review']['retry_instructions']=[]
        (directory/'attempt-01-review.json').write_text(json.dumps(report))
        with patch.object(repair,'try_scale_repair',return_value=False), patch.object(nodes,'expand_attempt',return_value={}) as expand:
            nodes.BookV2RenderAsset().run(self.project,spec,'')
        self.assertIn(report['review']['retry_scene'],expand.call_args.args[3])

    def test_first_render_and_model_configuration_are_unchanged(self):
        spec=self.scene(version=4)
        before=fixtures.render.expand_attempt(self.project,spec,1)['expand']
        self.project['render_settings']['scene_edit_version']=5
        after=fixtures.render.expand_attempt(self.project,spec,1)['expand']
        def instructions(graph):
            return [(n['class_type'],{k:v for k,v in n['inputs'].items() if not isinstance(v,list)}) for n in graph.values()
                    if n['class_type'] in ('CLIPTextEncode','UNETLoader','Flux2Scheduler','FluxGuidance')]
        self.assertEqual(instructions(before),instructions(after))

    def test_tail_correction_keeps_precise_target_and_anatomy_veto(self):
        quality=importlib.import_module('book_test_pack.quality')
        spec=self.scene()
        report=visual_report(self.project,spec)['review']
        instruction='Remove the curled tail attached to the sloth in the pink apron; preserve the monkey tail.'
        quality.apply_tail_review(report,{'checks':{'tails_plausible':False},'uncertain':False,
            'issues':['Extra tail attached to sloth.'],'retry_instructions':[instruction]})
        self.assertFalse(report['checks']['anatomy_sound'])
        self.assertIn(instruction,report['retry_instructions'])
        self.assertIn('Extra tail attached to sloth.',report['issues'])


if __name__ == '__main__':
    unittest.main()

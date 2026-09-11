import copy
import importlib
import json
from unittest.mock import patch
import unittest

import test_book as fixtures
from test_quality import visual_report

scope = importlib.import_module('book_test_pack.retry_scope')


class RetryScopeTests(unittest.TestCase):
    setUp = fixtures.BookTests.setUp
    restore_module = fixtures.BookTests.restore_module

    def measured_failure(self, factor=2.0):
        self.project['render_settings'].update(renderer='flux2', reference_strategy='cast_guide', scene_edit_version=4,
                                              flux_guidance=4.0, flux_steps=28)
        self.project['render_settings'].update(fixtures.render.FLUX_MODELS)
        for c, h in zip(self.project['book']['characters'], [110,50,55]):
            c['height_cm'] = h
        spec = next(s for s in fixtures.story.asset_specs(self.project) if s['name']=='pages/page-002.png')
        report = visual_report(self.project, spec)
        report['accepted'] = False
        report['review']['characters'][-1]['scale_matches'] = False
        report['review']['issues'] = ['fern scale: Measured character is oversized.']
        report['geometry'] = {'fern': {'relative_factor':factor, 'intended_ratio':.5,
                                       'anchor_id':'mira', 'measurement_decisive':True}}
        return spec, report

    def test_stalled_edits_restart_but_improvement_keeps_edit_available(self):
        _, previous = self.measured_failure(2.0)
        _, unchanged = self.measured_failure(2.1)
        _, improving = self.measured_failure(1.3)
        self.assertTrue(scope.scale_edit_stalled(previous, unchanged))
        self.assertFalse(scope.scale_edit_stalled(previous, improving))

    def test_action_identity_and_uncertain_failures_cannot_be_size_only(self):
        _, report = self.measured_failure()
        mutations = [lambda r:r['review']['checks'].update(scene_matches=False),
                     lambda r:r['review']['characters'][0].update(identity_matches=False),
                     lambda r:r['review']['issues'].append('The ball is missing.'),
                     lambda r:r['geometry']['fern'].update(measurement_decisive=False),
                     lambda r:r['review'].update(uncertain=True)]
        for mutate in mutations:
            bad=copy.deepcopy(report);mutate(bad)
            self.assertFalse(scope.scale_only_targets(bad))

    def test_measured_size_edit_retains_current_cast_reference_and_only_changes_size(self):
        spec, report = self.measured_failure()
        path=fixtures.storage.review_directory(self.project,spec)/'attempt-01-review.json'
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report))
        graph=fixtures.render.expand_attempt(self.project,spec,2,'Fix size',1)['expand']
        self.assertEqual(sum(n['class_type']=='ReferenceLatent' for n in graph.values()),2)
        self.assertEqual(sum(n['class_type']=='BookV2ScaleGuide' for n in graph.values()),1)
        prompt=next(n['inputs']['text'] for n in graph.values() if n['class_type']=='CLIPTextEncode')
        self.assertIn('50% of its CURRENT illustrated height',prompt)
        self.assertIn('Image 2 is the approved reference sheet',prompt)
        self.assertIn('Preserve all faces, expressions',prompt)
        self.assertNotIn('Reposition the characters',prompt)
        self.assertNotIn('Authoritative original scene:',prompt)

    def test_controller_stops_repeating_ineffective_size_edit(self):
        nodes=importlib.import_module('book_test_pack.nodes')
        repair=importlib.import_module('book_test_pack.repair')
        spec, first=self.measured_failure(2.0)
        _, second=self.measured_failure(2.1)
        self.project['render_settings']['art_attempts']=5
        directory=fixtures.storage.review_directory(self.project,spec)
        directory.mkdir(parents=True,exist_ok=True)
        for i, report in enumerate((first,second),1):
            (directory/f'attempt-{i:02d}-review.json').write_text(json.dumps(report))
        with patch.object(repair,'try_scale_repair',return_value=False), patch.object(nodes,'expand_attempt',return_value={}) as expand:
            nodes.BookV2RenderAsset().run(self.project,spec,'')
        self.assertEqual(expand.call_args.args[2],3)
        self.assertIsNone(expand.call_args.args[4])
        decision=json.loads((directory/'attempt-03-strategy.json').read_text())
        self.assertEqual(decision['strategy'],'canonical_redraw')
        self.assertIn('did not improve',decision['reason'])

    def test_held_object_veto_blocks_a_false_independent_resize_verdict(self):
        repair=importlib.import_module('book_test_pack.repair')
        audit={'can_resize_independently':True,'uncertain':False,'anchored_interactions':[],
               'target_holds_object':True,'held_objects':['honey jar']}
        self.assertFalse(repair.resize_relations_allow(audit))
        audit.update(target_holds_object=False,held_objects=[])
        self.assertTrue(repair.resize_relations_allow(audit))


if __name__ == '__main__':
    unittest.main()

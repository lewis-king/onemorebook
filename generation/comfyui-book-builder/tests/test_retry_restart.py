"""Bound unsuccessful scene editing while retaining meaningful local progress."""
import copy
import importlib
import json
import unittest
from unittest.mock import patch

import test_book as fixtures
from test_quality import visual_report

scope = importlib.import_module('book_test_pack.retry_scope')


def report(*failed):
    checks = {name: name not in failed for name in ('scene_matches', 'style_matches', 'anatomy_sound')}
    return {'accepted': False, 'review': {'checks': checks, 'issues': ['A required detail is incorrect.'],
            'uncertain': False, 'unexpected_character_count': 0, 'characters': [
                {'id': 'pip', 'count': 1, 'identity_matches': True, 'appearance_matches': True, 'scale_matches': True}]}}


def edit(source):
    return {'strategy': 'scene_edit', 'source_attempt': source}


class RestartDecisionTests(unittest.TestCase):
    def decision(self, reports, strategies):
        return scope.scene_edit_restart(list(enumerate(reports, 1)), strategies, ['pip'])

    def test_first_failure_or_fresh_redraw_does_not_count_as_a_failed_edit(self):
        first = report('scene_matches')
        self.assertIsNone(self.decision([first], {}))
        self.assertIsNone(self.decision([first, first], {2: {'strategy': 'canonical_redraw'}}))

    def test_one_unchanged_failed_edit_triggers_fresh_even_if_wording_changed(self):
        first = report('scene_matches')
        second = copy.deepcopy(first)
        second['review']['issues'] = ['The contact is still at the wrong location.']
        before = copy.deepcopy((first, second))
        decision = self.decision([first, second], {2: edit(1)})
        self.assertEqual(decision['decision'], 'canonical_redraw')
        self.assertIn('same review gates', decision['reason'])
        self.assertEqual((first, second), before)

    def test_new_clothing_or_cast_failure_triggers_fresh(self):
        first = report('scene_matches')
        for changes in ({'appearance_matches': False}, {'count': 0}, {'identity_matches': False}):
            second = copy.deepcopy(first)
            second['review']['characters'][0].update(changes)
            self.assertIn('new failed', self.decision([first, second], {2: edit(1)})['reason'])

    def test_removing_failed_gates_allows_one_more_edit(self):
        self.assertIsNone(self.decision([report('scene_matches', 'style_matches'), report('style_matches')], {2: edit(1)}))

    def test_two_edits_is_the_limit_even_with_incremental_progress(self):
        reports = [report('scene_matches', 'style_matches', 'anatomy_sound'),
                   report('scene_matches', 'style_matches'), report('style_matches')]
        decision = self.decision(reports, {2: edit(1), 3: edit(2)})
        self.assertEqual(decision['consecutive_scene_edits'], 2)
        self.assertIn('Two consecutive', decision['reason'])

    def test_fresh_render_resets_the_edit_chain(self):
        reports = [report('scene_matches'), report('scene_matches'),
                   report('scene_matches', 'style_matches'), report('style_matches')]
        self.assertIsNone(self.decision(reports, {2: edit(1), 3: {'strategy': 'canonical_redraw'}, 4: edit(3)}))

    def test_measured_masked_repair_is_not_a_generic_scene_edit(self):
        self.assertIsNone(self.decision([report('scene_matches'), report('scene_matches')],
                                       {2: {'strategy': 'masked_size_repair', 'source_attempt': 1}}))

    def test_invalid_or_missing_source_cannot_invent_a_stalled_chain(self):
        for source in (None, 2, 99, True):
            self.assertIsNone(self.decision([report('scene_matches'), report('scene_matches')], {2: edit(source)}))

    def test_approved_result_never_triggers_a_retry(self):
        second = report('scene_matches')
        second['accepted'] = True
        self.assertIsNone(self.decision([report('scene_matches'), second], {2: edit(1)}))


class RestartControllerTests(unittest.TestCase):
    setUp = fixtures.BookTests.setUp
    restore_module = fixtures.BookTests.restore_module

    def setup_reports(self, version=6, missing_cast=False, measured_scale=False):
        self.project['render_settings'].update(renderer='flux2', reference_strategy='cast_guide',
            scene_edit_version=version, flux_guidance=4.0, flux_steps=28, art_attempts=5,
            candidate_recovery_policy=1, pose_guide_version=3)
        self.project['render_settings'].update(fixtures.render.FLUX_MODELS)
        for character, height in zip(self.project['book']['characters'], [110, 50, 55]):
            character['height_cm'] = height
        spec = next(s for s in fixtures.story.asset_specs(self.project) if s['name'] == 'pages/page-002.png')
        first = visual_report(self.project, spec)
        first['accepted'] = False
        first['review']['checks']['scene_matches'] = False
        first['review']['issues'] = ['The required contact is absent.']
        first['review']['retry_instructions'] = ['Show the required contact.']
        second = copy.deepcopy(first)
        if missing_cast:
            second['review']['characters'][0]['count'] = 0
        if measured_scale:
            for item in (first, second):
                item['review']['checks']['scene_matches'] = True
                item['review']['characters'][-1]['scale_matches'] = False
                item['review']['issues'] = ['fern scale: Measured character is oversized.']
                item['geometry'] = {'fern': {'relative_factor': 2, 'intended_ratio': .5,
                                            'anchor_id': 'mira', 'measurement_decisive': True}}
        directory = fixtures.storage.review_directory(self.project, spec)
        directory.mkdir(parents=True, exist_ok=True)
        for number, item in enumerate((first, second), 1):
            (directory / f'attempt-{number:02d}-review.json').write_text(json.dumps(item))
        (directory / 'attempt-02-strategy.json').write_text(json.dumps({**edit(1), 'signature': spec['signature']}))
        return spec, directory

    def run_controller(self, spec, prepared_repair=False):
        nodes = importlib.import_module('book_test_pack.nodes')
        repair = importlib.import_module('book_test_pack.repair')
        pose = importlib.import_module('book_test_pack.pose')
        with patch.object(repair, 'try_scale_repair', return_value=prepared_repair), \
             patch.object(pose, 'try_pose_guide', return_value=False) as pose_guide, \
             patch.object(nodes, 'expand_attempt', return_value={}) as expand:
            nodes.BookV2RenderAsset().run(self.project, spec, '')
        return expand.call_args, pose_guide

    def test_native_controller_uses_fresh_conditioning_and_skips_pose_guide(self):
        spec, directory = self.setup_reports()
        call, pose = self.run_controller(spec)
        self.assertEqual(call.args[2], 3)
        self.assertIsNone(call.args[4])
        self.assertEqual(call.args[3], 'Show the required contact.')
        pose.assert_not_called()
        decision = json.loads((directory / 'attempt-03-strategy.json').read_text())
        self.assertEqual(decision['strategy'], 'canonical_redraw')
        self.assertEqual(decision['retry_policy']['edited_source_attempt'], 1)

    def test_recovery_cannot_reintroduce_old_pixels_after_regression(self):
        spec, directory = self.setup_reports(missing_cast=True)
        call, _ = self.run_controller(spec)
        self.assertIsNone(call.args[4])
        decision = json.loads((directory / 'attempt-03-strategy.json').read_text())
        self.assertIsNone(decision['recovered_from_regression'])
        self.assertEqual(decision['retry_policy']['latest_attempt'], 2)

    def test_prepared_size_and_held_prop_repair_takes_priority_over_redraw(self):
        spec, directory = self.setup_reports(measured_scale=True)
        call, _ = self.run_controller(spec, prepared_repair=True)
        self.assertTrue(call.kwargs['scale_repair'])
        decision = json.loads((directory / 'attempt-03-strategy.json').read_text())
        self.assertEqual(decision['strategy'], 'masked_size_repair')
        self.assertEqual(decision['retry_policy']['decision'], 'masked_size_repair')

    def test_old_saved_policy_keeps_its_existing_retry_behavior(self):
        spec, directory = self.setup_reports(version=5)
        call, _ = self.run_controller(spec)
        self.assertEqual(call.args[4], 2)
        self.assertIsNone(json.loads((directory / 'attempt-03-strategy.json').read_text())['retry_policy'])

    def test_stalled_masked_repair_does_not_repeat_the_same_failed_resize(self):
        spec, directory = self.setup_reports(measured_scale=True)
        (directory / 'attempt-02-strategy.json').write_text(json.dumps({
            'strategy': 'masked_size_repair', 'source_attempt': 1, 'signature': spec['signature']}))
        nodes = importlib.import_module('book_test_pack.nodes')
        repair = importlib.import_module('book_test_pack.repair')
        with patch.object(repair, 'try_scale_repair', return_value=True) as resize, \
             patch.object(nodes, 'expand_attempt', return_value={}) as expand:
            nodes.BookV2RenderAsset().run(self.project, spec, '')
        resize.assert_not_called()
        self.assertIsNone(expand.call_args.args[4])
        self.assertFalse(expand.call_args.kwargs['scale_repair'])

    def test_pose_assisted_edit_records_source_and_counts_toward_edit_limit(self):
        spec, directory = self.setup_reports()
        path = directory / 'attempt-01-review.json'
        first = json.loads(path.read_text())
        first['review']['checks']['style_matches'] = False
        path.write_text(json.dumps(first))
        nodes = importlib.import_module('book_test_pack.nodes')
        repair = importlib.import_module('book_test_pack.repair')
        pose = importlib.import_module('book_test_pack.pose')
        with patch.object(repair, 'try_scale_repair', return_value=False), \
             patch.object(pose, 'try_pose_guide', return_value=True), \
             patch.object(nodes, 'expand_attempt', return_value={}) as expand:
            nodes.BookV2RenderAsset().run(self.project, spec, '')
        self.assertTrue(expand.call_args.kwargs['pose_guide'])
        strategy = json.loads((directory / 'attempt-03-strategy.json').read_text())
        self.assertEqual(strategy['strategy'], 'scene_edit')
        self.assertEqual(strategy['source_attempt'], 2)
        self.assertTrue(strategy['pose_guide'])
        second = json.loads((directory / 'attempt-02-review.json').read_text())
        decision = scope.scene_edit_restart([(1, first), (2, second), (3, second)],
                                             {2: edit(1), 3: strategy},
                                             [c['id'] for c in second['review']['characters']])
        self.assertEqual(decision['consecutive_scene_edits'], 2)
        self.assertIn('Two consecutive', decision['reason'])

    def test_turbo_retry_never_uses_known_unsafe_measured_cutout(self):
        spec, directory = self.setup_reports(measured_scale=True)
        self.project['render_settings']['flux_scene_recipe']='turbo8_native'
        nodes=importlib.import_module('book_test_pack.nodes')
        repair=importlib.import_module('book_test_pack.repair')
        with patch.object(repair,'try_scale_repair',side_effect=AssertionError('Unsafe cutout used')), \
             patch.object(nodes,'expand_attempt',return_value={}) as expand:
            nodes.BookV2RenderAsset().run(self.project,spec,'')
        self.assertIsNone(expand.call_args.args[4])
        self.assertFalse(expand.call_args.kwargs['scale_repair'])
        strategy=json.loads((directory/'attempt-03-strategy.json').read_text())
        self.assertEqual(strategy['strategy'],'canonical_redraw')
        self.assertIn('Turbo8',strategy['reason'])


if __name__ == '__main__':
    unittest.main()

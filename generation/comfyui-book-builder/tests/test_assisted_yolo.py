import importlib
import json
import unittest
from unittest.mock import patch

import test_book as fixtures
import test_assisted_creator as helpers
import test_moment_books as moment_fixtures

store = importlib.import_module('book_test_pack.assisted_store')
engine = importlib.import_module('book_test_pack.assisted_engine')
yolo = importlib.import_module('book_test_pack.assisted_yolo')
quality = importlib.import_module('book_test_pack.quality')


def report(checks, ok=True, uncertain=False):
    return {'checks': {c: ok for c in checks}, 'evidence': 'Clear evidence.',
            'issues': [] if ok else ['Something specific is off.'], 'uncertain': uncertain}


class YoloConfigTests(unittest.TestCase):
    setUp = fixtures.BookTests.setUp
    restore_module = fixtures.BookTests.restore_module

    def test_approval_mode_defaults_to_assisted_and_validates(self):
        self.assertEqual(store.config({})['approval_mode'], 'assisted')
        self.assertEqual(store.config({'approval_mode': 'yolo'})['approval_mode'], 'yolo')
        with self.assertRaisesRegex(ValueError, 'assisted.*yolo'):
            store.config({'approval_mode': 'autopilot'})

    def test_decision_source_is_recorded_and_validated(self):
        state = store.create({'page_count': 3})
        intent = store.next_attempt(state)
        path = engine.directory(state['id'], 'story', intent['attempt']) / 'candidate.json'
        fixtures.storage.write_json(path, {'draft': True})
        state = store.record_candidate(state['id'], 'story', intent['attempt'], path, {'content': {}})
        candidate = engine.selected(state, 'story')
        record = store.decision(state, candidate, 'approve', 'Judge notes.', source='yolo')
        self.assertEqual(record['source'], 'yolo')
        saved = json.loads((store.root(state['id']) / 'creator/decisions' / (record['id'] + '.json')).read_text())
        self.assertEqual(saved['source'], 'yolo')
        with self.assertRaisesRegex(ValueError, 'Unknown decision source'):
            store.decision(state, candidate, 'approve', '', source='robot')


class YoloJudgeTests(unittest.TestCase):
    setUp = fixtures.BookTests.setUp
    restore_module = fixtures.BookTests.restore_module
    state = helpers.AssistedCreatorTests.state
    add = helpers.AssistedCreatorTests.add
    approve = helpers.AssistedCreatorTests.approve
    plan = helpers.AssistedCreatorTests.plan
    prepare = helpers.AssistedCreatorTests.prepare
    png = helpers.AssistedCreatorTests.png

    def yolo_state(self, **overrides):
        return store.create({'page_count': 3, 'max_characters': 3, 'seed': 731003,
                             'approval_mode': 'yolo', **overrides})

    def test_enabled_only_for_yolo_books(self):
        self.assertFalse(yolo.enabled(store.create({'page_count': 3})))
        self.assertTrue(yolo.enabled(self.yolo_state()))

    def test_validation_error_short_circuits_the_judge(self):
        state = self.add(self.yolo_state(), {'broken': True},
                         {'content': {'broken': True}, 'validation_error': 'missing pages'})
        with patch.object(quality, 'json_model', side_effect=AssertionError('must not be called')):
            verdict = yolo.judge_session(state['id'])
        self.assertEqual(verdict['action'], 'retry')
        self.assertIn('missing pages', verdict['feedback'])

    def test_story_pass_approves_and_advances_with_yolo_provenance(self):
        value = fixtures.package_fixture()
        for c, h in zip(value['production']['characters'], [100, 50, 65]):
            c['height_cm'] = h
        state = self.add(self.yolo_state(), value)
        with patch.object(quality, 'json_model', return_value=report(yolo.STORY_CHECKS)) as call:
            verdict = yolo.judge_session(state['id'])
        self.assertEqual(list(call.call_args.kwargs['images']), [])
        self.assertEqual(verdict['action'], 'approve')
        with store.LOCK:
            proceed = yolo.apply_verdict(store.read(state['id']), verdict)
        self.assertTrue(proceed)
        state = store.read(state['id'])
        self.assertEqual(store.stage(state, 'story')['status'], 'approved')
        self.assertEqual(state['current_stage'], 'plan')
        decisions = [json.loads(p.read_text())
                     for p in (store.root(state['id']) / 'creator/decisions').glob('*.json')]
        self.assertEqual(decisions[-1]['source'], 'yolo')
        self.assertEqual(decisions[-1]['action'], 'approve')

    def test_failed_judgement_regenerates_with_the_issues_as_feedback(self):
        state = self.state()
        with patch.object(quality, 'json_model', return_value=report(yolo.STORY_CHECKS, ok=False)):
            verdict = yolo.judge_session(state['id'])
        self.assertEqual(verdict['action'], 'retry')
        with store.LOCK:
            proceed = yolo.apply_verdict(store.read(state['id']), verdict)
        self.assertTrue(proceed)
        state = store.read(state['id'])
        self.assertEqual(state['status'], 'queued')
        self.assertEqual(state['job']['attempt'], 2)
        self.assertIn('Something specific is off.', state['job']['feedback'])
        self.assertEqual(store.stage(state, 'story')['auto_retries'], 1)

    def test_retry_budget_exhaustion_parks_for_a_human(self):
        state = self.state()
        stage = store.stage(state, 'story')
        stage['auto_retries'] = yolo.MAX_AUTO_RETRIES
        store.save(state)
        with patch.object(quality, 'json_model', return_value=report(yolo.STORY_CHECKS, ok=False)):
            verdict = yolo.judge_session(state['id'])
        with store.LOCK:
            proceed = yolo.apply_verdict(store.read(state['id']), verdict)
        self.assertFalse(proceed)
        state = store.read(state['id'])
        self.assertEqual(state['status'], 'awaiting_review')
        self.assertTrue(store.stage(state, 'story')['auto_parked'])
        self.assertIn('Something specific is off.', store.stage(state, 'story')['feedback'])

    def test_uncertain_verdict_parks_immediately(self):
        state = self.state()
        with patch.object(quality, 'json_model',
                          return_value=report(yolo.STORY_CHECKS, uncertain=True)):
            verdict = yolo.judge_session(state['id'])
        self.assertEqual(verdict['action'], 'park')
        with store.LOCK:
            proceed = yolo.apply_verdict(store.read(state['id']), verdict)
        self.assertFalse(proceed)
        self.assertEqual(store.read(state['id'])['status'], 'awaiting_review')

    def style_pool(self, takes):
        state = self.prepare()
        for _ in range(takes):
            state = self.png(store.read(state['id']))
        return store.read(state['id'])

    def test_style_judge_picks_the_best_take(self):
        state = self.style_pool(4)
        verdict_report = {'best_image': 2, 'acceptable': True, 'uncertain': False,
                          'evidence': 'Take two is warmest.', 'issues': []}
        with patch.object(quality, 'json_model', return_value=verdict_report) as call:
            verdict = yolo.judge_session(state['id'])
        self.assertEqual(len(call.call_args.kwargs['images']), 4)
        self.assertEqual(verdict['action'], 'approve')
        chosen = store.stage(state, 'style.png')['candidates'][1]
        self.assertEqual(verdict['candidate_id'], chosen['id'])
        with store.LOCK:
            proceed = yolo.apply_verdict(store.read(state['id']), verdict)
        self.assertTrue(proceed)
        state = store.read(state['id'])
        stage = store.stage(state, 'style.png')
        self.assertEqual(stage['status'], 'approved')
        self.assertEqual(stage['selected'], chosen['id'])
        self.assertNotEqual(state['current_stage'], 'style.png')

    def test_style_judge_retries_then_parks_after_two_rounds(self):
        state = self.style_pool(4)
        reject = {'best_image': 1, 'acceptable': False, 'uncertain': False,
                  'evidence': 'All muddy.', 'issues': ['Too dark for a five-year-old.']}
        with patch.object(quality, 'json_model', return_value=reject):
            verdict = yolo.judge_session(state['id'])
        self.assertEqual(verdict['action'], 'retry')
        self.assertIn('Too dark', verdict['feedback'])
        with store.LOCK:
            self.assertTrue(yolo.apply_verdict(store.read(state['id']), verdict))
        for _ in range(4):
            state = self.png(store.read(state['id']))
        with patch.object(quality, 'json_model', return_value=reject):
            verdict = yolo.judge_session(state['id'])
        self.assertEqual(verdict['action'], 'park')
        with store.LOCK:
            self.assertFalse(yolo.apply_verdict(store.read(state['id']), verdict))
        state = store.read(state['id'])
        self.assertEqual(store.stage(state, 'style.png')['status'], 'awaiting_review')

    def test_scene_judge_receives_candidate_and_cast_references(self):
        state = self.prepare()
        while state['current_stage'] != 'cover.png':
            state = self.approve(self.png(store.read(state['id'])))
        state = self.png(state)
        stage = store.stage(state)
        self.assertEqual(stage['kind'], 'scene')
        captured = {}
        def fake(url, model, prompt, schema, **kwargs):
            captured['prompt'] = prompt
            captured.update(kwargs)
            return report(yolo.SCENE_CHECKS)
        with patch.object(quality, 'json_model', side_effect=fake):
            verdict = yolo.judge_session(state['id'])
        self.assertEqual(len(captured['images']), 1 + len(stage['cast_refs']))
        self.assertIn('Illustration brief', captured['prompt'])
        self.assertEqual(verdict['action'], 'approve')

    def test_moment_scene_judge_receives_the_photograph(self):
        case = moment_fixtures.MomentBookTests()
        uploads = [case.stage_upload(), case.stage_upload()]
        state = store.create({**case.submission(uploads), 'approval_mode': 'yolo'})
        state = self.approve(self.add(state, moment_fixtures.moment_manuscript()))
        state = self.approve(self.add(state, case.moment_plan(state)))
        while state['current_stage'] != 'pages/page-001.png':
            state = self.approve(self.png(store.read(state['id'])))
        state = self.png(state)
        stage = store.stage(state)
        photo = store.root(state['id']) / stage['source_photo']['path']
        captured = {}
        def fake(url, model, prompt, schema, **kwargs):
            captured['prompt'] = prompt
            captured.update(kwargs)
            return report(yolo.SCENE_CHECKS)
        with patch.object(quality, 'json_model', side_effect=fake):
            verdict = yolo.judge_session(state['id'])
        self.assertIn(photo.read_bytes(), captured['images'])
        self.assertIn('real photograph', captured['prompt'])
        self.assertEqual(verdict['action'], 'approve')

    def test_reference_judge_receives_style_image(self):
        state = self.prepare()
        state = self.png(state)  # style.png candidate
        state = self.approve(state)
        state = self.png(state)  # first character candidate
        stage = store.stage(state)
        self.assertEqual(stage['kind'], 'character')
        captured = {}
        def fake(url, model, prompt, schema, **kwargs):
            captured.update(kwargs)
            return report(yolo.REFERENCE_CHECKS)
        with patch.object(quality, 'json_model', side_effect=fake):
            verdict = yolo.judge_session(state['id'])
        self.assertEqual(len(captured['images']), 2)
        self.assertEqual(verdict['action'], 'approve')


if __name__ == '__main__':
    unittest.main()

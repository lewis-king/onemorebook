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
        self.assertEqual(store.config({})['style_review_model'], yolo.DEFAULT_STYLE_REVIEW_MODEL)
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

    def test_rejudging_never_overwrites_a_saved_report(self):
        state = self.state()
        with patch.object(quality, 'json_model', return_value=report(yolo.STORY_CHECKS)):
            yolo.judge_session(state['id'])
            yolo.judge_session(state['id'])
        reports = list(engine.directory(state['id'], 'story', 1).glob('judge-report*.json'))
        self.assertEqual(len(reports), 2)

    def test_style_judge_uses_the_ranking_model_and_guards_photos(self):
        state = self.style_pool(4)
        verdict_report = {'best_image': 4, 'acceptable': True, 'uncertain': False,
                          'evidence': 'Take four is empty.', 'issues': []}
        with patch.object(quality, 'json_model', return_value=verdict_report) as call:
            yolo.judge_session(state['id'])
        self.assertEqual(call.call_args.args[1], yolo.DEFAULT_STYLE_REVIEW_MODEL)
        prompt = call.call_args.args[2]
        self.assertIn('photograph of a physical', prompt)
        self.assertIn('check every corner', prompt.lower())

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
        while state['current_stage'] != 'pages/page-001.png':
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
        self.assertIn('judge the design, not the angle', captured['prompt'])
        self.assertIn('not for framing choice alone', captured['prompt'])
        self.assertIn('The planned cast for this page is exactly', captured['prompt'])
        self.assertEqual(verdict['action'], 'approve')

    def test_scene_judge_states_an_empty_cast_for_character_free_pages(self):
        state = self.prepare()
        while state['current_stage'] != 'pages/page-003.png':
            state = self.approve(self.png(store.read(state['id'])))
        state = self.png(state)
        stage = store.stage(state)
        self.assertEqual(stage['cast_refs'], [])
        captured = {}
        def fake(url, model, prompt, schema, **kwargs):
            captured['prompt'] = prompt
            captured.update(kwargs)
            return report(yolo.SCENE_CHECKS)
        with patch.object(quality, 'json_model', side_effect=fake):
            verdict = yolo.judge_session(state['id'])
        self.assertIn('The planned cast for this page is EMPTY', captured['prompt'])
        self.assertEqual(verdict['action'], 'approve')

    def test_cover_judge_checks_title_typography(self):
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
            return report(yolo.COVER_CHECKS)
        with patch.object(quality, 'json_model', side_effect=fake):
            verdict = yolo.judge_session(state['id'])
        self.assertEqual(len(captured['images']), 1 + len(stage['cast_refs']))
        self.assertIn('title_correct', captured['prompt'])
        self.assertIn('pasted', captured['prompt'])
        self.assertEqual(verdict['action'], 'approve')

    def test_cover_prompt_reappends_title_clause_after_rewrite(self):
        state = self.prepare()
        while state['current_stage'] != 'cover.png':
            state = self.approve(self.png(store.read(state['id'])))
        intent = store.next_attempt(state)
        intent.pop('prompt_base', None)  # force the rewrite path
        with patch.object(engine, 'draft_json', return_value={'prompt': 'A hedgehog cover scene.'}):
            prompt, _, _ = engine.image_inputs(state, store.stage(state), intent)
        self.assertIn('hand-lettered display typography', prompt)
        self.assertIn('"The Borrowed Moonlight"', prompt)
        from book_test_pack.story import cover_title_instruction
        clause = cover_title_instruction('The Borrowed Moonlight')
        intent2 = store.next_attempt(store.read(state['id']))
        intent2.pop('prompt_base', None)
        with patch.object(engine, 'draft_json', return_value={'prompt': 'Lovely cover. ' + clause}):
            prompt2, _, _ = engine.image_inputs(store.read(state['id']), store.stage(store.read(state['id'])), intent2)
        self.assertEqual(prompt2.count('hand-lettered display typography'), 1)

    def test_page_prompts_forbid_lettering_after_rewrite(self):
        state = self.prepare()
        while state['current_stage'] != 'pages/page-001.png':
            state = self.approve(self.png(store.read(state['id'])))
        intent = store.next_attempt(state)
        intent.pop('prompt_base', None)
        with patch.object(engine, 'draft_json', return_value={'prompt': 'A busy market scene.'}):
            prompt, _, _ = engine.image_inputs(state, store.stage(state), intent)
        self.assertIn('No readable text', prompt)
        # The cover keeps its title rule instead.
        self.assertNotIn('hand-lettered display typography', prompt)

    def test_character_free_page_forbids_figures_after_rewrite(self):
        state = self.prepare()
        while state['current_stage'] != 'pages/page-003.png':
            state = self.approve(self.png(store.read(state['id'])))
        intent = store.next_attempt(state)
        intent.pop('prompt_base', None)
        with patch.object(engine, 'draft_json', return_value={'prompt': 'The empty garden glows.'}):
            prompt, _, _ = engine.image_inputs(state, store.stage(state), intent)
        self.assertIn('completely unpopulated scene', prompt)
        # A page with a cast does not get the unpopulated clause.
        state2 = self.prepare()
        while state2['current_stage'] != 'pages/page-001.png':
            state2 = self.approve(self.png(store.read(state2['id'])))
        intent2 = store.next_attempt(state2)
        intent2.pop('prompt_base', None)
        with patch.object(engine, 'draft_json', return_value={'prompt': 'Mira finds the light.'}):
            prompt2, _, _ = engine.image_inputs(state2, store.stage(state2), intent2)
        self.assertNotIn('completely unpopulated', prompt2)

    def test_populated_page_closes_the_cast_after_rewrite(self):
        state = self.prepare()
        while state['current_stage'] != 'pages/page-001.png':
            state = self.approve(self.png(store.read(state['id'])))
        intent = store.next_attempt(state)
        intent.pop('prompt_base', None)
        with patch.object(engine, 'draft_json', return_value={'prompt': 'Mira finds the light.'}):
            prompt, _, _ = engine.image_inputs(state, store.stage(state), intent)
        self.assertIn('Every clearly-depicted person and animal', prompt)
        self.assertIn('tiny, distant, anonymous', prompt)
        self.assertNotIn('completely unpopulated', prompt)

    def test_scene_judge_allows_brief_named_supporting_roles(self):
        state = self.prepare()
        while state['current_stage'] != 'pages/page-001.png':
            state = self.approve(self.png(store.read(state['id'])))
        state = self.png(state)
        captured = {}
        def fake(url, model, prompt, schema, **kwargs):
            captured['prompt'] = prompt
            return report(yolo.SCENE_CHECKS)
        with patch.object(quality, 'json_model', side_effect=fake):
            verdict = yolo.judge_session(state['id'])
        self.assertEqual(verdict['action'], 'approve')
        self.assertIn('supporting background role the brief itself names', captured['prompt'])
        self.assertIn('scenery, not characters', captured['prompt'])
        self.assertIn('story_logic', captured['prompt'])

    def test_story_judge_checks_ending_payoff(self):
        state = self.add(self.yolo_state(), fixtures.package_fixture())
        captured = {}
        def fake(url, model, prompt, schema, **kwargs):
            captured['prompt'] = prompt
            return report(yolo.STORY_CHECKS)
        with patch.object(quality, 'json_model', side_effect=fake):
            verdict = yolo.judge_session(state['id'])
        self.assertEqual(verdict['action'], 'approve')
        self.assertIn('ending_payoff', captured['prompt'])
        self.assertIn('flat', captured['prompt'])

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
            captured['prompt'] = prompt
            captured.update(kwargs)
            return report(yolo.REFERENCE_CHECKS)
        with patch.object(quality, 'json_model', side_effect=fake):
            verdict = yolo.judge_session(state['id'])
        self.assertEqual(len(captured['images']), 2)
        self.assertIn('FRAMING rule', captured['prompt'])
        self.assertEqual(verdict['action'], 'approve')


if __name__ == '__main__':
    unittest.main()

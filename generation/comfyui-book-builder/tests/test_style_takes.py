import importlib
import json
import unittest

import test_book as fixtures
import test_assisted_creator as helpers

store = importlib.import_module('book_test_pack.assisted_store')
engine = importlib.import_module('book_test_pack.assisted_engine')


def manuscript():
    value = fixtures.package_fixture()
    for c, h in zip(value['production']['characters'], [100, 50, 65]):
        c['height_cm'] = h
    return value


class StyleTakeTests(unittest.TestCase):
    setUp = fixtures.BookTests.setUp
    restore_module = fixtures.BookTests.restore_module
    state = helpers.AssistedCreatorTests.state
    add = helpers.AssistedCreatorTests.add
    approve = helpers.AssistedCreatorTests.approve
    plan = helpers.AssistedCreatorTests.plan
    prepare = helpers.AssistedCreatorTests.prepare
    png = helpers.AssistedCreatorTests.png

    def test_first_attempt_has_no_take_and_later_takes_are_distinct(self):
        state = self.prepare()  # story + plan approved, current stage style.png
        intent = store.next_attempt(state)
        self.assertIsNone(engine.style_take(state, intent))
        take = engine.style_take(state, {'stage_id': 'pages/page-001.png', 'attempt': 2, 'mode': 'fresh'})
        self.assertIsNone(take)
        seen = []
        for attempt in (2, 3, 4):
            intent = store.next_attempt(store.read(state['id']))
            intent['attempt'] = attempt  # allocate sequentially without generating
            seen.append(engine.style_take(store.read(state['id']), intent))
        self.assertEqual(len(seen), 3)
        self.assertEqual(len(set(seen)), 3, f'style takes must differ: {seen}')
        # Deterministic per book and attempt.
        again = engine.style_take(store.read(state['id']), {'stage_id': 'style.png', 'attempt': 3, 'mode': 'fresh'})
        self.assertEqual(again, seen[1])

    def test_style_prompt_gains_take_after_first_attempt(self):
        state = self.prepare()
        current = store.stage(state)
        intent = store.next_attempt(state)
        prompt, _, _ = engine.image_inputs(state, current, intent)
        self.assertNotIn('Give this picture', prompt)
        takes = set()
        for attempt in (2, 3, 4):
            intent = {'session_id': state['id'], 'stage_id': 'style.png', 'attempt': attempt,
                      'mode': 'fresh', 'feedback': ''}
            take = engine.style_take(state, intent)
            prompt, _, _ = engine.image_inputs(state, current, intent)
            self.assertIn(engine.STYLE_TAKES[take], prompt)
            takes.add(engine.STYLE_TAKES[take])
        self.assertEqual(len(takes), 3)

    def test_continue_style_variations_until_four_candidates(self):
        state = self.prepare()
        self.assertFalse(engine.continue_style_variations(state))  # nothing to review yet
        for _ in range(3):
            state = helpers.AssistedCreatorTests.png(self, store.read(state['id']))
            state = store.read(state['id'])
            self.assertTrue(engine.continue_style_variations(state))
            state = store.read(state['id'])
            self.assertEqual(state['status'], 'queued')
            self.assertEqual(state['job']['stage_id'], 'style.png')
        # The fourth candidate fills the set: no further auto-continuation.
        state = helpers.AssistedCreatorTests.png(self, store.read(state['id']))
        state = store.read(state['id'])
        self.assertEqual(len(store.stage(state, 'style.png')['candidates']), 4)
        self.assertFalse(engine.continue_style_variations(state))
        # A human decision in flight always wins over auto-continuation —
        # except a revision of the style stage itself, which is the take flow.
        deciding = store.read(state['id'])
        deciding['page_revision'] = {'stage_id': 'pages/page-001.png'}
        deciding['status'] = 'awaiting_review'
        deciding['job'] = None
        self.assertFalse(engine.continue_style_variations(deciding))
        fresh = self.prepare()
        fresh = self.png(store.read(fresh['id']))
        fresh = store.read(fresh['id'])
        fresh['page_revision'] = {'stage_id': 'style.png'}
        self.assertTrue(engine.continue_style_variations(fresh))

    def test_art_inspiration_config_validation(self):
        with self.assertRaisesRegex(ValueError, 'under 300'):
            store.config({'art_inspiration': 'x' * 301})
        kept = store.config({'art_inspiration': '  demon hunters  '})
        self.assertEqual(kept['art_inspiration'], 'demon hunters')
        self.assertNotIn('art_inspiration', store.config({}))

    def test_style_prompt_carries_inspiration_on_every_take(self):
        state = store.create({'art_inspiration': 'demon hunters', 'page_count': 3})
        state = self.approve(self.add(state, manuscript()))
        state = self.approve(self.add(state, self.plan(state)))
        current = store.stage(state)
        prompts = []
        for attempt in (1, 2, 3, 4):
            intent = {'session_id': state['id'], 'stage_id': 'style.png', 'attempt': attempt,
                      'mode': 'fresh', 'feedback': ''}
            prompt, _, _ = engine.image_inputs(state, current, intent)
            prompts.append(prompt)
        self.assertIn('Art inspiration from the reader', prompts[0])
        self.assertIn('demon hunters', prompts[0])
        self.assertIn('never scary or dark', prompts[0])
        for prompt in prompts[1:]:
            self.assertIn('demon hunters', prompt)

    def test_style_prompt_without_inspiration_stays_plain(self):
        state = self.prepare()
        current = store.stage(state)
        intent = {'session_id': state['id'], 'stage_id': 'style.png', 'attempt': 2, 'mode': 'fresh', 'feedback': ''}
        prompt, _, _ = engine.image_inputs(state, current, intent)
        self.assertNotIn('Art inspiration', prompt)

    def test_chaining_restarts_when_inspiration_changes(self):
        state = self.prepare()
        for _ in range(4):
            state = self.png(store.read(state['id']))
        state = store.read(state['id'])
        self.assertFalse(engine.continue_style_variations(state))  # four plain takes exist
        state['config']['art_inspiration'] = 'demon hunters'
        store.save(state)
        state = store.read(state['id'])
        self.assertTrue(engine.continue_style_variations(state))  # fresh inspired set allowed

    def test_style_candidate_records_its_inspiration(self):
        import sys
        sys.modules['folder_paths'].get_full_path = lambda category, name: '/tmp/' + name
        state = store.create({'art_inspiration': 'demon hunters', 'page_count': 3})
        state = self.approve(self.add(state, manuscript()))
        state = self.approve(self.add(state, self.plan(state)))
        intent = store.next_attempt(state)
        graph = engine.image_graph(store.read(state['id']), intent)
        save = next(n for n in graph['expand'].values() if n.get('class_type') == 'BookAssistedSaveCandidate')
        info = json.loads(save['inputs']['metadata'])
        self.assertEqual(info['style_inspiration'], 'demon hunters')


if __name__ == '__main__':
    unittest.main()


class StyleInspirationAPITests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.BookTests.setUp
    restore_module = fixtures.BookTests.restore_module
    state = StyleTakeTests.state
    add = StyleTakeTests.add
    approve = StyleTakeTests.approve
    plan = StyleTakeTests.plan
    prepare = StyleTakeTests.prepare
    png = StyleTakeTests.png

    async def test_style_action_saves_art_inspiration(self):
        from unittest.mock import patch
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        api = importlib.import_module('book_test_pack.assisted_web')
        state = self.prepare()
        app = web.Application()
        app.router.add_post('/api/{sid}', api.api)
        async with TestClient(TestServer(app)) as client:
            with patch.object(api, 'launch') as launch:
                response = await client.post('/api/' + state['id'], json={
                    'action': 'regenerate', 'revision': state['revision'],
                    'art_inspiration': 'demon hunters'}, headers={'X-Book-Creator': '1'})
                self.assertEqual(response.status, 200, await response.text())
                shown = await response.json()
                launch.assert_called_once()
        self.assertEqual(shown['config']['art_inspiration'], 'demon hunters')
        saved = store.read(state['id'])
        self.assertEqual(saved['config']['art_inspiration'], 'demon hunters')
        self.assertEqual(saved['current_stage'], 'style.png')

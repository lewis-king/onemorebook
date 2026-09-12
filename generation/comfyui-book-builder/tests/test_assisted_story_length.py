import copy
import importlib
import json
import unittest
from unittest.mock import patch

import test_book as fixtures
import test_assisted_creator as helpers

store = importlib.import_module('book_test_pack.assisted_store')
engine = importlib.import_module('book_test_pack.assisted_engine')
length = importlib.import_module('book_test_pack.assisted_story')
api = importlib.import_module('book_test_pack.assisted_web')


def manuscript(count):
    value = fixtures.package_fixture()
    pages = value['story']['pages']
    value['story']['pages'] = [dict(copy.deepcopy(pages[i % len(pages)]), pageNumber=i+1)
                               for i in range(count)]
    for c, h in zip(value['production']['characters'], [100, 50, 65]):
        c['height_cm'] = h
    return value


class FlexibleStoryTests(unittest.TestCase):
    setUp = fixtures.BookTests.setUp
    restore_module = fixtures.BookTests.restore_module
    add = helpers.AssistedCreatorTests.add
    approve = helpers.AssistedCreatorTests.approve
    plan = helpers.AssistedCreatorTests.plan
    png = helpers.AssistedCreatorTests.png

    def test_empty_form_persists_free_creation_and_bounded_writer_schema(self):
        state = store.create({'story_idea': ''})
        cfg = state['config']
        self.assertEqual(cfg['story_craft_version'], 'picturebook-2')
        self.assertEqual(cfg['age_range'], '4–7')
        self.assertEqual(length.page_bounds(cfg), (8, 16))
        self.assertEqual(cfg['page_count_target'], 14)
        self.assertTrue(set(cfg).isdisjoint({'story_flavour', 'art_preset', 'read_aloud'}))
        intent = store.next_attempt(state)
        with patch.object(engine, 'draft_json', return_value=manuscript(9)) as writer:
            engine.text_step(state, intent)
        spec = writer.call_args.args[-1]['properties']['story']['properties']['pages']
        self.assertEqual((spec['minItems'], spec['maxItems']), (8, 16))
        saved = store.read(state['id'])
        self.assertEqual(saved['status'], 'awaiting_review')
        self.assertFalse((store.root(state['id'])/'creator/decisions').exists())
        self.assertEqual(saved['config'], cfg)

    def test_differently_sized_drafts_keep_own_counts_and_selected_length(self):
        state = store.create({})
        original_config = copy.deepcopy(state['config'])
        for n in (9, 15):
            state = self.add(state, manuscript(n))
        shown = api.public_state(state)
        self.assertEqual([c['metadata']['story_guide']['page_count']
                          for c in shown['stages'][0]['candidates']], [9, 15])
        first = state['stages'][0]['candidates'][0]
        data = store.candidate_path(state, first).read_bytes()
        state = self.approve(state, first)  # test fixture only
        self.assertEqual(state['approved_page_count'], 9)
        self.assertEqual(state['config'], original_config)
        self.assertEqual(store.candidate_path(state, first).read_bytes(), data)
        state = self.approve(self.add(state, self.plan(state)))
        self.assertEqual(len([s for s in state['stages'] if s['id'].startswith('pages/')]), 9)

    def test_invalid_lengths_numbering_and_fields_still_fail(self):
        cfg = store.config({})
        for n in (7, 17):
            with self.subTest(n=n), self.assertRaisesRegex(ValueError, '8–16'):
                length.validate(manuscript(n), cfg)
        for n in (8, 16):
            length.validate(manuscript(n), cfg)
        bad = manuscript(10); bad['story']['pages'][3]['pageNumber'] = 3
        with self.assertRaisesRegex(ValueError, 'pageNumber'): length.validate(bad, cfg)
        bad = manuscript(10); bad['story']['metadata']['newField'] = True
        with self.assertRaises(ValueError): length.validate(bad, cfg)
        fixed = store.config({'page_count': 12})
        with self.assertRaisesRegex(ValueError, '12 pages'): length.validate(manuscript(11), fixed)
        length.validate(manuscript(12), fixed)

    def test_resume_recovers_variable_length_without_writer_or_config_change(self):
        state = self.add(store.create({}), manuscript(11)); cfg = copy.deepcopy(state['config'])
        state['stages'][0].update(candidates=[], selected=None)
        state['status'] = 'generating'; store.save(state)
        with patch.object(engine, 'draft_json', side_effect=AssertionError('Do not regenerate')):
            self.assertTrue(engine.recover_candidate(state, state['job']))
        restored = store.read(state['id'])
        shown = api.public_state(restored)['stages'][0]['candidates'][0]
        self.assertIsNone(shown['metadata']['validation_error'])
        self.assertEqual(shown['metadata']['story_guide']['page_count'], 11)
        self.assertEqual(restored['config'], cfg)

    def test_variable_length_reaches_export_with_original_public_data(self):
        value = manuscript(8)
        state = self.approve(self.add(store.create({}), value))
        state = self.approve(self.add(state, self.plan(state)))
        while state['status'] != 'exporting':
            state = self.approve(self.png(state))
        state = engine.export_session(state)
        target = store.root(state['id'])/'export'
        self.assertEqual(json.loads((target/'story.json').read_text()), value['story'])
        self.assertEqual(len(list((target/'pages').glob('*.png'))), 8)
        self.assertEqual(state['config']['page_count'], 0)
        self.assertEqual(state['approved_page_count'], 8)
        self.assertEqual(state['status'], 'complete')

    def test_legacy_fixed_length_preferences_are_not_reinterpreted(self):
        state = store.create({'page_count': 12, 'story_flavour': 'comedy'})
        before = (store.root(state['id'])/'creator.json').read_bytes()
        restored = store.read(state['id'])
        self.assertEqual(restored['config']['story_craft_version'], 'picturebook-1')
        self.assertEqual(length.page_bounds(restored['config']), (12, 12))
        self.assertEqual((store.root(state['id'])/'creator.json').read_bytes(), before)


class FlexibleStoryAPITests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.BookTests.setUp
    restore_module = fixtures.BookTests.restore_module
    add = helpers.AssistedCreatorTests.add

    async def test_manual_revision_can_change_length_without_approving(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        state = self.add(store.create({}), manuscript(9))
        old = engine.selected(state, 'story'); original = store.candidate_path(state, old).read_bytes()
        app = web.Application(); app.router.add_route('*', '/{sid}', api.api)
        async with TestClient(TestServer(app)) as client, self.assert_no_launch():
            response = await client.post('/'+state['id'], json={
                'action': 'save_draft', 'revision': state['revision'], 'candidate_id': old['id'],
                'feedback': 'Give the ending room.', 'content': manuscript(13)},
                headers={'X-Book-Creator': '1'})
            self.assertEqual(response.status, 200, await response.text())
            shown = await response.json()
        self.assertEqual(shown['status'], 'awaiting_review')
        self.assertEqual(shown['stages'][0]['candidates'][-1]['metadata']['story_guide']['page_count'], 13)
        self.assertEqual(store.candidate_path(state, old).read_bytes(), original)
        self.assertEqual(shown['stages'][1]['candidates'], [])

    def assert_no_launch(self):
        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def context():
            with patch.object(api, 'launch', side_effect=AssertionError('A revision must pause')):
                yield
        return context()

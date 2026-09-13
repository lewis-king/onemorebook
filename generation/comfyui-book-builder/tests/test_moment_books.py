import copy
import hashlib
import importlib
import io
import json
import unittest
import uuid
from unittest.mock import patch

import test_book as fixtures
import test_assisted_creator as helpers

store = importlib.import_module('book_test_pack.assisted_store')
engine = importlib.import_module('book_test_pack.assisted_engine')
planning = importlib.import_module('book_test_pack.assisted_plan')
moment = importlib.import_module('book_test_pack.assisted_moment')
api = importlib.import_module('book_test_pack.assisted_web')

DESCRIPTION = "Esme's fifth birthday at Willow Farm, with the tractor cake and the donkeys."
CAPTION_1 = 'Esme blowing out the five candles on the tractor cake.'
CAPTION_2 = 'Grandpa leads the donkey ride while Esme laughs in the saddle.'


def png_bytes(size=(8, 8), colour=(210, 160, 120)):
    from PIL import Image
    buffer = io.BytesIO()
    Image.new('RGB', size, colour).save(buffer, format='PNG')
    return buffer.getvalue()


def manuscript():
    value = fixtures.package_fixture()
    for c, h in zip(value['production']['characters'], [100, 50, 65]):
        c['height_cm'] = h
    return value


def moment_manuscript():
    """Two pages: the default moment fixtures upload two photographs."""
    value = manuscript()
    value['story']['pages'] = value['story']['pages'][:2]
    return value


class MomentBookTests(unittest.TestCase):
    setUp = fixtures.BookTests.setUp
    restore_module = fixtures.BookTests.restore_module
    add = helpers.AssistedCreatorTests.add
    approve = helpers.AssistedCreatorTests.approve
    plan = helpers.AssistedCreatorTests.plan
    png = helpers.AssistedCreatorTests.png

    def stage_upload(self, data=None):
        upload_id = uuid.uuid4().hex
        target = moment.staged_path(upload_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data if data is not None else png_bytes())
        return upload_id

    def submission(self, uploads, captions=(CAPTION_1, CAPTION_2), description=DESCRIPTION):
        return {'mode': 'moment', 'story_idea': '', 'page_count': 3,
                'moment': {'description': description,
                           'photos': [{'upload_id': u, 'caption': captions[i % len(captions)]}
                                      for i, u in enumerate(uploads)]}}

    def moment_state(self):
        uploads = [self.stage_upload(), self.stage_upload()]
        state = store.create(self.submission(uploads))
        return store.read(state['id'])

    def test_submission_validation(self):
        one = self.stage_upload()
        with self.assertRaisesRegex(ValueError, 'Describe the day'):
            store.config(self.submission([one], description='  '))
        with self.assertRaisesRegex(ValueError, 'one to 14 photographs'):
            store.config({'mode': 'moment', 'moment': {'description': DESCRIPTION, 'photos': []}})
        with self.assertRaisesRegex(ValueError, 'one to 14 photographs'):
            store.config(self.submission([self.stage_upload() for _ in range(15)]))
        with self.assertRaisesRegex(ValueError, 'short caption'):
            store.config(self.submission([one], captions=('',)))
        with self.assertRaisesRegex(ValueError, 'under 500'):
            store.config(self.submission([one], captions=('word ' * 120,)))
        with self.assertRaisesRegex(ValueError, 'twice'):
            store.config(self.submission([one, one]))
        with self.assertRaisesRegex(ValueError, 'missing'):
            store.config(self.submission([uuid.uuid4().hex]))
        with self.assertRaisesRegex(ValueError, 'scratch.*moment|moment.*scratch|Choose'):
            store.config({'mode': 'wombat'})
        with self.assertRaisesRegex(ValueError, 'Photographs only'):
            store.config({'moment': {'description': DESCRIPTION, 'photos': [{'upload_id': one, 'caption': CAPTION_1}]}})
        store.config(self.submission([one]))

    def test_create_intakes_photos_into_session(self):
        first, second = self.stage_upload(), self.stage_upload()
        state = store.create(self.submission([first, second]))
        root = store.root(state['id'])
        # One page per photograph: the story length follows the upload.
        self.assertEqual(state['config']['page_count'], 2)
        photos = state['config']['moment']['photos']
        self.assertEqual([p['id'] for p in photos], ['moment_01', 'moment_02'])
        for photo, caption, original in zip(photos, (CAPTION_1, CAPTION_2), (first, second)):
            self.assertEqual(photo['caption'], caption)
            saved = (root / photo['path']).read_bytes()
            self.assertEqual(photo['sha256'], hashlib.sha256(saved).hexdigest())
            self.assertFalse(moment.staged_path(original).exists())
        self.assertEqual(state['config']['moment']['description'], DESCRIPTION)
        # Uploads are single-use: a second session cannot claim them again.
        with self.assertRaisesRegex(ValueError, 'missing'):
            store.create(self.submission([first]))
        listed = store.listing()
        self.assertTrue(any(item['id'] == state['id'] for item in listed))

    def test_writer_plan_and_restlye_texts(self):
        brief = moment.writer_brief({'description': DESCRIPTION,
                                     'photos': [{'id': 'moment_01', 'caption': CAPTION_1}]})
        self.assertIn(DESCRIPTION, brief)
        self.assertIn(CAPTION_1, brief)
        self.assertIn('moment_01', brief)
        self.assertIn('souvenir', brief)
        restyle = moment.restyle_brief({'caption': CAPTION_1})
        self.assertIn(CAPTION_1, restyle)
        self.assertIn('storybook style', restyle)
        guidance = moment.plan_guidance({'photos': [{'id': 'moment_01', 'caption': CAPTION_1}]})
        self.assertIn('moment_01', guidance)
        self.assertIn('asset_refs', guidance)

    def test_story_prompt_includes_moment_brief(self):
        state = self.moment_state()
        intent = store.next_attempt(state)
        with patch.object(engine, 'draft_json', return_value=moment_manuscript()) as writer:
            engine.text_step(state, intent)
        saved = store.read(state['id'])
        prompt = engine.selected(saved, 'story')['metadata']['prompt']
        self.assertIn(DESCRIPTION, prompt)
        self.assertIn(CAPTION_1, prompt)
        self.assertIn(CAPTION_2, prompt)
        self.assertIn('exactly 2 pages', prompt)
        self.assertEqual(writer.call_args.args[1], 'story')

    def moment_plan(self, state):
        book_plan = self.plan(state)
        book_plan['assets'].append({'id': 'moment_01', 'kind': 'moment', 'name': 'The cake moment',
                                    'appearance': 'Esme blowing out the candles, restyled from the family photograph.',
                                    'source_character': ''})
        book_plan['assets'].append({'id': 'moment_02', 'kind': 'moment', 'name': 'The donkey ride',
                                    'appearance': 'Grandpa leading the donkey while Esme laughs, restyled from the family photograph.',
                                    'source_character': ''})
        book_plan['scenes'][1]['asset_refs'].append('moment_01')
        book_plan['scenes'][2]['asset_refs'].append('moment_02')
        return book_plan

    def test_every_moment_must_illustrate_a_page(self):
        state = self.approve(self.add(self.moment_state(), moment_manuscript()))
        package = engine.package(state)
        moment_ids = [p['id'] for p in state['config']['moment']['photos']]
        full = self.moment_plan(state)
        planning.validate(package, full, moment_ids)
        # Leaving a photograph out now leaves its page empty — one page per photo.
        uncited = copy.deepcopy(full)
        uncited['scenes'][2]['asset_refs'] = ['garden']
        with self.assertRaisesRegex(ValueError, 'no photograph'):
            planning.validate(package, uncited, moment_ids)
        # Scratch books are unaffected.
        scratch = self.approve(self.add(store.create({'page_count': 3}), manuscript()))
        planning.validate(engine.package(scratch), self.plan(scratch))

    def test_pages_follow_photograph_order(self):
        state = self.approve(self.add(self.moment_state(), moment_manuscript()))
        package = engine.package(state)
        moment_ids = [p['id'] for p in state['config']['moment']['photos']]
        # Swapped: the donkey ride (uploaded second) cannot come before the cake.
        swapped = copy.deepcopy(self.moment_plan(state))
        swapped['scenes'][1]['asset_refs'] = ['garden', 'moment_02']
        swapped['scenes'][2]['asset_refs'] = ['garden', 'moment_01']
        with self.assertRaisesRegex(ValueError, 'photograph order'):
            planning.validate(package, swapped, moment_ids)
        # Two moments on one page is not allowed either.
        crowded = copy.deepcopy(self.moment_plan(state))
        crowded['scenes'][1]['asset_refs'] = ['garden', 'moment_01', 'moment_02']
        with self.assertRaisesRegex(ValueError, 'one moment only'):
            planning.validate(package, crowded, moment_ids)
        # The same moment on two pages is not allowed.
        repeated = copy.deepcopy(self.moment_plan(state))
        repeated['scenes'][2]['asset_refs'] = ['moment_01']
        with self.assertRaisesRegex(ValueError, 'two pages'):
            planning.validate(package, repeated, moment_ids)
        # Every numbered page needs its photograph: one page per photo.
        empty = copy.deepcopy(self.moment_plan(state))
        empty['scenes'][2]['asset_refs'] = ['garden']
        with self.assertRaisesRegex(ValueError, 'no photograph'):
            planning.validate(package, empty, moment_ids)
        # The cover is illustrated from the story, not from a photograph.
        cover = copy.deepcopy(self.moment_plan(state))
        cover['scenes'][0]['asset_refs'] = ['moment_01']
        cover['scenes'][1]['asset_refs'] = ['garden', 'moment_02']
        with self.assertRaisesRegex(ValueError, 'cover'):
            planning.validate(package, cover, moment_ids)
        # A later photograph on a later page is fine.
        planning.validate(package, self.moment_plan(state), moment_ids)

    def test_plan_schema_accepts_only_configured_moments(self):
        state = self.approve(self.add(self.moment_state(), moment_manuscript()))
        book_plan = self.moment_plan(state)
        package = engine.package(state)
        moment_ids = [p['id'] for p in state['config']['moment']['photos']]
        planning.validate(package, book_plan, moment_ids)
        with self.assertRaises(Exception):
            planning.validate(package, book_plan, None)
        with self.assertRaises(Exception):
            planning.validate(package, book_plan, ['moment_99'])
        bad = copy.deepcopy(book_plan)
        bad['assets'][-1]['id'] = 'moment_77'
        with self.assertRaises(Exception):
            planning.validate(package, bad, moment_ids)

    def test_plan_request_describes_available_moments(self):
        state = self.moment_state()
        prompt, schema = planning.request(engine.package(self.approve(self.add(state, moment_manuscript()))),
                                          state['config'])
        self.assertIn('MOMENT REFERENCES', prompt)
        self.assertIn(CAPTION_1, prompt)
        kinds = schema['properties']['assets']['items']['properties']['kind']['enum']
        self.assertIn('moment', kinds)
        plain, plain_schema = planning.request(engine.package(self.approve(self.add(store.create({'page_count': 3}), manuscript()))))
        self.assertNotIn('MOMENT REFERENCES', plain)
        self.assertNotIn('moment', plain_schema['properties']['assets']['items']['properties']['kind']['enum'])

    def test_moment_stages_follow_style_and_feed_scenes(self):
        state = self.approve(self.add(self.moment_state(), moment_manuscript()))
        state = self.approve(self.add(state, self.moment_plan(state)))
        ids = [s['id'] for s in state['stages']]
        self.assertEqual(ids[:4], ['story', 'plan', 'style.png', 'moments/moment_01.png'])
        stage = store.stage(state, 'moments/moment_01.png')
        self.assertEqual(stage['kind'], 'moment')
        self.assertEqual(stage['references'], ['style.png'])
        self.assertEqual(stage['source_photo']['caption'], CAPTION_1)
        self.assertEqual(stage['brief'], moment.restyle_brief(stage['source_photo']))
        shown = api.public_state(state)
        shown_stage = next(s for s in shown['stages'] if s['id'] == 'moments/moment_01.png')
        self.assertIn('moment-src/moment_01.png', shown_stage['source_photo_url'])
        cake_scene = next(s for s in state['stages'] if s.get('page') == 1)
        self.assertIn('moments/moment_01.png', cake_scene['references'])
        # The page brief binds the illustration to the real memory by image number.
        self.assertIn('real moment from the reader', cake_scene['brief'])
        self.assertIn('Image 3', cake_scene['brief'])

    def test_image_inputs_put_photograph_first_and_pin_only_approved_refs(self):
        state = self.approve(self.add(self.moment_state(), moment_manuscript()))
        state = self.approve(self.add(state, self.moment_plan(state)))
        state = self.approve(self.png(state))  # style.png
        self.assertEqual(state['current_stage'], 'moments/moment_01.png')
        intent = store.next_attempt(state)
        current = store.stage(state)
        prompt, references, hashes = engine.image_inputs(state, current, intent)
        self.assertEqual(references[0]['path'], 'moment-src/moment_01.png')
        self.assertIn('photograph to restyle', references[0]['label'])
        self.assertIn(CAPTION_1, references[0]['label'])
        self.assertTrue(references[1]['path'].startswith('creator/stages/style.png/'))
        self.assertEqual(set(hashes), {'style.png'})
        self.assertIn('Image 1', prompt)
        self.assertIn('Image 2', prompt)
        self.assertIn('style of Image 2', prompt)
        state = self.approve(self.png(store.read(state['id'])))  # approve the restyle; approval checks only approved references
        self.assertEqual(state['current_stage'], 'moments/moment_02.png')


class MomentUploadAPITests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.BookTests.setUp
    restore_module = fixtures.BookTests.restore_module

    async def post_upload(self, data, headers='default', filename='photo.png'):
        from aiohttp import FormData, web
        from aiohttp.test_utils import TestClient, TestServer
        form = FormData()
        form.add_field('file', data, filename=filename, content_type='image/png')
        app = web.Application()
        app.router.add_route('POST', '/upload', api.upload)
        sent = {'X-Book-Creator': '1'} if headers == 'default' else headers
        async with TestClient(TestServer(app)) as client:
            response = await client.post('/upload', data=form, headers=sent)
            return response.status, await response.text()

    async def test_upload_stages_valid_png(self):
        status, body = await self.post_upload(io.BytesIO(png_bytes()))
        self.assertEqual(status, 200, body)
        result = json.loads(body)
        staged = moment.staged_path(result['upload_id'])
        self.assertTrue(staged.is_file())
        self.assertEqual(result['sha256'], hashlib.sha256(staged.read_bytes()).hexdigest())

    async def test_upload_rejects_bad_header_and_non_image(self):
        status, body = await self.post_upload(io.BytesIO(png_bytes()), headers={})
        self.assertEqual(status, 403)
        status, body = await self.post_upload(io.BytesIO(b'hello world'))
        self.assertEqual(status, 400)
        self.assertIn('readable image', body)

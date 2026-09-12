import copy
import importlib
import json
from unittest.mock import patch

import test_book as fixtures
import test_assisted_creator as assisted_fixtures

craft = importlib.import_module('book_test_pack.story_craft')
store = importlib.import_module('book_test_pack.assisted_store')
engine = importlib.import_module('book_test_pack.assisted_engine')
planner = importlib.import_module('book_test_pack.assisted_plan')
api = importlib.import_module('book_test_pack.assisted_web')


class StoryCraftTests(fixtures.unittest.TestCase):
    setUp = fixtures.BookTests.setUp
    restore_module = fixtures.BookTests.restore_module
    add = assisted_fixtures.AssistedCreatorTests.add

    def test_new_preferences_are_persisted_without_rewriting_old_sessions(self):
        state = store.create({'seed': 73419, 'story_flavour': 'comedy', 'read_aloud': 'prose'})
        self.assertEqual(state['config']['age_range'], '4–7')
        self.assertEqual(state['config']['story_craft_version'], craft.VERSION)
        self.assertEqual(store.read(state['id'])['config'], state['config'])
        old = copy.deepcopy(state)
        for k in ('story_craft_version', 'story_flavour', 'read_aloud', 'art_preset'):
            old['config'].pop(k)
        old['config']['age_range'] = '4–6'
        store.save(old)
        before = (store.root(state['id'])/'creator.json').read_bytes()
        restored = store.read(state['id'])
        self.assertEqual(restored['config'], old['config'])
        self.assertEqual((store.root(state['id'])/'creator.json').read_bytes(), before)
        self.assertNotEqual(fixtures.story.writing_prompt(restored['config']),
                            fixtures.story.writing_prompt(state['config']))
        self.assertIn('British English', fixtures.story.writing_prompt(state['config']))
        self.assertIn('British English', fixtures.story.writing_prompt({**state['config'], 'story_craft_version': 'picturebook-2'}))

    def test_new_craft_requires_specific_payoff_and_varied_distinct_cast(self):
        prompt = fixtures.story.writing_prompt(store.config({'seed': 73420}))
        for phrase in ('specific, visible way', 'pays off something deliberately planted', 'generic thank-you',
                       'Choose names that are easy to say aloud', 'Vary species'):
            self.assertIn(phrase, prompt)

    def test_custom_art_replaces_preset_and_choices_fail_explicitly(self):
        cfg = store.config({'art_preset': 'graphic', 'art_style': '  Blue pencil on cream paper. '})
        self.assertEqual(cfg['art_style'], 'Blue pencil on cream paper.')
        self.assertEqual(store.config({'art_preset': 'paper', 'art_style': '  '})['art_style'], craft.ART['paper'][1])
        for key in ('story_flavour', 'read_aloud', 'art_preset'):
            for value in ('unknown', [], None):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    store.config({key: value})

    def test_story_candidate_preserves_public_contract_and_waits_for_human(self):
        for flavour in craft.FLAVOURS:
            with self.subTest(flavour=flavour):
                state = store.create({'page_count': 3, 'max_characters': 3, 'seed': 420,
                                      'story_flavour': flavour})
                value = fixtures.package_fixture()
                intent = store.next_attempt(state)
                with patch.object(engine, 'draft_json', return_value=copy.deepcopy(value)) as writer:
                    engine.text_step(state, intent)
                schema = writer.call_args.args[-1]
                self.assertEqual(schema, fixtures.story.book_schema(3, 3))
                saved = store.read(state['id'])
                candidate = engine.selected(saved, 'story')
                self.assertEqual(json.loads(store.candidate_path(saved, candidate).read_text()), value)
                self.assertEqual(saved['status'], 'awaiting_review')
                self.assertEqual(saved['stages'][1]['candidates'], [])
                self.assertFalse((store.root(saved['id'])/'creator/decisions').exists())
                guide = json.loads((engine.directory(saved['id'], 'story', intent['attempt'])/'story-guide.json').read_text())
                self.assertEqual(guide['words'], sum(len(p['text'].split()) for p in value['story']['pages']))
                self.assertEqual(guide, candidate['metadata']['story_guide'])
                self.assertNotIn('score', guide)
                fixtures.story.validate_package(value, 3, 3)

    def test_human_revision_guide_is_derived_from_exact_candidate_not_old_counts(self):
        state = store.create({'page_count': 3, 'max_characters': 3, 'seed': 431})
        value = fixtures.package_fixture()
        first = self.add(state, value)
        revision = copy.deepcopy(value)
        revision['story']['pages'][0]['text'] = 'Mira waited.'
        second = self.add(first, revision, {'content': revision, 'method': 'human_text_revision'})
        before = (store.root(state['id'])/'creator.json').read_bytes()
        view = api.public_state(second)
        guides = [c['metadata']['story_guide'] for c in view['stages'][0]['candidates']]
        self.assertEqual(guides[1]['pages'][0]['words'], 2)
        self.assertGreater(guides[0]['words'], guides[1]['words'])
        self.assertEqual((store.root(state['id'])/'creator.json').read_bytes(), before)

    def test_invalid_package_remains_visible_without_false_guide_or_approval(self):
        state = store.create({'page_count': 3, 'max_characters': 3, 'seed': 440})
        value = fixtures.package_fixture()
        value['story']['metadata']['craft'] = 'must not enter the public contract'
        intent = store.next_attempt(state)
        with patch.object(engine, 'draft_json', return_value=value):
            engine.text_step(state, intent)
        result = store.read(state['id'])
        info = engine.selected(result, 'story')['metadata']
        self.assertTrue(info['validation_error'])
        self.assertNotIn('story_guide', info)
        self.assertEqual(result['status'], 'awaiting_review')

    def test_planner_uses_new_guidance_only_for_opted_in_sessions(self):
        package = fixtures.package_fixture()
        before = copy.deepcopy(package)
        legacy, legacy_schema = planner.request(package)
        current, current_schema = planner.request(package, store.config({'seed': 451}))
        self.assertEqual(legacy_schema, current_schema)
        self.assertEqual(package, before)
        self.assertEqual(current.replace(craft.ILLUSTRATION_GUIDANCE, ''), legacy)

    def test_pretend_claim_is_not_rejected_as_a_species_change(self):
        package = fixtures.package_fixture()
        page = package['story']['pages'][1]
        page['text'] = '“I am a mountain,” said Pip. Mira smiled. Fern peered down at the small mouse.'
        page['imagePrompt'] = 'Pip the grey mouse stands proudly while Mira and Fern smile down at him.'
        before = copy.deepcopy(package)
        fixtures.story.validate_package(package, 3, 3)
        self.assertEqual(package, before)
        # Structural validation intentionally makes no literary judgment.
        guide = craft.review_guide(package, store.config({'story_flavour': 'comedy'}))
        self.assertNotIn('approved', guide)

    def test_unknown_saved_prompt_version_is_not_silently_upgraded(self):
        cfg = store.config({'seed': 452})
        cfg['story_craft_version'] = 'future-version'
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            fixtures.story.writing_prompt(cfg)

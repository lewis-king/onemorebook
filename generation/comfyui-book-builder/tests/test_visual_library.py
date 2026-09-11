import copy
import importlib
import unittest

import test_book as fixtures

library = importlib.import_module('book_test_pack.visual_library')
visual_review = importlib.import_module('book_test_pack.visual_review')
actors = importlib.import_module('book_test_pack.actor_labels')
quality = importlib.import_module('book_test_pack.quality')


def entry(identifier='statue', kind='prop'):
    return {'id': identifier, 'kind': kind, 'name': 'Crowned statue' if kind == 'prop' else 'Moonlit garden',
        'appearance': 'Grey stone crowned girl standing on a square base.' if kind == 'prop' else 'Walled garden with a round gate.',
        'source_object_id': 'statue' if kind == 'prop' else '', 'source_character_id': '', 'source_item': '',
        'scenes': ['pages/page-001.png', 'pages/page-002.png'],
        'required_scenes': ['pages/page-001.png'] if kind == 'prop' else [],
        'evidence': 'The same statue/garden is visited twice.'}


class VisualLibraryTests(unittest.TestCase):
    setUp = fixtures.BookTests.setUp
    restore_module = fixtures.BookTests.restore_module

    def library_project(self):
        self.project['scene_contract'] = {'objects': [{'id': 'statue', 'name': 'Statue', 'appearance': 'Grey stone.'}]}
        plan = {'entries': [entry(), entry('garden', 'location')], 'uncertain': False, 'issues': []}
        library.validate(self.project, plan)
        self.project['visual_library'] = {'version': 1, 'plan': plan}
        return self.project

    def test_public_story_and_original_specs_survive_optional_library(self):
        original_story = copy.deepcopy(self.project['story'])
        old_specs = fixtures.story.asset_specs(self.project)
        project = self.library_project()
        # The existing scene-contract methods expect the normal full contract;
        # routing itself consumes only the independent visual-library plan.
        project.pop('scene_contract')
        specs = fixtures.story.asset_specs(project)
        self.assertEqual(project['story'], original_story)
        self.assertEqual([s['name'] for s in specs if s['kind'] in ('prop', 'location')],
                         ['props/statue.png', 'locations/garden.png'])
        scene = next(s for s in specs if s['name'] == 'pages/page-003.png')
        self.assertNotIn('visual_references', scene)  # Ending is not force-fed absent subjects.
        first = next(s for s in specs if s['name'] == 'pages/page-001.png')
        self.assertEqual(first['visual_references'], ['props/statue.png', 'locations/garden.png'])
        for name in ('props/statue.png', 'locations/garden.png'):
            spec = next(s for s in specs if s['name'] == name)
            self.assertEqual(quality.expected_scene(project, spec)[0], [])
        project.pop('visual_library')
        self.assertEqual(fixtures.story.asset_specs(project), old_specs)

    def test_rejects_unsafe_paths_duplicate_designs_and_unrouted_requirements(self):
        project = self.library_project()
        for mutation in ('duplicate_id', 'duplicate_source', 'unrouted_required', 'one_page', 'missing_garment_source'):
            value = copy.deepcopy(project['visual_library']['plan'])
            if mutation == 'duplicate_id': value['entries'].append(entry())
            if mutation == 'duplicate_source': value['entries'].append({**entry(), 'id': 'other_statue'})
            if mutation == 'unrouted_required': value['entries'][0]['required_scenes'].append('pages/page-003.png')
            if mutation == 'one_page': value['entries'][0]['scenes'] = ['pages/page-001.png']
            if mutation == 'missing_garment_source': value['entries'][0]['source_item'] = 'scarf'
            with self.assertRaises(ValueError, msg=mutation): library.validate(project, value)
        for path in ('props/../../story.json', 'locations/Upper.png', 'props/a/b.png'):
            with self.assertRaises(ValueError): fixtures.story.safe_asset_name(path)

    def test_native_graph_receives_prop_and_location_images_with_explicit_roles(self):
        project = self.library_project()
        project.pop('scene_contract')
        project['render_settings'].update(renderer='flux2', **fixtures.render.FLUX_MODELS,
            flux_steps=28, flux_guidance=4, reference_strategy='cast_guide')
        for c, height in zip(project['book']['characters'], [100, 45, 60]): c['height_cm'] = height
        spec = next(s for s in fixtures.story.asset_specs(project) if s['name'] == 'pages/page-002.png')
        graph = fixtures.render.expand_attempt(project, spec, 1)['expand']
        visual = [n for n in graph.values() if n['class_type'] == 'BookV2VisualReferenceSheet']
        self.assertEqual({n['inputs']['kind'] for n in visual}, {'prop', 'location'})
        self.assertEqual(sum(n['class_type'] == 'ReferenceLatent' for n in graph.values()), 3)
        prompt = next(n['inputs']['text'] for n in graph.values() if n['class_type'] == 'CLIPTextEncode')
        self.assertIn('Image 2 is the canonical prop reference', prompt)
        self.assertIn('Image 3 is the canonical location reference', prompt)

    def test_failed_visual_reference_check_cannot_be_masked_by_good_cast(self):
        report = {'checks': dict.fromkeys(quality.VISUAL_CHECKS, True), 'uncertain': False,
                  'issues': [], 'retry_instructions': []}
        check = {'id': 'statue', 'accepted': False, 'review': {'uncertain': False,
                 'issues': ['The crowned standing girl has become a male bust.'],
                 'retry_instructions': ['Restore the same standing girl, crown and square base.']}}
        visual_review.apply_checks(report, [check])
        self.assertFalse(report['checks']['scene_matches'])
        self.assertEqual(len(report['issues']), 1)
        self.assertIn('standing girl', report['retry_instructions'][0])

    def test_separate_inputs_have_exact_roles_and_recorded_input_paths(self):
        import json
        project=self.library_project();project.pop('scene_contract')
        project['render_settings'].update(renderer='flux2', **fixtures.render.FLUX_MODELS,
            flux_steps=28,flux_guidance=4,reference_strategy='cast_guide')
        project['runtime_retry_policy']={'visual_reference_input_policy':1}
        for c,height in zip(project['book']['characters'],[100,45,60]):c['height_cm']=height
        spec=next(s for s in fixtures.story.asset_specs(project) if s['name']=='pages/page-002.png')
        graph=fixtures.render.expand_attempt(project,spec,1)['expand']
        self.assertFalse(any(n['class_type']=='BookV2VisualReferenceSheet' for n in graph.values()))
        loaded={n['inputs']['asset_name'] for n in graph.values() if n['class_type']=='BookV2LoadReference'}
        self.assertEqual(loaded,{'props/statue.png','locations/garden.png'})
        self.assertEqual(sum(n['class_type']=='ReferenceLatent' for n in graph.values()),3)
        info=json.loads(next(n['inputs']['generation_info'] for n in graph.values() if n['class_type']=='BookV2ReviewAsset'))
        self.assertEqual([r['path'] for r in info['reference_images']][1:],['props/statue.png','locations/garden.png'])

    def test_reference_budget_falls_back_to_complete_sheets_instead_of_dropping_a_design(self):
        project=self.library_project();project.pop('scene_contract')
        project['runtime_retry_policy']={'visual_reference_input_policy':1}
        spec=next(s for s in fixtures.story.asset_specs(project) if s['name']=='pages/page-002.png')
        self.assertEqual(len(library.separate_reference_inputs(project,spec,4)),2)
        self.assertEqual(library.separate_reference_inputs(project,spec,5),[])
        self.assertEqual(len(library.entries(project,spec)),2)

    def test_reference_retry_keeps_style_at_second_image_after_candidate(self):
        project = self.library_project()
        project.pop('scene_contract')
        project['render_settings'].update(renderer='flux2', **fixtures.render.FLUX_MODELS,
                                         flux_steps=28, flux_guidance=4)
        spec = next(s for s in fixtures.story.asset_specs(project) if s['name'] == 'props/statue.png')
        for token in ('Image1', 'Image 1', 'IMAGE1', 'Picture1'):
            sample = {**spec, 'prompt': token + ' provides painting style only.'}
            graph = fixtures.render.expand_attempt(project, sample, 2,
                feedback='Soften the painted texture.', correction_attempt=1)['expand']
            prompt = next(n['inputs']['text'] for n in graph.values() if n['class_type'] == 'CLIPTextEncode')
            self.assertIn(token.rstrip('1').strip() + ' 2 provides painting style only.', prompt)
            self.assertNotIn('SAME characters', prompt)
            self.assertIn('Edit image 1, the previous illustration.', prompt)
            images = [n for n in graph.values() if n['class_type'] == 'VAEEncode']
            self.assertEqual([graph[n['inputs']['pixels'][0]]['class_type'] for n in images],
                             ['BookV2LoadCandidate', 'BookV2LoadReference'])

    def test_name_binding_uses_whole_names_once_and_distinguishes_same_species(self):
        cast = [{'id': 'pip', 'name': 'Pip'}, {'id': 'pippa', 'name': 'Pippa'}]
        labels = {'pip': 'the monkey in the blue vest', 'pippa': 'the monkey in the red dress'}
        text = 'Pip pours; Pippa holds it. Pipkin watches. Pip (the monkey in the blue vest) smiles.'
        result = actors.qualify_text(text, cast, labels)
        self.assertIn('Pip (the monkey in the blue vest) pours', result)
        self.assertIn('Pippa (the monkey in the red dress) holds', result)
        self.assertIn('Pipkin watches', result)
        self.assertNotIn(') (', result)

    def test_interchangeable_helper_requires_prose_agnostic_ownership_and_preserved_agency(self):
        issue = 'The other friend is pouring honey onto the shared scarf.'
        audit = {'observed_event': 'Both friends apply honey to their scarf.',
            'required_story_event': 'Prepare the sticky scarf trap together.',
            'story_event_visible': True, 'uncertain': False, 'essential_issues': [],
            'same_story_outcome': True, 'character_agency_preserved': True,
            'explicit_actor_constraint_preserved': True,
            'whole_story_role_evidence': 'This is shared preparation; neither helper owns a promise or unique climactic achievement in this action.',
            'prior_issues': [{'issue_index': 0, 'kind': 'interchangeable_helper', 'required_by': 'illustration_only',
                             'evidence': 'Honey visibly reaches the scarf.', 'story_impact': 'The prepared trap has the same meaning.'}]}
        self.assertTrue(quality.scene_objections_are_optional(audit, [issue]))
        for field in ('same_story_outcome', 'character_agency_preserved', 'explicit_actor_constraint_preserved'):
            bad = copy.deepcopy(audit); bad[field] = False
            self.assertFalse(quality.scene_objections_are_optional(bad, [issue]), field)
        for source in ('prose', 'explicit_user', 'continuity'):
            bad = copy.deepcopy(audit); bad['prior_issues'][0]['required_by'] = source
            self.assertFalse(quality.scene_objections_are_optional(bad, [issue]))
        bad = copy.deepcopy(audit); bad['essential_issues'] = ['Jar has no visible holder.']
        self.assertFalse(quality.scene_objections_are_optional(bad, [issue]))


if __name__ == '__main__':
    unittest.main()

import copy
import importlib
import json
import unittest
from unittest.mock import patch

import test_book as fixtures
from test_visual_library import entry

groups = importlib.import_module('book_test_pack.prop_groups')
geometry = importlib.import_module('book_test_pack.object_geometry')
library = importlib.import_module('book_test_pack.visual_library')


def group():
    return {'id': 'ball_in_orb', 'inner_id': 'ball', 'outer_id': 'orb',
        'inner_detection': 'a red ball', 'outer_detection': 'a clear orb',
        'diameter_ratio': .35, 'source_fact_id': '', 'scenes': ['pages/page-001.png', 'pages/page-002.png'],
        'evidence': 'The ball remains inside the orb until page three.'}


class PropGroupTests(unittest.TestCase):
    setUp = fixtures.BookTests.setUp
    restore_module = fixtures.BookTests.restore_module

    def configured(self):
        self.project['config']['ollama_url'] = 'http://127.0.0.1:11434'
        self.project['book_root'] = str(self.output/'books/test')
        entries = [{**entry(i), 'name': name, 'appearance': appearance,
                    'source_object_id': '', 'scenes': ['pages/page-001.png', 'pages/page-002.png']}
                   for i, name, appearance in [('ball', 'Red ball', 'Round red rubber ball.'),
                       ('orb', 'Clear orb', 'Transparent round orb.'),
                       ('statue', 'Stone statue', 'Crowned stone figure.')]]
        self.project['visual_library'] = {'version': 3,
            'plan': {'entries': entries, 'uncertain': False, 'issues': []}}
        self.project['prop_groups'] = {'version': 1,
            'plan': {'groups': [group()], 'uncertain': False, 'issues': []}}
        return self.project

    def test_public_contract_unchanged_and_groups_after_source_references(self):
        original = copy.deepcopy(self.project['story'])
        project = self.configured()
        specs = fixtures.story.asset_specs(project)
        names = [s['name'] for s in specs]
        self.assertLess(names.index('props/orb.png'), names.index('prop_groups/ball_in_orb.png'))
        self.assertLess(names.index('prop_groups/ball_in_orb.png'), names.index('pages/page-001.png'))
        self.assertEqual(project['story'], original)
        for path in ('prop_groups/../story.json', 'prop_groups/foo/bar.png', 'prop_groups/Upper.png'):
            with self.assertRaises(ValueError): fixtures.story.safe_asset_name(path)

    def test_routing_replaces_members_once_and_does_not_route_popped_container(self):
        project = self.configured()
        spec = {'name': 'pages/page-001.png'}
        panels = groups.sheet_entries(project, spec, library.entries(project, spec))
        self.assertEqual([p['asset_name'] for p in panels], ['prop_groups/ball_in_orb.png', 'props/statue.png'])
        self.assertEqual(groups.groups(project, {'name': 'pages/page-003.png'}), [])
        project['visual_library']['plan']['entries'][1]['scenes'] = ['pages/page-002.png']
        self.assertEqual(groups.groups(project, spec), [])

    def test_unsafe_duplicate_and_single_page_plans_rejected(self):
        project = self.configured()
        groups.validate(project, project['prop_groups']['plan'])
        for mutation in ('same_subject', 'overlap', 'one_page', 'unsafe', 'inverted_ratio'):
            plan = copy.deepcopy(project['prop_groups']['plan'])
            g = plan['groups'][0]
            if mutation == 'same_subject': g['outer_id'] = g['inner_id']
            if mutation == 'overlap': plan['groups'].append({**g, 'id': 'another'})
            if mutation == 'one_page': g['scenes'] = ['cover.png', 'pages/page-001.png']
            if mutation == 'unsafe': g['id'] = '../x'
            if mutation == 'inverted_ratio': g['diameter_ratio'] = 1.5
            with self.assertRaises((ValueError, __import__('jsonschema').ValidationError)):
                groups.validate(project, plan)

    def test_native_group_first_and_retry_reference_roles_and_exact_seed(self):
        project = self.configured()
        project['render_settings'].update(renderer='flux2', **fixtures.render.FLUX_MODELS,
            flux_steps=28, flux_guidance=4)
        spec = next(s for s in fixtures.story.asset_specs(project) if s['kind'] == 'prop_group')
        for attempt in (1, 2):
            graph = fixtures.render.expand_attempt(project, spec, attempt, 'Keep the inner object small.',
                correction_attempt=None if attempt == 1 else 1)['expand']
            prompt = next(n['inputs']['text'] for n in graph.values() if n['class_type'] == 'CLIPTextEncode')
            self.assertIn(f'Image {attempt} supplies ONLY Red ball', prompt)
            self.assertIn(f'Image {attempt+1} supplies ONLY Clear orb', prompt)
            self.assertEqual(sum(n['class_type'] == 'ReferenceLatent' for n in graph.values()), attempt+1)
            noise = next(n['inputs']['noise_seed'] for n in graph.values() if n['class_type'] == 'RandomNoise')
            expected = spec['seed'] if attempt == 1 else fixtures.story.asset_seed(spec['seed'], 'retry-2')
            self.assertEqual(noise, expected)

    def test_scene_receives_grouped_panels_and_scale_instruction(self):
        project = self.configured()
        spec = {'name': 'pages/page-001.png'}
        text = library.reference_instruction(project, spec, 'prop', 2)
        self.assertIn('panel 1: a red ball inside a clear orb', text)
        self.assertIn('35%', text)
        self.assertIn('panel 2: Stone statue', text)
        self.assertNotIn('panel 3', text)

    def test_measurement_rejects_false_presence_duplicate_boxes_and_occlusion(self):
        boxes = [{'bbox': [35,35,65,65]}, {'bbox': [0,0,100,100]}]
        audit = {'subjects': [{'id': cid, 'present': True, 'box_index': i, 'box_tight': True,
            'outline_complete': True, 'deformed': False, 'evidence': 'Full spherical outline.'}
            for i,cid in enumerate(('inner','outer'))], 'uncertain': False, 'contained': True,
            'shared_depth': True, 'evidence': 'One inside the other.'}
        self.assertAlmostEqual(geometry.measured_ratio(boxes, audit, (100,100)), .3)
        for key in ('present', 'box_tight', 'outline_complete'):
            bad = copy.deepcopy(audit); bad['subjects'][0][key] = False
            self.assertIsNone(geometry.measured_ratio(boxes, bad, (100,100)))
        for key in ('deformed',):
            bad = copy.deepcopy(audit); bad['subjects'][0][key] = True
            self.assertIsNone(geometry.measured_ratio(boxes, bad, (100,100)))
        bad = copy.deepcopy(audit); bad['subjects'][1]['box_index'] = 0
        self.assertIsNone(geometry.measured_ratio(boxes, bad, (100,100)))
        bad = copy.deepcopy(audit); bad['subjects'][1]['box_index'] = 22
        self.assertIsNone(geometry.measured_ratio(boxes, bad, (100,100)))

    def test_real_calibration_ratios_allow_small_variation_and_reject_clear_growth(self):
        for ratio in (.3536221109, .3835205795, .3449209217, .3434646504):
            self.assertTrue(geometry.verdict(ratio, .3536221109)['accepted'])
        for ratio in (.6061994234, .6245679324):
            self.assertFalse(geometry.verdict(ratio, .3536221109)['accepted'])
        self.assertIsNone(geometry.verdict(None, .35)['accepted'])

    def test_unmeasurable_scene_is_no_numeric_claim_but_canonical_group_must_measure(self):
        p = self.configured()
        result = {'ratio': None, 'audit': {'evidence': 'Cropped boundary.'}}
        with patch.object(geometry, 'measure', return_value=result):
            scene = groups.check(p, group(), b'x', None)
            ref = groups.check(p, group(), b'x', None, reference=True)
        self.assertTrue(scene['accepted'])
        self.assertEqual(scene['decision']['status'], 'unmeasurable')
        self.assertFalse(ref['accepted'])
        self.assertTrue(ref['review']['uncertain'])

    def test_size_failure_cannot_clear_existing_scene_failures(self):
        visual = importlib.import_module('book_test_pack.visual_review')
        report = {'checks': {'scene_matches': False, 'anatomy_sound': False}, 'uncertain': False,
            'issues': ['Extra limb'], 'retry_instructions': []}
        with patch.object(geometry, 'measure', return_value={'ratio': .62, 'audit': {'evidence': 'Complete outlines.'}}):
            result = groups.check(self.configured(), group(), b'x', None)
        visual.apply_checks(report, [result])
        self.assertFalse(report['checks']['anatomy_sound'])
        self.assertIn('Extra limb', report['issues'])
        self.assertEqual(len(report['issues']), 2)

    def test_conditional_fact_routes_unnamed_middle_pages(self):
        project = self.configured()
        project['scene_contract'] = {'objects': [{'id': i} for i in ('ball', 'orb')],
            'persistent_facts': [{'id': 'inside', 'object_ids': ['ball', 'orb'],
                'visibility': 'conditional', 'from_page': 1, 'through_page': 3,
                'requirement': 'If orb visible, ball inside.'}]}
        for e in project['visual_library']['plan']['entries']:
            if e['id'] in ('ball', 'orb'):
                e['source_object_id'] = e['id']
                e['scenes'].append('pages/page-003.png')
        plan = {'groups': [{**group(), 'source_fact_id': 'inside',
            'scenes': ['pages/page-001.png', 'pages/page-003.png']}], 'uncertain': False, 'issues': []}
        review = dict.fromkeys(('faithful', 'complete', 'routing_correct', 'sizes_plausible'), True)
        review.update(uncertain=False, issues=[])
        from unittest.mock import Mock
        generate = Mock(side_effect=[plan, review])
        with patch.object(groups, 'previous_baseline', return_value=None):
            result = groups.compile_groups(project, 'local', generate)
        self.assertIn('pages/page-002.png', result['plan']['groups'][0]['scenes'])
        self.assertEqual(generate.call_count, 2)
        # Shutdown recovery reads the exact checked plan without model calls.
        self.assertEqual(groups.compile_groups(project, 'local', generate), result)
        self.assertEqual(generate.call_count, 2)

    def test_baseline_uses_prepared_project_and_hash_checked_approved_pixels(self):
        from pathlib import Path
        from unittest.mock import Mock
        project = self.configured()
        old = copy.deepcopy(project)
        old['render_root'] = str(Path(project['book_root'])/'renders'/'old')
        root = Path(old['render_root']); root.mkdir(parents=True)
        (root/'project.json').write_text(json.dumps(old))
        prepared = {**old, 'state_edits': {'marker': True}}
        (root/'prepared-state-project.json').write_text(json.dumps(prepared))
        path = root/'pages/page-001.png'; path.parent.mkdir(); path.write_bytes(b'approved pixels')
        spec = {'name': 'pages/page-001.png'}
        def valid(actual, candidate):
            self.assertEqual(actual['state_edits'], {'marker': True})
            return True
        value = {'ratio': .35, 'source_hash': 'verified', 'evidence_dir': 'local-proof'}
        with patch.object(fixtures.story, 'asset_specs', return_value=[spec]), \
                patch.object(fixtures.storage, 'valid_asset', side_effect=valid), \
                patch.object(geometry, 'measure', return_value=value):
            result = groups.previous_baseline(project, group(), 'local', Mock())
        self.assertEqual(result['ratio'], .35)
        self.assertEqual(result['source_hash'], 'verified')

    def test_reusing_prop_review_with_no_cast_inventory_does_not_crash(self):
        ranking = importlib.import_module('book_test_pack.candidate_ranking')
        report = {'inventory': None, 'scale_review': None, 'geometry': None,
            'review': {'characters': [], 'unexpected_character_count': 0,
                       'checks': {'scene_matches': True}, 'issues': []}}
        self.assertEqual(ranking.cast_penalty(report, []), 0)
        self.assertLess(ranking.rank_candidate(report, [], approved=True),
                        ranking.rank_candidate(report, [], approved=False))
        bad = copy.deepcopy(report)
        bad['review']['unexpected_character_count'] = 1
        bad['review']['issues'] = ['Living monkey instead of a statue.']
        self.assertGreater(ranking.rank_candidate(bad, []), ranking.rank_candidate(report, []))

    def test_spherical_assembly_preserves_container_pixels_and_places_requested_scale(self):
        from PIL import Image, ImageDraw, ImageChops
        source = Image.new('RGB', (100,100), '#ffffcc')
        ImageDraw.Draw(source).ellipse((20,20,80,80), fill='red')
        outer = Image.new('RGB', (100,100), '#fffafa')
        ImageDraw.Draw(outer).ellipse((10,10,90,90), outline='blue', width=2)
        result, proof = groups.compose_spheres(source, outer, [20,20,80,80], [10,10,90,90], .35)
        self.assertEqual(proof['placed_size'], [28,28])
        self.assertEqual(proof['placed_at'], [36,36])
        self.assertEqual(result.getpixel((50,50)), (255,0,0))
        self.assertEqual(ImageChops.difference(result, outer).getbbox(), (36,36,64,64))
        with self.assertRaises(ValueError):
            groups.compose_spheres(source, outer, [20,20,80,30], [10,10,90,90], .35)

    def test_native_assembly_still_requires_full_review_and_can_fallback(self):
        project = self.configured()
        project['render_settings'].update(renderer='flux2', **fixtures.render.FLUX_MODELS,
            flux_steps=28, flux_guidance=4, prop_group_composition=1)
        spec = next(s for s in fixtures.story.asset_specs(project) if s['kind']=='prop_group')
        with patch.object(groups, 'assemble_reference', return_value={'path':'prepared.png'}):
            graph = fixtures.render.expand_attempt(project, spec, 1)['expand']
        classes = [n['class_type'] for n in graph.values()]
        self.assertEqual(classes, ['BookV2LoadGroupAssembly','BookV2ReviewAsset'])
        self.assertNotIn('BookV2SaveAsset', classes)
        with patch.object(groups, 'assemble_reference', return_value=None):
            fallback = fixtures.render.expand_attempt(project, spec, 1)['expand']
        self.assertIn('SamplerCustomAdvanced', [n['class_type'] for n in fallback.values()])
        self.assertIn('BookV2ReviewAsset', [n['class_type'] for n in fallback.values()])

    def test_reference_repairs_do_not_instruct_preserving_nonexistent_cast(self):
        project = self.configured()
        project['render_settings'].update(renderer='flux2', **fixtures.render.FLUX_MODELS,
            flux_steps=28, flux_guidance=4)
        spec = next(s for s in fixtures.story.asset_specs(project) if s['kind']=='prop_group')
        with patch.object(geometry, 'measure', return_value={'ratio': .56, 'audit': {'evidence': 'Full outlines.'}}):
            result = groups.check(project, group(), b'x', None, reference=True)
        feedback = ' '.join(result['review']['retry_instructions'])
        self.assertNotIn('character', feedback)
        self.assertNotIn('scene action', feedback)
        graph = fixtures.render.expand_attempt(project, spec, 2, feedback, correction_attempt=1)['expand']
        prompt = next(n['inputs']['text'] for n in graph.values() if n['class_type']=='CLIPTextEncode')
        self.assertNotIn('identities, outfits', prompt)
        self.assertIn('Preserve its object designs', prompt)

    def test_clean_canonical_group_must_meet_design_band_before_scene_uncertainty(self):
        with patch.object(geometry, 'measure', return_value={'ratio': .445, 'audit': {'evidence':'Full outlines.'}}):
            reference = groups.check(self.configured(), group(), b'x', None, reference=True)
        self.assertFalse(reference['accepted'])


if __name__ == '__main__': unittest.main()

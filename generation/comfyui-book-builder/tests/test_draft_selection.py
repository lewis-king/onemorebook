"""Draft selection keeps rejected images visible without publishing them."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from test_book import fixture, package_fixture, story
import importlib
selection = importlib.import_module('book_test_pack.draft_selection')

class DraftSelectionTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        output = Path(self.tmp.name)
        fake = types.ModuleType('folder_paths')
        fake.get_output_directory = lambda: str(output)
        env = patch.dict(sys.modules, folder_paths=fake)
        env.start()
        self.addCleanup(env.stop)
        self.path = output/'books/example/renders/test'
        self.project = {'book': fixture(), **package_fixture(),
                        'config': {'seed': 100, 'art_style': story.DEFAULT_STYLE, 'ollama_url': 'http://127.0.0.1:11434'},
                        'render_root': str(self.path), 'render_settings': {'review_model': 'gemma4:31b'}}
        self.spec = next(s for s in story.asset_specs(self.project) if s['name'] == 'cover.png')
        directory = self.path/'quality/cover'
        directory.mkdir(parents=True)
        for attempt, color in [(1, 'red'), (2, 'green')]:
            path = directory/f'attempt-{attempt:02d}.png'
            Image.new('RGB', (16, 16), color).save(path)
            path.with_name(path.stem+'-render.json').write_text(json.dumps({'signature': self.spec['signature']}))
            path.with_name(path.stem+'-review.json').write_text(json.dumps({'signature': self.spec['signature'],
                'png_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'accepted': False,
                'review': {'issues': ['Wrong sleeve' if attempt == 1 else 'Missing main character']}}))
        self.calls = 0
        self.audit_calls = 0
        def audit(project, spec, png, **kwargs):
            self.audit_calls += 1
            number = kwargs['attempt']
            return {'accepted': False, 'review': {'issues': ['Wrong sleeve' if number == 1 else 'Missing main character']}}
        context = patch('book_test_pack.quality.review_art', side_effect=audit)
        context.start()
        self.addCleanup(context.stop)

    def reviewer(self, *args, **kwargs):
        self.calls += 1
        self.assertEqual(args[1], 'gemma4:31b')
        self.assertNotIn('images', kwargs)
        self.assertIn('Current independently recorded candidate assessments', args[2])
        return {'ranking': [1, 2], 'uncertain': False, 'reason': 'Attempt 1 preserves all actors despite a sleeve defect.',
                'observations': [{'attempt': n, 'cast_identity': 'all present' if n == 1 else 'main missing',
                                  'story_action': 'visible', 'appearance_and_scale': 'sleeve issue',
                                  'anatomy_and_style': 'coherent', 'remaining_problems': ['sleeve' if n == 1 else 'cast']} for n in [1, 2]]}

    def test_selects_earlier_candidate_resumes_and_does_not_publish(self):
        originals = {p: p.read_bytes() for p in (self.path/'quality/cover').iterdir()}
        result = selection.select_review_candidate(self.project, self.spec, self.reviewer)
        self.assertEqual(result['selected_attempt'], 1)
        self.assertEqual(selection.selected_draft_candidate(self.project, self.spec)['attempt'], 1)
        self.assertEqual(result['status'], 'unapproved_draft_selection')
        self.assertFalse((self.path/'cover.png').exists())
        self.assertEqual(selection.select_review_candidate(self.project, self.spec, self.reviewer), result)
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.audit_calls, 2)
        from book_test_pack.preview import write_review_draft
        html = write_review_draft(self.project).read_text()
        self.assertIn('Best failed candidate — attempt 1 (unapproved)', html)
        manifest = json.loads((self.path/'draft-manifest.json').read_text())
        self.assertEqual(manifest['assets']['cover.png']['selected'], 'quality/cover/attempt-01.png')
        self.assertFalse(manifest['assets']['cover.png']['approved'])
        for path, data in originals.items():
            self.assertEqual(path.read_bytes(), data)

    def test_changed_pixels_require_new_selection_preserving_previous_record(self):
        from PIL import Image
        selection.select_review_candidate(self.project, self.spec, self.reviewer)
        Image.new('RGB', (16, 16), 'blue').save(self.path/'quality/cover/attempt-02.png')
        self.assertIsNone(selection.selected_draft_candidate(self.project, self.spec))
        selection.select_review_candidate(self.project, self.spec, self.reviewer)
        self.assertEqual(self.calls, 2)
        self.assertEqual(len(list((self.path/'quality/cover/draft-selections').glob('*.json'))), 2)

    def test_native_concise_reviews_are_reused_without_legacy_pixel_review(self):
        from book_test_pack import quality_preview
        self.project['render_settings']['scene_quality_policy'] = 'concise_v1'
        directory = self.path/'quality/cover'
        for path in directory.glob('attempt-*-review.json'):
            record = json.loads(path.read_text())
            record['qa_version'] = quality_preview.QA_VERSION
            path.write_text(json.dumps(record))
        with patch.object(quality_preview, 'review_art', side_effect=AssertionError('Unexpected duplicate pixel review')):
            result = selection.select_review_candidate(self.project, self.spec, self.reviewer)
        self.assertEqual(result['inputs']['review_policy'], quality_preview.QA_VERSION)
        self.assertEqual(self.audit_calls, 0)
        self.assertEqual(self.calls, 1)
        self.assertEqual(result['selected_attempt'], 1)
        self.assertFalse((self.path/'cover.png').exists())

    def test_stale_concise_review_uses_selected_policy_not_legacy_policy(self):
        from book_test_pack import quality_preview
        self.project['render_settings']['scene_quality_policy'] = 'concise_v1'
        audit = {'accepted': False, 'review': {'issues': ['Current policy issue']}}
        with patch.object(quality_preview, 'review_art', return_value=audit) as current:
            selection.select_review_candidate(self.project, self.spec, self.reviewer)
        self.assertEqual(current.call_count, 2)
        self.assertEqual(self.audit_calls, 0)

    def test_missing_or_duplicate_candidates_cannot_be_selected(self):
        for ranking in ([1, 1], [1], [1, 3]):
            result = self.reviewer(None, 'gemma4:31b', 'Current independently recorded candidate assessments')
            result['ranking'] = ranking
            with self.assertRaises(ValueError):
                selection.validate_comparison(result, [1, 2])


if __name__ == '__main__':
    unittest.main()

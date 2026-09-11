import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from test_book import fixture, package_fixture, story

preview = importlib.import_module('book_test_pack.preview')
export = importlib.import_module('book_test_pack.export')


class ReviewDraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        output = Path(self.tmp.name)
        fake = types.ModuleType('folder_paths')
        fake.get_output_directory = lambda: str(output)
        context = patch.dict(sys.modules, folder_paths=fake)
        context.start()
        self.addCleanup(context.stop)
        self.root = output/'books/example/renders/test'
        self.project = {'book': fixture(), **package_fixture(),
                        'config': {'seed': 100, 'art_style': story.DEFAULT_STYLE},
                        'render_root': str(self.root), 'render_settings': {}}

    def candidate(self, number, color):
        from PIL import Image
        spec = next(s for s in story.asset_specs(self.project) if s['name'] == 'cover.png')
        directory = self.root/'quality/cover'
        directory.mkdir(parents=True, exist_ok=True)
        path = directory/f'attempt-{number:02d}.png'
        Image.new('RGB', (16, 16), color).save(path)
        report = {'signature': spec['signature'], 'png_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'accepted': False, 'review': {'issues': ['Two copies of the main character']}}
        path.with_name(path.stem+'-review.json').write_text(json.dumps(report))
        return path

    def test_rejected_book_exposes_all_attempts_without_approving_or_changing_them(self):
        first = self.candidate(1, 'blue')
        second = self.candidate(2, 'green')
        originals = {p: p.read_bytes() for p in (self.root/'quality').rglob('*') if p.is_file()}
        page = preview.write_review_draft(self.project).read_text()
        manifest = json.loads((self.root/'draft-manifest.json').read_text())
        cover = manifest['assets']['cover.png']
        self.assertFalse(cover['approved'])
        self.assertEqual(cover['selected'], second.relative_to(self.root).as_posix())
        self.assertIn(first.relative_to(self.root).as_posix(), page)
        self.assertIn('Two copies of the main character', page)
        self.assertIn('Illustration not generated yet', page)
        self.assertFalse((self.root/'cover.png').exists())
        self.assertFalse((self.root/'manifest.json').exists())
        for path, data in originals.items():
            self.assertEqual(path.read_bytes(), data)

    def test_stale_review_is_not_attributed_to_changed_image(self):
        from PIL import Image
        path = self.candidate(1, 'blue')
        Image.new('RGB', (16, 16), 'red').save(path)
        preview.write_review_draft(self.project)
        manifest = json.loads((self.root/'draft-manifest.json').read_text())
        attempt = manifest['assets']['cover.png']['attempts'][0]
        self.assertEqual(attempt['status'], 'awaiting review')
        self.assertEqual(attempt['review'], {})

    def test_export_failure_still_saves_readable_draft_and_keeps_gate(self):
        self.candidate(1, 'blue')
        with self.assertRaisesRegex(ValueError, 'Book is incomplete.*review-draft.html'):
            export.export_book(self.project, False)
        self.assertTrue((self.root/'review-draft.html').exists())
        self.assertFalse((self.root/'book.html').exists())
        self.assertFalse((self.root/'manifest.json').exists())

    def test_exact_sampler_prompt_is_visible_escaped_and_keeps_large_seed(self):
        import html
        path = self.candidate(1, 'blue')
        report_path = path.with_name(path.stem+'-review.json')
        report = json.loads(report_path.read_text())
        actual = 'A specific edited scene.\nKeep <script>alert(1)</script> as literal prompt data.'
        report.update(prompt=actual, seed=914235837607224496)
        report_path.write_text(json.dumps(report))
        page = preview.write_review_draft(self.project).read_text()
        self.assertIn(html.escape(actual, quote=True), page)
        self.assertNotIn('<script>alert(1)</script>', page)
        self.assertIn('914235837607224496', page)
        self.assertIn('Copy full prompt', page)
        saved = json.loads((self.root/'draft-manifest.json').read_text())
        self.assertEqual(saved['assets']['cover.png']['attempts'][0]['generation']['prompt'], actual)

    def test_stale_image_does_not_inherit_other_images_exact_prompt(self):
        from PIL import Image
        path = self.candidate(1, 'blue')
        report_path = path.with_name(path.stem+'-review.json')
        report = json.loads(report_path.read_text())
        report.update(prompt='STALE ACTUAL PROMPT', seed=42)
        report_path.write_text(json.dumps(report))
        Image.new('RGB', (16,16), 'red').save(path)
        page = preview.write_review_draft(self.project).read_text()
        self.assertNotIn('STALE ACTUAL PROMPT', page)

    def test_published_asset_shows_its_approved_attempt_prompt(self):
        path = self.candidate(1, 'blue')
        report_path = path.with_name(path.stem+'-review.json')
        report = json.loads(report_path.read_text())
        report.update(prompt='APPROVED ACTUAL SAMPLER PROMPT', seed=42, accepted=True)
        report_path.write_text(json.dumps(report))
        with patch.object(preview, 'valid_asset', side_effect=lambda project,spec: spec['name']=='cover.png'):
            page = preview.write_review_draft(self.project).read_text()
        self.assertIn('APPROVED ACTUAL SAMPLER PROMPT', page)
        self.assertEqual(page.count('<pre>APPROVED ACTUAL SAMPLER PROMPT</pre>'), 2)

    def test_actual_graph_recipe_wins_over_project_defaults(self):
        self.project['render_settings']['flux_scene_recipe']='turbo8_native'
        path = self.candidate(1, 'blue')
        report_path = path.with_name(path.stem+'-review.json')
        report = json.loads(report_path.read_text())
        report.update(prompt='Edit the existing illustration.', seed=42)
        report_path.write_text(json.dumps(report))
        rendered = {'signature':report['signature'], 'generation_info': {
            'method':'image_edit', 'model':'flux2_dev_fp8mixed.safetensors',
            'steps':28, 'loras':[], 'provenance':'recorded from executed graph'}}
        path.with_name(path.stem+'-render.json').write_text(json.dumps(rendered))
        page = preview.write_review_draft(self.project).read_text()
        self.assertIn('Image edit of an existing illustration',page)
        self.assertIn('steps: 28',page)
        self.assertNotIn('FLUX.2 dev Turbo 8',page)

    def test_unknown_strategy_is_not_mislabelled_as_text_to_image(self):
        path = self.candidate(1, 'blue')
        report_path = path.with_name(path.stem+'-review.json')
        report = json.loads(report_path.read_text());report.update(prompt='Historical prompt.', seed=42)
        report_path.write_text(json.dumps(report))
        page = preview.write_review_draft(self.project).read_text()
        self.assertIn('Generation method not recorded',page)

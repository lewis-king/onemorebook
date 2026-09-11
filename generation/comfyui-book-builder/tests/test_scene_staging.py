import copy, importlib, json, unittest
from unittest.mock import patch
import test_book as fixtures
from test_quality import visual_report

staging=importlib.import_module('book_test_pack.scene_staging')
quality=importlib.import_module('book_test_pack.quality')
nodes=importlib.import_module('book_test_pack.nodes')
preview=importlib.import_module('book_test_pack.preview')
selection=importlib.import_module('book_test_pack.draft_selection')

class SceneStagingTests(unittest.TestCase):
    setUp=fixtures.BookTests.setUp
    restore_module=fixtures.BookTests.restore_module

    def case(self):
        self.project['render_settings']['compact_prompt_policy']=11
        page=self.project['book']['pages'][1]
        page['scene_prompt']='A cutaway view of a tree. Mira reaches for the brass lamp inside the trunk.'
        spec=next(s for s in fixtures.story.asset_specs(self.project) if s['name']=='pages/page-002.png')
        return page,spec

    def test_reviewer_keeps_action_but_uses_same_camera_interpretation_as_renderer(self):
        page,spec=self.case();before=copy.deepcopy(self.project)
        _,brief,prose=quality.expected_scene(self.project,spec)
        self.assertIn('A close view of a tree.',brief)
        self.assertIn('Mira reaches for the brass lamp inside the trunk.',brief)
        self.assertEqual(prose,page['text'])
        self.assertEqual(self.project,before)

    def test_explicit_camera_request_and_story_content_remain_authoritative(self):
        page,spec=self.case()
        self.project['config']['art_style']='Educational cutaway illustrations'
        self.assertIn('cutaway view',quality.expected_scene(self.project,spec)[1])
        self.project['config']['art_style']='watercolour'
        page['text']='Mira pointed to the cutaway drawing on the wall.'
        self.assertIn('cutaway view',quality.expected_scene(self.project,spec)[1])

    def test_camera_normalization_does_not_rewrite_props_or_legacy_workflows(self):
        self.case()
        text='A cross-section view of the stone. The single coin remains inside its pocket.'
        self.assertEqual(staging.normalize(self.project,'',text),
                         'A close view of the stone. The single coin remains inside its pocket.')
        self.project['render_settings']['compact_prompt_policy']=10
        self.assertEqual(staging.normalize(self.project,'',text),text)

    def test_scene_planning_failure_continues_without_approving_any_image(self):
        _,spec=self.case()
        with patch.object(nodes.BookV2RenderAsset,'_run',side_effect=staging.ScenePromptError('Cannot reconcile scene')), \
             patch.object(selection,'try_select_review_candidate'),patch.object(preview,'refresh_review_draft'):
            result=nodes.BookV2RenderAsset().run(self.project,spec,'')
        self.assertEqual(result,('UNAPPROVED: '+spec['name'],))
        record=json.loads((fixtures.storage.review_directory(self.project,spec)/'failed.json').read_text())
        self.assertEqual(record['status'],'planning_failed')
        self.assertFalse(fixtures.storage.asset_path(self.project,spec['name']).exists())

    def test_integrity_errors_and_reference_failures_still_stop(self):
        _,spec=self.case()
        with patch.object(nodes.BookV2RenderAsset,'_run',side_effect=ValueError('Changed signature')):
            with self.assertRaisesRegex(ValueError,'Changed signature'):
                nodes.BookV2RenderAsset().run(self.project,spec,'')

    def test_recheck_archives_old_review_and_reuses_saved_pixels(self):
        _,spec=self.case();self.project['render_settings']['art_attempts']=1
        d=fixtures.storage.review_directory(self.project,spec);d.mkdir(parents=True)
        old=json.dumps({'qa_version':'1.40','signature':spec['signature'],'accepted':False})
        (d/'attempt-01-review.json').write_text(old)
        (d/'attempt-01-render.json').write_text(json.dumps({'seed':987,'prompt':'Original executed prompt'}))
        (d/'attempt-01.png').write_bytes(b'saved original pixels')
        fresh={**visual_report(self.project,spec,False),'qa_version':quality.QA_VERSION}
        with patch.object(nodes,'review_art',return_value=fresh) as review, \
             patch.object(preview,'refresh_review_draft'):
            result=nodes.BookV2RenderAsset().run(self.project,spec,'')
        self.assertIn('expand',result)
        self.assertEqual(review.call_args.args[2],b'saved original pixels')
        active=json.loads((d/'attempt-01-review.json').read_text())
        self.assertEqual(active['qa_version'],quality.QA_VERSION)
        self.assertEqual(active['seed'],987)
        self.assertEqual(active['prompt'],'Original executed prompt')
        self.assertFalse(active['accepted'])
        archives=list(d.glob('attempt-01-review-before-staging-*.json'))
        self.assertEqual(len(archives),1);self.assertEqual(archives[0].read_text(),old)
        self.assertEqual((d/'attempt-01.png').read_bytes(),b'saved original pixels')
        spec={**spec,'kind':'character'}
        with patch.object(nodes.BookV2RenderAsset,'_run',side_effect=staging.ScenePromptError('Reference invalid')):
            with self.assertRaises(staging.ScenePromptError):
                nodes.BookV2RenderAsset().run(self.project,spec,'')

    def test_changed_failure_status_keeps_history_without_stopping_next_page(self):
        _,spec=self.case();d=fixtures.storage.review_directory(self.project,spec)
        first={'status':'planning_failed','reason':'Failed planning','signature':spec['signature']}
        second={'status':'unapproved','reason':'Image retries exhausted','signature':spec['signature']}
        fixtures.storage.record_asset_failure(d,first)
        fixtures.storage.record_asset_failure(d,second)
        self.assertEqual(json.loads((d/'failed.json').read_text()),second)
        history=[json.loads(p.read_text()) for p in (d/'failure-history').glob('*.json')]
        self.assertIn(first,history);self.assertIn(second,history)

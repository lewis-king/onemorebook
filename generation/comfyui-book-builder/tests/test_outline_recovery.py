import importlib,json,unittest
from pathlib import Path
from unittest.mock import patch
import test_book as fixtures
nodes=importlib.import_module('book_test_pack.nodes')
planning=importlib.import_module('book_test_pack.planning')

class OutlineRecoveryTests(unittest.TestCase):
    setUp=fixtures.BookTests.setUp
    restore_module=fixtures.BookTests.restore_module

    def config(self):
        return {'page_count':3,'max_characters':3,'story_attempts':5,'seed':101,
                'age_range':'4-6','story_idea':'A child rescues a lost kite.',
                'ollama_url':'http://local.invalid','ollama_model':'local-writer','review_model':'local-reviewer'}

    def outline(self, title='Rejected mechanism'):
        value={k:'A concrete story detail.' for k in planning.outline_schema(3)['properties'] if k!='beats'}
        value['title']=title
        value['beats']=[{'page':n,**{k:'EXACT_PREVIOUS_BEAT_TEXT' for k in ['event','character_choice','what_changes','drawable_moment','page_turn_reason']}} for n in range(1,4)]
        return value

    def review(self, accepted):
        return {'accepted':accepted,'review':{'checks':{'continuity':accepted},'issues':[] if accepted else ['The mechanism contradicts the setup.'],'uncertain':False}}

    def test_two_failures_trigger_new_approach_without_full_failed_plot(self):
        value=self.outline()
        with patch.object(nodes,'ollama_generate',return_value=json.dumps(value)) as writer, patch.object(nodes,'review_outline',side_effect=[self.review(False),self.review(False),self.review(True)]):
            self.assertEqual(nodes.narrative_outline(self.output,self.config()),value)
        self.assertEqual(writer.call_count,3)
        self.assertIn('EXACT_PREVIOUS_BEAT_TEXT',writer.call_args_list[1].args[2])
        prompt=writer.call_args_list[2].args[2]
        self.assertNotIn('EXACT_PREVIOUS_BEAT_TEXT',prompt)
        self.assertIn('substantially different',prompt)
        self.assertIn(self.config()['story_idea'],prompt)
        self.assertEqual([c.args[4] for c in writer.call_args_list],[101,102,103])

    def test_exhaustion_stays_bounded_and_resume_does_not_spend_attempts_again(self):
        with patch.object(nodes,'ollama_generate',return_value=json.dumps(self.outline())) as writer, patch.object(nodes,'review_outline',return_value=self.review(False)) as reviewer:
            for _ in range(2):
                with self.assertRaisesRegex(ValueError,'Could not plan'):
                    nodes.narrative_outline(self.output,self.config())
            self.assertEqual(writer.call_count,5)
            self.assertEqual(reviewer.call_count,5)
        self.assertFalse((self.output/'outline.json').exists())

    def test_accepted_outline_is_reused_without_rewriting(self):
        value=self.outline('Approved and immutable')
        (self.output/'outline.json').write_text(json.dumps(value))
        with patch.object(nodes,'ollama_generate',side_effect=AssertionError('Rewrote saved outline')):
            self.assertEqual(nodes.narrative_outline(self.output,self.config()),value)

    def test_legacy_failed_files_are_preserved_and_trigger_new_approach(self):
        folder=self.output/'quality/outline';folder.mkdir(parents=True)
        old=folder/'attempt-05.txt';raw=json.dumps(self.outline());old.write_text(raw)
        (folder/'attempt-05-review.json').write_text(json.dumps(self.review(False)))
        with patch.object(nodes,'ollama_generate',return_value=json.dumps(self.outline('New plot'))) as writer, patch.object(nodes,'review_outline',return_value=self.review(True)):
            result=nodes.narrative_outline(self.output,self.config())
        self.assertEqual(result['title'],'New plot')
        self.assertIn('substantially different',writer.call_args.args[2])
        self.assertNotIn('EXACT_PREVIOUS_BEAT_TEXT',writer.call_args.args[2])
        self.assertEqual(old.read_text(),raw)

    def test_changed_request_cannot_reuse_an_old_draft_or_review(self):
        with patch.object(nodes,'ollama_generate',return_value=json.dumps(self.outline())), patch.object(nodes,'review_outline',return_value=self.review(False)):
            with self.assertRaisesRegex(ValueError,'Could not plan'):nodes.narrative_outline(self.output,self.config())
        changed={**self.config(),'story_idea':'A different explicit premise.'}
        with patch.object(nodes,'ollama_generate',side_effect=AssertionError('Overwrote old attempt')):
            with self.assertRaisesRegex(ValueError,'Saved outline request differs'):
                nodes.narrative_outline(self.output,changed)

    def test_new_editor_rechecks_saved_prose_without_regenerating_or_rewriting_requests(self):
        with patch.object(nodes,'ollama_generate',return_value=json.dumps(self.outline())) as writer, patch.object(nodes,'review_outline',return_value=self.review(False)):
            with self.assertRaisesRegex(ValueError,'Could not plan'):nodes.narrative_outline(self.output,self.config())
            self.assertEqual(writer.call_count,5)
        folder=self.output/'quality/outline/policy-2'
        requests={p.name:p.read_bytes() for p in folder.glob('*request.json')}
        # Simulate records from the older reviewer: keep them on disk while the
        # new review version gets its own records for the exact saved drafts.
        for p in folder.glob('*review-v2.json'):p.rename(p.with_name(p.name.replace('-v2','-v1')))
        different=self.review(False);different['review']['issues']=['A different supported concern.']
        with patch.object(nodes,'ollama_generate',side_effect=AssertionError('Regenerated saved prose')), patch.object(nodes,'review_outline',side_effect=[different,self.review(True)]) as editor:
            result=nodes.narrative_outline(self.output,self.config())
        self.assertEqual(editor.call_count,2)
        self.assertEqual(result,self.outline())
        for name,raw in requests.items():self.assertEqual((folder/name).read_bytes(),raw)
        self.assertEqual(len(list(folder.glob('*review-v1.json'))),5)

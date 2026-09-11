import copy
import hashlib
import importlib
import json
import unittest
from unittest.mock import patch

import test_book as fixtures
import test_assisted_creator as helpers

store=importlib.import_module('book_test_pack.assisted_store')
engine=importlib.import_module('book_test_pack.assisted_engine')
bases=importlib.import_module('book_test_pack.assisted_prompt_base')


class PromptBaseTests(unittest.TestCase):
    setUp=fixtures.BookTests.setUp
    restore_module=fixtures.BookTests.restore_module
    state=helpers.AssistedCreatorTests.state
    add=helpers.AssistedCreatorTests.add
    approve=helpers.AssistedCreatorTests.approve
    plan=helpers.AssistedCreatorTests.plan
    prepare=helpers.AssistedCreatorTests.prepare
    png=helpers.AssistedCreatorTests.png

    def scene(self):
        state=self.prepare()
        while store.stage(state)['kind']!='scene':state=self.approve(self.png(state))
        return state

    def context(self,state):
        current=store.stage(state)
        hashes={r:hashlib.sha256(engine.approved(state,r).read_bytes()).hexdigest()
                for r in current['references']}
        return bases.signature(state,current,hashes)

    def install(self,state,prompt='The corrected complete scene.'):
        base=bases.install(state,state['current_stage'],prompt,self.context(state),
                           reason='Fixture correction',source={'kind':'test_fixture'})
        return store.read(state['id']),base

    def test_blank_regenerate_uses_saved_base_verbatim_without_writer(self):
        state=self.scene();brief=store.stage(state)['brief'];original=engine.approved(state,'plan').read_bytes()
        state,base=self.install(state)
        intent=store.next_attempt(state)
        with patch.object(engine,'draft_json',side_effect=AssertionError('Saved base needs no rewrite')):
            prompt,refs,_=engine.image_inputs(state,store.stage(state),intent)
        self.assertEqual(prompt,base['prompt'])
        self.assertEqual(intent['prompt_base'],base)
        self.assertEqual(store.stage(store.read(state['id']))['brief'],brief)
        self.assertEqual(engine.approved(state,'plan').read_bytes(),original)
        self.assertEqual(len(refs),2)

    def test_first_fresh_scene_prepares_once_then_survives_restart(self):
        state=self.scene();intent=store.next_attempt(state)
        with patch.object(engine,'draft_json',return_value={'prompt':'A complete scene matching the prose.'}) as writer:
            first,_,_=engine.image_inputs(state,store.stage(state),intent)
        writer.assert_called_once()
        state=store.read(state['id'])
        self.assertEqual(store.stage(state)['prompt_base']['prompt'],first)
        # A failed image still keeps the successfully prepared full-scene prompt.
        state.update(status='error');store.save(state)
        next_intent=store.next_attempt(state)
        with patch.object(engine,'draft_json',side_effect=AssertionError('Do not repeat preparation')):
            second,_,_=engine.image_inputs(state,store.stage(state),next_intent)
        self.assertEqual(second,first)

    def test_feedback_updates_base_and_next_blank_attempt_retains_correction(self):
        state,old=self.install(self.scene())
        intent=store.next_attempt(state,'Keep the lantern attached to the boat.')
        with patch.object(engine,'draft_json',return_value={'prompt':'The lantern glows while attached to the boat.'}) as writer:
            corrected,_,_=engine.image_inputs(state,store.stage(state),intent)
        self.assertIn(old['prompt'],writer.call_args.args[3])
        state=store.read(state['id']);new=store.stage(state)['prompt_base']
        self.assertNotEqual(new['id'],old['id'])
        self.assertEqual(bases.verify(state,state['current_stage'],old),old)
        state['status']='error';store.save(state);intent=store.next_attempt(state)
        with patch.object(engine,'draft_json',side_effect=AssertionError('Feedback is already saved')):
            self.assertEqual(engine.image_inputs(state,store.stage(state),intent)[0],corrected)

    def test_edit_instruction_cannot_replace_full_scene_base(self):
        state,base=self.install(self.scene());state=self.png(state)
        candidate=engine.selected(state,state['current_stage'])
        intent=store.next_attempt(state,'Remove the extra sleeve badge.',mode='edit',source_candidate=candidate['id'])
        with patch.object(engine,'draft_json',return_value={'prompt':'Remove the extra sleeve badge in Image 1.'}):
            engine.image_inputs(state,store.stage(state),intent)
        self.assertEqual(store.stage(store.read(state['id']))['prompt_base'],base)

    def test_attempt_pins_its_base_even_if_a_new_revision_is_saved(self):
        state,first=self.install(self.scene(),'First base.')
        intent=store.next_attempt(state)
        second=bases.install(state,state['current_stage'],'Later base.',self.context(state),
                              reason='Later revision fixture',source={'kind':'test_fixture'},attempt=intent['attempt'])
        latest=store.read(state['id'])
        with patch.object(engine,'draft_json',side_effect=AssertionError('Pinned base must be reused')):
            self.assertEqual(engine.image_inputs(latest,store.stage(latest),intent)[0],first['prompt'])
        self.assertEqual(store.stage(store.read(state['id']))['prompt_base'],second)

    def test_changed_scene_context_invalidates_old_base(self):
        state,base=self.install(self.scene())
        store.stage(state)['text']='The lantern is now carried inside the boat.';store.save(state)
        intent=store.next_attempt(state)
        with patch.object(engine,'draft_json',return_value={'prompt':'The lantern rests inside the boat.'}) as writer:
            prompt,_,_=engine.image_inputs(state,store.stage(state),intent)
        writer.assert_called_once()
        self.assertNotEqual(prompt,base['prompt'])
        self.assertNotEqual(store.stage(store.read(state['id']))['prompt_base']['context_sha256'],base['context_sha256'])

    def test_old_intent_stays_legacy_and_tampered_base_is_rejected(self):
        state,base=self.install(self.scene())
        legacy={'attempt':9,'feedback':'','mode':'fresh','prompt_override':''}
        with patch.object(engine,'draft_json',side_effect=AssertionError('Old intent cannot acquire a new request')):
            prompt,_,_=engine.image_inputs(state,store.stage(state),legacy)
        self.assertNotEqual(prompt,base['prompt'])
        altered=copy.deepcopy(base);altered['prompt']='Unexpected replacement.'
        store.stage(state)['prompt_base']=altered;store.save(state)
        with self.assertRaisesRegex(ValueError,'changed after'):
            store.next_attempt(state)

    def test_manual_update_rejects_stale_or_running_state(self):
        state=self.scene();stale=copy.deepcopy(state)
        state,_=self.install(state)
        with self.assertRaises(store.Conflict):self.install(stale,'Stale edit.')
        store.next_attempt(state)
        with self.assertRaisesRegex(store.Conflict,'Wait for this attempt'):
            self.install(store.read(state['id']),'Overlapping edit.')

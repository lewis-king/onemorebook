import copy
import importlib
import unittest

import test_book

appearance = importlib.import_module('book_test_pack.appearance_review')


class AppearanceReviewTests(unittest.TestCase):
    def setUp(self):
        self.report = {
            'checks': {'scene_matches': False, 'anatomy_sound': True, 'style_matches': True},
            'uncertain': False, 'unexpected_character_count': 0,
            'issues': ['Pip looks happy.', 'Momo has no sandals.'],
            'retry_instructions': ['Give Pip a shocked expression.', 'Add Momo sandals.'],
            'characters': [
                {'id': 'pip', 'count': 1, 'identity_matches': True, 'appearance_matches': True, 'scale_matches': True, 'evidence': 'Matches.'},
                {'id': 'momo', 'count': 1, 'identity_matches': True, 'appearance_matches': False, 'scale_matches': True, 'evidence': 'Missing sandals.'}]}
        item = lambda i, addressed: {'index': i, 'this_character_appearance': addressed,
            'contradicted_by_visible_evidence': addressed, 'evidence': 'Brown sandal straps are visible.' if addressed else 'Expression is separate.'}
        self.audit = {'character_id': 'momo', 'candidate_observation': 'Brown strapped sandals cover the visible foot.',
            'reference_observation': 'Brown leather sandals with straps.', 'same_character': True,
            'required_appearance_present': True, 'disputed_features_visible': True, 'discrepancies': [],
            'uncertain': False, 'issues': [item(0, False), item(1, True)], 'retries': [item(0, False), item(1, True)]}

    def test_duplicate_missing_identity_and_uncertainty_never_enter_appearance_recheck(self):
        self.assertTrue(appearance.eligible(self.report, ['pip', 'momo']))
        mutations = [lambda r: r.update(uncertain=True), lambda r: r.update(unexpected_character_count=1),
                     lambda r: r['characters'][1].update(count=2), lambda r: r['characters'][1].update(count=0),
                     lambda r: r['characters'][1].update(identity_matches=False)]
        for mutate in mutations:
            r=copy.deepcopy(self.report); mutate(r)
            self.assertFalse(appearance.eligible(r, ['pip', 'momo']))

    def test_visible_evidence_corrects_only_appearance_and_its_specific_objections(self):
        self.assertTrue(appearance.apply_verified(self.report, self.report['characters'][1], self.audit))
        self.assertTrue(self.report['characters'][1]['appearance_matches'])
        self.assertFalse(self.report['checks']['scene_matches'])
        self.assertEqual(self.report['issues'], ['Pip looks happy.'])
        self.assertEqual(self.report['retry_instructions'], ['Give Pip a shocked expression.'])
        self.assertTrue(self.report['checks']['anatomy_sound'])

    def test_wrong_clothing_or_unseen_detail_cannot_clear_a_rejection(self):
        for mutation in ({'discrepancies': ['The required sandal is absent.']}, {'disputed_features_visible': False},
                         {'required_appearance_present': False}, {'same_character': False}, {'uncertain': True}):
            r=copy.deepcopy(self.report); a={**self.audit, **mutation}
            self.assertFalse(appearance.apply_verified(r, r['characters'][1], a))
            self.assertEqual(r, self.report)

    def test_missing_duplicate_or_wrong_issue_indices_cannot_clear_anything(self):
        for issues in ([], [self.audit['issues'][0]] * 2, [{**x, 'index': x['index']+1} for x in self.audit['issues']]):
            r=copy.deepcopy(self.report); a={**self.audit, 'issues': issues}
            self.assertFalse(appearance.apply_verified(r, r['characters'][1], a))
            self.assertEqual(r, self.report)

    def test_empty_appearance_objections_still_need_independent_action_confirmation(self):
        self.report['issues'] = ['Momo has no sandals.']
        self.audit['issues'] = [{**self.audit['issues'][1], 'index': 0}]
        self.assertTrue(appearance.apply_verified(self.report, self.report['characters'][1], self.audit))
        self.assertTrue(appearance.needs_scene_confirmation(self.report, [{'changed': True}]))
        self.assertFalse(appearance.confirmed_scene({'story_event_visible': False, 'uncertain': False,
            'essential_issues': ['Required contact is missing.'], 'prior_issues': [],
            'observed_event': 'Standing.', 'required_story_event': 'Holding the shared object.'}))
        self.assertTrue(appearance.confirmed_scene({'story_event_visible': True, 'uncertain': False,
            'essential_issues': [], 'prior_issues': [], 'observed_event': 'Holding the shared object.',
            'required_story_event': 'Holding the shared object.'}))
        self.report['checks']['anatomy_sound'] = False
        self.assertFalse(appearance.needs_scene_confirmation(self.report, [{'changed': True}]))

    def test_active_or_detached_costume_is_left_to_existing_state_audits(self):
        from unittest.mock import patch
        ledger=importlib.import_module('book_test_pack.state_ledger')
        changes=[{'id':'scarf_off','character_id':'pip'},{'id':'cape_off','character_id':'momo'}]
        project={'art_plan':{'ledger':{'changes':changes}}}
        with patch.object(ledger,'active_changes',return_value=[changes[0]]), patch.object(ledger,'inactive_additions',return_value=[]):
            self.assertEqual(appearance.state_owned_characters(project,{},{}),{'pip'})
            self.assertEqual(appearance.state_owned_characters(project,{},
                {'props':[{'source_change_id':'cape_off'}]}),{'pip','momo'})


if __name__ == '__main__':
    unittest.main()

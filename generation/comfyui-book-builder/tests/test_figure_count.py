import importlib
import unittest
import test_book as fixtures

counter=importlib.import_module('book_test_pack.figure_count')


class FigureCountTests(unittest.TestCase):
    setUp=fixtures.BookTests.setUp
    restore_module=fixtures.BookTests.restore_module

    def audit(self,observations,extra=(),uncertain=False):
        self.project['config']['ollama_url']='http://unused'
        self.project['render_settings']['review_model']='fixture'
        inventory={'figure_count':3,'visible_figures':['child','mouse','stone face']}
        return counter.reconcile_scene_count(self.project,{'kind':'scene','name':'pages/page-002.png'},
            b'candidate',inventory,lambda *args:{'observations':observations,
                'additional_characters':list(extra),'uncertain':uncertain})

    def observations(self):
        return [{'inventory_index':i,'category':kind,'character_id':cid,'evidence':'Observed material and role.'}
                for i,(kind,cid) in enumerate([('character','mira'),('character','pip'),('inanimate_depiction','unknown')])]

    def test_depiction_is_excluded_but_duplicates_and_additional_characters_remain(self):
        observations=self.observations();report=self.audit(observations)
        self.assertTrue(report['resolved']);self.assertEqual(report['figure_count'],2)
        observations[2].update(category='character',character_id='mira')
        report=self.audit(observations)
        self.assertEqual(report['figure_count'],3);self.assertEqual(report['per_character']['mira'],2)
        report=self.audit(self.observations(),extra=['another visible child'])
        self.assertEqual(report['figure_count'],3)

    def test_partial_duplicated_or_uncertain_classification_cannot_clear_blind_count(self):
        observations=self.observations()
        for value,uncertain in [(observations[:2],False),(observations[:2]+[observations[1]],False),
                                 (observations,True)]:
            report=self.audit(value,uncertain=uncertain)
            self.assertFalse(report['resolved']);self.assertEqual(report['figure_count'],3)
        observations[2]['category']='uncertain'
        self.assertFalse(self.audit(observations)['resolved'])

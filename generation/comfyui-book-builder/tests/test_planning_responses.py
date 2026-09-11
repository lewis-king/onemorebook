import copy,importlib,json,unittest
from unittest.mock import Mock
import jsonschema
import test_book as fixtures
library=importlib.import_module('book_test_pack.visual_library')

class PlanningResponseTests(unittest.TestCase):
    setUp=fixtures.BookTests.setUp
    restore_module=fixtures.BookTests.restore_module
    def schema(self):
        return {'type':'object','required':['missing'],'properties':{'missing':{'type':'array','items':{'type':'array','minItems':2,'uniqueItems':True,'items':{'enum':['page1','page2']}}}}}
    def call(self,generate):
        return library.checked_model_call(self.output,'audit',generate,'http://local.invalid','local-reviewer','Source story',self.schema())
    def test_duplicate_page_transport_error_is_corrected_and_saved(self):
        bad={'missing':[['page1','page1']]};calls=[]
        def generate(url,model,prompt,schema,**kwargs):
            calls.append((prompt,kwargs['seed']))
            if len(calls)==1:jsonschema.validate(bad,schema)
            return {'missing':[]}
        self.assertEqual(self.call(generate),{'missing':[]})
        self.assertEqual(len(calls),2)
        self.assertIn('only one story page',calls[1][0])
        self.assertEqual([c[1] for c in calls],[0,1])
        error=next(self.output.rglob('*error.json'));self.assertEqual(json.loads(error.read_text())['invalid_fragment'],['page1','page1'])
        self.assertEqual(self.call(Mock(side_effect=AssertionError('Repeated saved request'))),{'missing':[]})
    def test_invalid_injected_reply_is_not_accepted(self):
        generate=Mock(side_effect=[{'missing':[['page2','page2']]},{'missing':[]}])
        self.assertEqual(self.call(generate),{'missing':[]});self.assertEqual(generate.call_count,2)
    def test_exhaustion_remains_bounded_across_restart(self):
        generate=Mock(return_value={'missing':[['page1','page1']]})
        for _ in range(2):
            with self.assertRaisesRegex(ValueError,'three saved attempts'):self.call(generate)
        self.assertEqual(generate.call_count,3)
        self.assertEqual(len(list(self.output.rglob('*error.json'))),3)
    def test_valid_missing_subject_is_preserved_for_semantic_rejection(self):
        value={'missing':[['page1','page2']]}
        self.assertEqual(self.call(Mock(return_value=value)),value)

    def observations(self, scenes):
        return {'faithful':True,'routing_correct':True,'uncertain':False,'evidence':'Source checked.',
                'design_or_routing_issues':[], 'missing_subject_observations':[
                    {'name':'Pedestal','visible_scenes':scenes,'evidence':'Shown in these scenes.'}]}
    def test_duplicate_page_cannot_fabricate_a_recurring_subject(self):
        raw=self.observations(['page12','page12']);before=copy.deepcopy(raw)
        result=library.classify_observations(raw)
        self.assertTrue(result['complete']);self.assertFalse(result['missing_recurring_subjects'])
        self.assertEqual(result['one_page_observations'][0]['distinct_visible_scenes'],['page12'])
        self.assertEqual(raw,before)
    def test_actual_missing_recurring_subject_still_blocks_completeness(self):
        result=library.classify_observations(self.observations(['page1','page2','page1']))
        self.assertFalse(result['complete']);self.assertEqual(len(result['missing_recurring_subjects']),1)
    def test_one_page_observation_does_not_clear_other_failures(self):
        raw=self.observations(['page12']);raw.update(faithful=False,routing_correct=False,uncertain=True)
        raw['design_or_routing_issues']=['Wrong design.']
        result=library.classify_observations(raw)
        self.assertFalse(result['faithful']);self.assertFalse(result['routing_correct'])
        self.assertTrue(result['uncertain']);self.assertEqual(result['issues'],['Wrong design.'])

import copy
import importlib
import json
from pathlib import Path
import test_book as fixtures

relations=importlib.import_module('book_test_pack.object_relations')


class ObjectRelationTests(fixtures.unittest.TestCase):
    setUp=fixtures.BookTests.setUp
    restore_module=fixtures.BookTests.restore_module

    def install(self):
        self.project['book_root']=str(self.output/'books/relation-test')
        self.project['render_settings'].update(scene_context_policy=3,review_model='fixture')
        self.project['config']['ollama_url']='unused'
        self.project['scene_contract']={'objects':[{'id':'box','name':'Wooden box','appearance':'Wooden cube.'},
            {'id':'key','name':'Brass key','appearance':'Small brass key.'}]}
        self.row={'id':'key_in_box','content_id':'key','container_id':'box',
            'from_page':1,'through_page':2,'source_evidence':'Key placed in box on page1, retrieved on page3.'}
        self.project['object_relations']={'relations':[self.row]}

    def test_relationship_stops_at_retrieval_and_does_not_leak_into_cover(self):
        self.install()
        self.assertEqual(relations.active(self.project,'pages/page-002.png'),[self.row])
        self.assertEqual(relations.active(self.project,'pages/page-003.png'),[])
        self.assertEqual(relations.active(self.project,'cover.png'),[])

    def test_empty_occupied_occluded_and_offscreen_interiors(self):
        self.install();spec={'name':'pages/page-002.png'}
        for interior,content,surface,expected in [
            ('visibly_empty','absent','',False),('occupied','visible','',True),
            ('not_visible','unclear','',True),('occupied','physically_occluded','visible opaque divider',True),
            ('occupied','physically_occluded','',False),('unclear','unclear','',False),
            ('visibly_empty','visible','',False)]:
            with self.subTest(interior=interior,content=content,surface=surface):
                raw={'items':[{'id':'key_in_box','interior':interior,'expected_content':content,
                    'occluding_surface':surface,'observation':'Observed test interior.'}]}
                result=relations.inspect_contents(self.project,spec,b'pixels',lambda *a:raw)
                self.assertEqual(result['accepted'],expected)

    def test_omitted_relation_cannot_pass_and_inactive_relation_makes_no_model_call(self):
        self.install()
        self.assertFalse(relations.inspect_contents(self.project,{'name':'pages/page-001.png'},b'',lambda *a:{'items':[]})['accepted'])
        def forbidden(*args):raise AssertionError('No relationship is active here')
        self.assertTrue(relations.inspect_contents(self.project,{'name':'pages/page-003.png'},b'',forbidden)['accepted'])

    def test_plan_checkpoint_public_contract_and_tamper_detection(self):
        self.install();before=copy.deepcopy(self.project['story']);calls=[]
        def generate(url,model,prompt,schema):
            calls.append(prompt)
            if 'relations' in schema['properties']:return {'relations':[self.row]}
            return {'correct_contents':True,'correct_intervals':True,'complete':True,'uncertain':False,'issues':[],'evidence':'Prose checked.'}
        first=relations.compile_relations(self.project,'fixture',generate)
        self.assertEqual(first,relations.compile_relations(self.project,'fixture',generate))
        self.assertEqual(len(calls),2)
        self.assertEqual(self.project['story'],before)
        path=next(Path(self.project['book_root']).glob('object-relations/*/approved.json'))
        changed=json.loads(path.read_text());changed['relations'][0]['through_page']=3;path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError,'provenance mismatch'):relations.compile_relations(self.project,'fixture',generate)

    def test_incorrect_timeline_audit_blocks_rendering(self):
        self.install()
        def generate(url,model,prompt,schema):
            if 'relations' in schema['properties']:return {'relations':[self.row]}
            return {'correct_contents':True,'correct_intervals':False,'complete':True,'uncertain':False,
                'issues':['Contents persist after removal.'],'evidence':'Retrieval page contradicts interval.'}
        with self.assertRaisesRegex(ValueError,'did not pass'):relations.compile_relations(self.project,'fixture',generate)

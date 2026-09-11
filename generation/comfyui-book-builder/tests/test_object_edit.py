import copy,hashlib,importlib,json
from unittest.mock import patch
import unittest
import test_duplicate_edit as duplicate_fixtures
from test_book import storage,render
from test_quality import visual_report
policy=importlib.import_module('book_test_pack.object_edit')

class ObjectEditTests(unittest.TestCase):
    setUp=duplicate_fixtures.DuplicateEditTests.setUp
    restore_module=duplicate_fixtures.DuplicateEditTests.restore_module
    case=duplicate_fixtures.DuplicateEditTests.case
    def object_case(self):
        spec,report,_,directory=self.case()
        report['review']['unexpected_character_count']=0
        for c in report['review']['characters']:c['count']=1
        report['review']['issues']=['An extra container with duplicated contents.']
        plan={'decision':'remove_extra_object_cluster','objects':{'container':[{'location':'left'},{'location':'right'}]},
              'target_id':'container','keep':'the original container held by Mira','remove':'the detached extra container and contents on the right',
              'removed_object_ids':['container','light'],'preserve':['Mira’s pose and held original contents'],
              'fill':'the surrounding garden','reason':'Separate extra copy',
              'checks':{k:True for k in policy.CHECKS},'remaining_defects_after_removal':[]}
        (directory/'attempt-01-review.json').write_text(json.dumps(report))
        return spec,report,plan,directory

    def test_object_repair_requires_complete_unduplicated_cast(self):
        spec,r,_,_=self.object_case();ids=[c['id'] for c in r['review']['characters']]
        self.assertTrue(policy.eligible(r,ids))
        for field,value in [('count',0),('count',2),('appearance_matches',False),('scale_matches',False)]:
            bad=copy.deepcopy(r);bad['review']['characters'][0][field]=value
            self.assertFalse(policy.eligible(bad,ids))

    def test_object_repair_resume_and_single_edit_budget(self):
        spec,r,plan,d=self.object_case()
        with patch.object(policy,'plan_edit',return_value=plan):record=policy.prepare_edit(self.project,spec,1,2,r)
        (d/'attempt-02-strategy.json').write_text(json.dumps({'signature':spec['signature'],'strategy':'object_removal'}))
        with patch.object(policy,'plan_edit',side_effect=AssertionError('Must not plan twice')):
            self.assertEqual(policy.prepare_edit(self.project,spec,1,2,r),record)
            self.assertIsNone(policy.prepare_edit(self.project,spec,1,3,r))
        (d/'attempt-01.png').write_bytes(b'changed');self.assertIsNone(policy.prepare_edit(self.project,spec,1,2,r))

    def test_object_edit_has_only_source_image_and_base_recipe(self):
        spec,r,plan,d=self.object_case()
        record={'signature':spec['signature'],'source_attempt':1,'source_sha256':r['png_sha256'],'plan':plan}
        g=policy.expand_edit(self.project,spec,2,record)['expand']
        self.assertEqual(sum(n['class_type']=='ReferenceLatent' for n in g.values()),1)
        self.assertFalse(any(n['class_type']=='LoraLoaderModelOnly' for n in g.values()))
        info=json.loads(next(n['inputs']['generation_info'] for n in g.values() if n['class_type']=='BookV2ReviewAsset'))
        self.assertEqual(info['method'],'image_edit');self.assertEqual(info['steps'],28)

    def test_lost_original_contents_vetoes_otherwise_passing_review(self):
        spec,r,plan,d=self.object_case()
        record={'signature':spec['signature'],'source_attempt':1,'source_sha256':r['png_sha256'],'plan':plan}
        (d/'attempt-02-object-plan.json').write_text(json.dumps(record))
        (d/'attempt-02-strategy.json').write_text(json.dumps({'signature':spec['signature'],'strategy':'object_removal'}))
        result={'checks':{k:True for k in policy.PRESERVATION},'uncertain':False,'evidence':'The original contents vanished.','issues':['Original contents removed too.']}
        result['checks']['original_objects_and_contents_preserved']=False
        good=visual_report(self.project,spec,True)
        checked=policy.apply_edit_review(self.project,spec,2,b'after',good,lambda *a,**k:result)
        self.assertFalse(checked['accepted'])

    def test_turbo_retry_controller_routes_object_removal_before_redraw(self):
        spec,r,plan,d=self.object_case()
        self.project['render_settings'].update(object_edit_policy=1,art_attempts=5)
        record={'signature':spec['signature'],'source_attempt':1,'source_sha256':r['png_sha256'],'plan':plan}
        nodes=importlib.import_module('book_test_pack.nodes')
        with patch.object(policy,'prepare_edit',return_value=record),patch.object(policy,'expand_edit',return_value={'repair':True}) as expand:
            result=nodes.BookV2RenderAsset().run(self.project,spec,'')
        self.assertEqual(result,{'repair':True})
        self.assertEqual(expand.call_args.args[-1],record)
        self.assertEqual(json.loads((d/'attempt-02-strategy.json').read_text())['strategy'],'object_removal')

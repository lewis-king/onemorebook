import copy
import hashlib
import importlib
import json
from pathlib import Path
from unittest.mock import patch
import unittest

import test_book as fixtures
from test_book import storage

details=importlib.import_module('book_test_pack.scene_details')
assets=importlib.import_module('book_test_pack.state_assets')


class SceneDetailTests(unittest.TestCase):
    setUp=fixtures.BookTests.setUp
    restore_module=fixtures.BookTests.restore_module

    def test_actual_low_score_button_is_retained_but_container_is_not_counted(self):
        data=json.loads((Path(__file__).parent/'fixtures/scene-button-proposals.json').read_text())
        before=copy.deepcopy(data['proposals'])
        selected=details.object_proposals(data['proposals'],data['garment_size'])
        self.assertEqual(len(selected),2)
        self.assertTrue(any(o['score']<.35 for o in selected))
        self.assertEqual(before,data['proposals'])
        self.assertTrue(all(o['bbox'][2]-o['bbox'][0]<30 for o in selected))

    def test_a_real_button_in_a_hand_is_not_an_attached_clothing_button(self):
        item={'result':{'kind':'sewing_button','uncertain':False,'support_surface':'hand_or_paw'}}
        self.assertFalse(details.confirmed_attached(item))
        item['result']['support_surface']='garment_fabric'
        self.assertTrue(details.confirmed_attached(item))
        item['result']['uncertain']=True
        self.assertFalse(details.confirmed_attached(item))
        item['result'].update(kind='button_like_dot',uncertain=False)
        self.assertFalse(details.confirmed_attached(item))

    def test_no_excess_or_unresolved_observation_never_clears_existing_failures(self):
        report={'checks':{'scene_matches':False,'anatomy_sound':False},'issues':['Missing rabbit'],'uncertain':True}
        before=copy.deepcopy(report)
        for review in (None,{'excess_visible':False,'items':[]},
                       {'excess_visible':False,'items':[{'observation':{'status':'unresolved'}}]}):
            details.apply_scene_fastening_review(report,review)
            self.assertEqual(before,report)
        details.apply_scene_fastening_review(report,{'excess_visible':True,'items':[{
            'excess_visible':True,'character_id':'pip','confirmed_attached_count':2,'inventory':{'remaining':1}}]})
        self.assertIn('Missing rabbit',report['issues'])
        self.assertTrue(report['uncertain'])
        self.assertTrue(any('confirm 2 attached solid buttons' in issue for issue in report['issues']))

    def test_inventory_uses_original_measured_removals_and_checks_source_integrity(self):
        change={'id':'lost_button'}
        root=Path(self.project['render_root']);root.mkdir(parents=True,exist_ok=True)
        baseline=root/'baseline.png';baseline.write_bytes(b'original-pixels')
        directory=root/'measurement';directory.mkdir()
        first={'bbox':[10,10,30,30],'score':.8};second={'bbox':[10,50,30,70],'score':.7}
        record={'change':change,'source_name':'baseline.png','source_sha256':hashlib.sha256(baseline.read_bytes()).hexdigest(),
                'proposals':[first,second],'selected':[first]}
        storage.write_json(directory/'measurement.json',record)
        storage.write_json(directory/'measurement-review.json',{'matches':True,'uncertain':False,'issues':[]})
        with patch.object(assets,'detail_directory',return_value=directory),patch.object(storage,'asset_path',return_value=baseline):
            inventory=details.remaining_inventory(self.project,change)
            self.assertEqual((inventory['original'],inventory['removed'],inventory['remaining']),(2,1,1))
            record['selected']=[first,first];(directory/'measurement.json').write_text(json.dumps(record))
            with self.assertRaises(ValueError):details.remaining_inventory(self.project,change)
            record['selected']=[first];(directory/'measurement.json').write_text(json.dumps(record))
            baseline.write_bytes(b'changed-pixels')
            with self.assertRaises(ValueError):details.remaining_inventory(self.project,change)

    def test_unrelated_assets_and_books_without_states_make_no_model_calls(self):
        def no_model(*args):raise AssertionError('Unexpected model request')
        original=copy.deepcopy(self.project)
        for spec in ({'kind':'character'},{'kind':'scene'}):
            self.assertIsNone(details.review_scene_fastening_inventory(self.project,spec,b'',no_model))
        self.assertEqual(original,self.project)

    def test_clothing_query_uses_explicit_colour_without_borrowing_fur_or_neighbour_clothes(self):
        self.assertEqual(details.garment_query({'appearance':'Cream rabbit, blue buttoned waistcoat.'},'waistcoat'),'blue waistcoat')
        self.assertEqual(details.garment_query({'appearance':'Blue trousers and red coat.'},'coat'),'red coat')
        self.assertEqual(details.garment_query({'appearance':'Cream rabbit, waistcoat.'},'waistcoat'),'waistcoat')
        self.assertEqual(details.garment_query({'appearance':'Cream rabbit wearing a waistcoat.'},'waistcoat'),'waistcoat')

    def test_noncontact_pointing_blocks_independent_resize(self):
        repair=importlib.import_module('book_test_pack.repair')
        free={'can_resize_independently':True,'anchored_interactions':[],'uncertain':False}
        self.assertTrue(repair.resize_relations_allow(free))
        coupled={**free,'anchored_interactions':['The child points at the rabbit chest.']}
        self.assertFalse(repair.resize_relations_allow(coupled))
        self.assertFalse(repair.resize_relations_allow({**free,'uncertain':True}))

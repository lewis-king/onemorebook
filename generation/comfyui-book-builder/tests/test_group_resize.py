import importlib
import unittest
from unittest.mock import patch
import test_book as fixtures

repair=importlib.import_module('book_test_pack.repair')
detection=importlib.import_module('book_test_pack.detection')


class GroupResizeTests(unittest.TestCase):
    def test_group_requires_explicit_exclusive_ownership_without_outside_contact(self):
        audit={'can_resize_independently':False,'target_holds_object':True,'held_objects':['jar'],
               'can_resize_with_held_objects':True,'other_anchored_interactions':[],'uncertain':False}
        self.assertFalse(repair.resize_relations_allow(audit))
        self.assertTrue(repair.resize_group_allow(audit))
        self.assertFalse(repair.resize_group_allow(audit,require_grounded=True))
        self.assertTrue(repair.resize_group_allow({**audit,'target_grounded':True},require_grounded=True))
        for changes in [{'other_anchored_interactions':['Another actor holds the same jar']},
                        {'uncertain':True},{'can_resize_with_held_objects':False},
                        {'held_objects':[]}]:
            self.assertFalse(repair.resize_group_allow({**audit,**changes}))
        del audit['can_resize_with_held_objects']
        self.assertFalse(repair.resize_group_allow(audit))

    def test_carrying_prop_can_reach_group_audit_but_not_override_it(self):
        report={'geometry':{'suki':{'safe_to_resize':False,'measurement_decisive':True,'relative_factor':2.0}},
                'scale_review':{'characters':[{'id':'suki','pose':'standing_upright',
                    'full_body_visible':True,'same_depth_as_largest':True,'independent_ground_contact':False}]}}
        self.assertTrue(repair.group_resize_candidate(report,'suki'))
        report['scale_review']['characters'][0]['full_body_visible']=False
        self.assertFalse(repair.group_resize_candidate(report,'suki'))

    def test_prop_localization_rejects_unknown_or_other_actor_overlap(self):
        candidate={'held_0':{'bbox':[500,400,600,600],'image_size':[1000,1000]}}
        with patch.object(detection,'detect_cast',return_value=({},[])):
            with self.assertRaisesRegex(ValueError,'uniquely detected'):
                repair.locate_held_objects(b'fixture',['jar'],[])
        with patch.object(detection,'detect_cast',return_value=(candidate,[])) as detect:
            boxes,_=repair.locate_held_objects(b'fixture',['jar of honey'],[[10,10,200,800]])
            self.assertEqual(boxes,[[500,400,600,600]])
            self.assertEqual(detect.call_args.args[1][0]['detection_prompt'],'jar')
            with self.assertRaisesRegex(ValueError,'different actor'):
                repair.locate_held_objects(b'fixture',['jar'],[[550,400,650,600]])


if __name__=='__main__':unittest.main()

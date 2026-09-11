import importlib
import unittest
import test_book as fixtures

contract=importlib.import_module('book_test_pack.scene_contract')


class PropPromptTests(unittest.TestCase):
    setUp=fixtures.BookTests.setUp
    restore_module=fixtures.BookTests.restore_module

    def configured(self):
        p=self.project
        p['render_settings']['scene_contract_prompt_policy']=1
        p['scene_contract']={'objects':[
            {'id':'red_ball','name':'Red Ball','appearance':'Smooth red rubber sphere.'},
            {'id':'magic_bubble','name':'Magic Bubble','appearance':'Large iridescent sphere.'},
            {'id':'yellow_scarf','name':'Yellow Scarf','appearance':'Chunky yellow knit with tassels.'},
            {'id':'stone_statue','name':'Stone Statue','appearance':'A grey crowned stone figure.'}],
            'persistent_facts':[
                {'id':'bubble_gone','object_ids':['magic_bubble'],'requirement':'The bubble is absent.',
                 'visibility':'absent','from_page':3,'through_page':3},
                {'id':'scarf_sticky','object_ids':['yellow_scarf'],'requirement':'IF the scarf is visible it is sticky.',
                 'visibility':'conditional','from_page':2,'through_page':3}],
            'scenes':{}}
        return p

    def test_absent_objects_and_offscreen_conditional_props_do_not_get_drawn_back_in(self):
        p=self.configured()
        scene={'page_number':3,'scene_prompt':'Pip is not wearing his scarf; he hugs his red ball. The bubble is gone.'}
        p['story']['pages'][2]['text']='Pip hugged the red ball. The bubble vanished.'
        p['scene_contract']['scenes']['pages/page-003.png']={'literal_prompt':scene['scene_prompt'],
            'object_ids':['red_ball','magic_bubble','yellow_scarf'],'checks':[]}
        prompt=contract.scene_brief(p,scene)
        self.assertIn('Smooth red rubber sphere.',prompt)
        self.assertNotIn('Large iridescent sphere.',prompt)
        self.assertNotIn('Chunky yellow knit',prompt)
        self.assertNotIn('IF the scarf',prompt)
        self.assertIn('The bubble is absent.',prompt)
        # The visual gate still checks absent and optional props independently.
        effective=contract.effective_record(p,'pages/page-003.png')
        self.assertEqual(len(effective['checks']),2)
        self.assertIn('yellow_scarf',effective['object_ids'])

    def test_actually_held_detached_scarf_keeps_its_design_and_sticky_state(self):
        p=self.configured()
        scene={'page_number':2,'scene_prompt':'Pip is not wearing his scarf; he holds the yellow scarf flat.'}
        p['story']['pages'][1]['text']='He took off his yellow scarf and held it out.'
        p['scene_contract']['scenes']['pages/page-002.png']={'literal_prompt':scene['scene_prompt'],
            'object_ids':['yellow_scarf'],'checks':[]}
        prompt=contract.scene_brief(p,scene)
        self.assertIn('Chunky yellow knit with tassels.',prompt)
        self.assertIn('IF the scarf',prompt)

    def test_prose_binds_whole_statue_when_art_mentions_only_its_crown(self):
        p=self.configured()
        scene={'page_number':2,'scene_prompt':'Pip pushes the bubble toward the stone crown.'}
        p['story']['pages'][1]['text']='Pip pushed toward the statue’s sharp crown.'
        p['scene_contract']['scenes']['pages/page-002.png']={'literal_prompt':scene['scene_prompt'],
            'object_ids':['magic_bubble'],'checks':[]}
        prompt=contract.scene_brief(p,scene)
        self.assertIn('A grey crowned stone figure.',prompt)
        self.assertIn('stone_statue',contract.effective_record(p,'pages/page-002.png')['object_ids'])


if __name__=='__main__':unittest.main()

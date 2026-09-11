import copy
import hashlib
import importlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, MagicMock
import numpy as np
import torch

import test_book as fixtures
from test_quality import visual_report
from test_visual_library import entry

qwen=importlib.import_module('book_test_pack.qwen_book')
compiler=importlib.import_module('book_test_pack.compact_prompt')
session=importlib.import_module('book_test_pack.review_session')
quality_preview=importlib.import_module('book_test_pack.quality_preview')


class QwenBookTests(unittest.TestCase):
    setUp=fixtures.BookTests.setUp
    restore_module=fixtures.BookTests.restore_module

    def setup_qwen(self):
        self.project['render_settings'].update(qwen.MODELS,renderer='qwen',qwen_scene_recipe=qwen.RECIPE,
            reference_strategy='cast_guide',edit_steps=8,edit_cfg=1.0,review_model='local')
        for c,height in zip(self.project['book']['characters'],[100,45,60]):c['height_cm']=height
        return next(s for s in fixtures.story.asset_specs(self.project) if s['name']=='pages/page-002.png')

    def test_three_cast_and_prop_location_fit_actual_qwen_inputs(self):
        self.setup_qwen()
        self.project['visual_library']={'version':1,'plan':{'entries':[entry(),entry('garden','location')]}}
        spec=next(s for s in fixtures.story.asset_specs(self.project) if s['name']=='pages/page-002.png')
        with patch.object(compiler,'compile_prompt',return_value='Concise checked prompt') as compiled:
            graph=fixtures.render.expand_attempt(self.project,spec,1)['expand']
        kinds={k:n for k,n in graph.items()}
        pos=next(n['inputs'] for n in graph.values() if n['class_type']=='TextEncodeQwenImageEditPlus')
        self.assertEqual([k for k in pos if k.startswith('image')],['image1','image2','image3'])
        self.assertEqual(kinds[pos['image1'][0]]['class_type'],'BookV2ScaleGuide')
        self.assertEqual(kinds[pos['image2'][0]]['inputs']['kind'],'prop')
        self.assertEqual(kinds[pos['image3'][0]]['inputs']['kind'],'location')
        self.assertIn('Image 2 is the canonical prop reference',compiled.call_args.args[2])
        self.assertIn('Image 3 is the canonical location reference',compiled.call_args.args[2])
        sampler=next(n['inputs'] for n in graph.values() if n['class_type']=='KSampler')
        latent=kinds[sampler['latent_image'][0]]['inputs']
        self.assertEqual(latent['pixels'],pos['image1'])
        self.assertEqual((sampler['steps'],sampler['cfg'],sampler['seed']),(8,1.0,spec['seed']))
        self.assertEqual(pos['prompt'],'Concise checked prompt')
        self.assertTrue(any(n['class_type']=='LoraLoaderModelOnly' and n['inputs']['lora_name']==qwen.MODELS['edit_lora'] for n in graph.values()))

    def test_retry_draws_fresh_canonical_cast_and_keeps_feedback_and_seed(self):
        spec=self.setup_qwen()
        with patch.object(compiler,'compile_prompt',side_effect=lambda p,s,text,count:text):
            graph=fixtures.render.expand_attempt(self.project,spec,2,'Mira holds the lamp.',correction_attempt=1,scale_repair=True)['expand']
        types=[n['class_type'] for n in graph.values()]
        self.assertNotIn('BookV2LoadRepair',types)
        self.assertNotIn('BookV2LoadCandidate',types)
        sampler=next(n['inputs'] for n in graph.values() if n['class_type']=='KSampler')
        self.assertEqual(sampler['seed'],fixtures.story.asset_seed(spec['seed'],'retry-2'))
        prompt=next(n['inputs']['prompt'] for n in graph.values() if n['class_type']=='TextEncodeQwenImageEditPlus')
        self.assertIn('Required corrections',prompt)
        self.assertIn('Mira holds the lamp.',prompt)

    def test_single_actor_uses_portrait_and_empty_scene_never_invents_a_cast_guide(self):
        self.setup_qwen()
        specs=fixtures.story.asset_specs(self.project)
        for name in ('pages/page-001.png','pages/page-003.png'):
            spec=next(s for s in specs if s['name']==name)
            with patch.object(compiler,'compile_prompt',side_effect=lambda p,s,text,count:text):
                graph=fixtures.render.expand_attempt(self.project,spec,1)['expand']
            self.assertFalse(any(n['class_type']=='BookV2ScaleGuide' for n in graph.values()))
            loaded=[n['inputs']['asset_name'] for n in graph.values() if n['class_type']=='BookV2LoadReference']
            self.assertIn('characters/mira.png' if name.endswith('001.png') else 'style.png',loaded)

    def test_legacy_qwen_remains_unaccelerated_edit_recipe(self):
        self.project['render_settings']['renderer']='qwen'
        spec=next(s for s in fixtures.story.asset_specs(self.project) if s['name']=='pages/page-002.png')
        with patch.object(qwen,'expand_scene',side_effect=AssertionError('Legacy renderer must stay intact')):
            graph=fixtures.render.expand_attempt(self.project,spec,1)['expand']
        sampler=next(n['inputs'] for n in graph.values() if n['class_type']=='KSampler')
        self.assertEqual((sampler['steps'],sampler['cfg']),(40,4.0))
        self.assertFalse(any(n['class_type']=='LoraLoaderModelOnly' for n in graph.values()))

    def source_fixture(self):
        source=copy.deepcopy(self.project)
        source['book_root']=str(self.output/'books/source')
        source['render_root']=str(self.output/'books/source/renders/old')
        source['config'].update(page_count=3,max_characters=3)
        source['render_settings'].update(quality_required=True,review_model='local')
        for spec in fixtures.story.asset_specs(source):
            report=visual_report(source,spec)
            pixels=np.tile(np.linspace(0,1,1024,dtype=np.float32)[None,None,:,None],(1,1024,1,3))
            png=fixtures.storage.image_bytes(spec,torch.from_numpy(pixels))
            report.update(png_sha256=hashlib.sha256(png).hexdigest(),attempt=1,seed=spec['seed'],prompt=spec['prompt'])
            fixtures.storage.publish_reviewed_asset(source,spec,png,report)
        path=Path(source['render_root'])/'prepared-state-project.json'
        fixtures.storage.write_json(path,source)
        model=self.output/'dummy-model';model.write_bytes(b'metadata')
        sys.modules['folder_paths'].get_full_path=lambda category,name:str(model)
        return source,path

    def test_new_edition_retains_verified_references_and_never_reuses_pages(self):
        source,path=self.source_fixture();before=path.read_bytes()
        result=qwen.prepare_edition(path,2)
        self.assertEqual(result['story'],source['story'])
        self.assertEqual(result['production'],source['production'])
        for spec in fixtures.story.asset_specs(result):
            self.assertEqual(fixtures.storage.valid_asset(result,spec),spec['kind']!='scene')
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(qwen.prepare_edition(path,2),result,'Reopening must resume the same edition.')
        spec=next(s for s in fixtures.story.asset_specs(result) if s['kind']=='character')
        fixtures.storage.asset_path(result,spec['name']).write_bytes(b'altered')
        with self.assertRaisesRegex(ValueError,'pixels/metadata changed'):
            fixtures.storage.valid_asset(result,spec)

    def test_reference_adoption_rejects_changed_design_and_source_approval(self):
        source,path=self.source_fixture();result=qwen.prepare_edition(path,2)
        spec=next(s for s in fixtures.story.asset_specs(result) if s['kind']=='character')
        result['production']['characters'][0]['appearance']='Different species'
        with self.assertRaisesRegex(ValueError,'another book/design'):
            fixtures.storage.valid_asset(result,spec)
        result['production']=copy.deepcopy(source['production'])
        old=next(s for s in fixtures.story.asset_specs(source) if s['name']==spec['name'])
        approval=fixtures.storage.approval_path(source,old)
        approval.unlink()
        with self.assertRaises(ValueError):fixtures.storage.valid_asset(result,spec)

    def test_review_session_unloads_on_exception_and_resets_context(self):
        self.project['render_settings']['review_session_policy']=1
        with patch('urllib.request.urlopen') as opened:
            with self.assertRaisesRegex(RuntimeError,'interrupted'):
                with session.phase(self.project,self.output):
                    session.current.get()['models'].add(('http://local','gemma4:31b'))
                    raise RuntimeError('interrupted')
        self.assertIsNone(session.current.get())
        payload=json.loads(opened.call_args.args[0].data)
        self.assertEqual(payload,{'model':'gemma4:31b','keep_alive':0})

    def test_preview_actor_veto_cannot_be_cleared_by_other_passes(self):
        report={'checks':{'scene_matches':True},'issues':[],'uncertain':False}
        quality_preview.enforce_scene_event(report,{'story_event_visible':True,'uncertain':False,
            'explicit_actor_constraint_preserved':False,'character_agency_preserved':True,'essential_issues':[]})
        self.assertFalse(report['checks']['scene_matches'])

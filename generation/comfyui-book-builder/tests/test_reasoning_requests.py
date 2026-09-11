import copy, importlib, io, json, sys, types, unittest
from unittest.mock import Mock, patch
import test_book as fixtures
import test_quality

nodes=importlib.import_module('book_test_pack.nodes')
quality=importlib.import_module('book_test_pack.quality')
planning=importlib.import_module('book_test_pack.planning')


class ReasoningRequestTests(unittest.TestCase):
    def fake_runtime(self):
        comfy=types.ModuleType('comfy');mm=types.ModuleType('comfy.model_management')
        mm.throw_exception_if_processing_interrupted=lambda:None
        mm.unload_all_models=lambda:None
        mm.soft_empty_cache=lambda:None
        comfy.model_management=mm
        return {'comfy':comfy,'comfy.model_management':mm}

    def capture_http(self,requests):
        def respond(request,**kwargs):
            data=json.loads(request.data);requests.append(data)
            if 'messages' not in data:return io.BytesIO(b'{}')
            chunks=[{'message':{'thinking':'private reasoning'}},
                    {'message':{'content':'{"result":"ok"}'},'done':True,'done_reason':'stop'}]
            return io.BytesIO(b'\n'.join(json.dumps(c).encode() for c in chunks))
        return respond

    def test_actual_writer_request_enables_gemma_and_qwen_and_keeps_only_answer(self):
        for name,expected in [('gemma4:31b',True),('qwen3.5:27b',True),('other-model',False)]:
            calls=[]
            with self.subTest(model=name),patch.dict(sys.modules,self.fake_runtime()), \
                 patch.object(nodes.urllib.request,'urlopen',side_effect=self.capture_http(calls)):
                result=nodes._ollama_generate_once('http://local.invalid',name,'Write a story',{},123)
            self.assertEqual(result,'{"result":"ok"}')
            self.assertIs(calls[0]['think'],expected)
            self.assertEqual(calls[0]['options']['num_predict'],24576)
            self.assertEqual(calls[-1]['keep_alive'],0)

    def test_actual_review_http_payload_keeps_thinking_enabled(self):
        calls=[]
        schema={'type':'object','properties':{'result':{'type':'string'}},'required':['result']}
        with patch.dict(sys.modules,self.fake_runtime()), \
             patch.object(quality.urllib.request,'urlopen',side_effect=self.capture_http(calls)):
            result=quality.json_model('http://local.invalid','gemma4:31b','Review',schema,think=True,num_predict=8192)
        self.assertEqual(result,{'result':'ok'})
        self.assertIs(calls[0]['think'],True)
        self.assertEqual(calls[0]['options']['num_predict'],8192)

    def test_production_story_broad_page_and_continuity_calls_all_request_reasoning(self):
        package=fixtures.package_fixture();before=copy.deepcopy(package)
        names={c['name']:c['id'] for c in package['production']['characters']}
        broad={'checks':{k:True for k in quality.TEXT_CHECKS},'issues':[],'evidence':'Fixture','uncertain':False}
        pages=[{'pageNumber':p['pageNumber'],'checks':{'moment_matches':True},'issues':[],
                'evidence':'Fixture','uncertain':False,
                'illustrated_figures':[{'description':n,'cast_id':names[n],'is_character':True} for n in p['charactersPresent']]}
               for p in package['story']['pages']]
        continuity=test_quality.QualityTests.continuity_fixture(self,package['story'])
        generate=Mock(side_effect=[broad,{'pages':pages},continuity])
        result=quality.review_story(package,{'age_range':'4-6','story_idea':'test','ollama_url':'http://local.invalid',
                                           'review_model':'gemma4:31b'},generate=generate)
        self.assertTrue(result['accepted']);self.assertEqual(package,before)
        self.assertEqual(generate.call_count,3)
        for call in generate.call_args_list:
            self.assertIs(call.kwargs['think'],True)
            self.assertEqual(call.kwargs['num_predict'],8192)

    def test_actual_outline_review_path_requests_reasoning(self):
        generate=Mock(return_value={'checks':{'causal_plot':True},'uncertain':False,'issues':[]})
        result=planning.review_outline({'title':'Test'}, {'age_range':'4-6','story_idea':'test',
            'ollama_url':'http://local.invalid','review_model':'gemma4:31b'},generate=generate)
        self.assertTrue(result['accepted'])
        self.assertIs(generate.call_args.kwargs['think'],True)

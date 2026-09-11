import importlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_book

writer=importlib.import_module('book_test_pack.assisted_writer')


class AssistedWriterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)
        self.config={'ollama_model':'gemma4:31b','ollama_url':'http://local.invalid'}
        self.schema={'type':'object','properties':{'prompt':{'type':'string'}},'required':['prompt']}
        self.calls=[]

    def call(self):
        return writer.complete_json(self.path,self.config,'Write JSON',self.schema,731003,8192,lambda:None)

    def transport(self,replies):
        def send(request,**kwargs):
            payload=json.loads(request.data)
            if request.full_url.endswith('/api/generate'):return io.BytesIO(b'{}')
            self.calls.append(payload)
            return io.BytesIO(json.dumps(replies[len(self.calls)-1]).encode())
        return patch('urllib.request.urlopen',side_effect=send)

    def test_gemma_keeps_reasoning_without_ollama_grammar_restart(self):
        response={'done':True,'done_reason':'stop','message':{'content':'{"prompt":"A complete scene."}'}}
        with self.transport([response]):self.assertEqual(self.call(),{'prompt':'A complete scene.'})
        self.assertTrue(self.calls[0]['think'])
        self.assertNotIn('format',self.calls[0])
        self.assertIn(json.dumps(self.schema,separators=(',',':')),self.calls[0]['messages'][0]['content'])
        self.assertEqual(self.calls[0]['options']['seed'],731003)
        with patch('urllib.request.urlopen',side_effect=AssertionError('Completed replies must be reused')):
            self.assertEqual(self.call(),{'prompt':'A complete scene.'})

    def test_partial_done_false_reply_is_preserved_and_recovered_once(self):
        partial={'done':False,'message':{'content':'{"prompt":"unfinished'}}
        good={'done':True,'done_reason':'stop','message':{'content':'```json\n{"prompt":"Recovered."}\n```'}}
        with self.transport([partial,good]):self.assertEqual(self.call(),{'prompt':'Recovered.'})
        self.assertEqual(len(self.calls),2)
        self.assertEqual(json.loads((self.path/'ollama-response.json').read_text()),partial)
        self.assertTrue((self.path/'text-recovery-1/request.json').exists())
        self.assertEqual(json.loads((self.path/'writer-status.json').read_text())['call'],2)

    def test_invalid_json_and_token_exhaustion_never_become_candidate(self):
        for replies in ([{'done':True,'message':{'content':'broken'}}]*2,
                        [{'done':True,'done_reason':'length','message':{'content':'{}'}}]*2):
            with self.subTest(replies=replies),tempfile.TemporaryDirectory() as directory:
                self.path=Path(directory);self.calls=[]
                with self.transport(replies),self.assertRaisesRegex(RuntimeError,'two saved requests'):self.call()
                self.assertFalse((self.path/'response.txt').exists())
                with patch('urllib.request.urlopen',return_value=io.BytesIO(b'{}')) as transport:
                    with self.assertRaisesRegex(RuntimeError,'two saved requests'):self.call()
                    # Reopening an exhausted attempt reads its receipts; only unload is sent.
                    self.assertEqual(transport.call_count,1)

    def test_interruption_does_not_trigger_automatic_recovery(self):
        def cancelled():raise RuntimeError('Interrupted by user')
        with patch('urllib.request.urlopen',return_value=io.BytesIO(b'{}')) as transport:
            with self.assertRaisesRegex(RuntimeError,'Interrupted by user'):
                writer.complete_json(self.path,self.config,'Write JSON',self.schema,731003,8192,cancelled)
            self.assertEqual(transport.call_count,1)  # unload only

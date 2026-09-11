"""ComfyUI entry and single-stage nodes for the assisted creator."""
import hashlib
import json
from pathlib import Path

from . import assisted_store as store
from . import assisted_engine as engine


class BookAssistedStart:
    @classmethod
    def INPUT_TYPES(cls):
        from .story_craft import DEFAULT_AGE, FLAVOURS, LANGUAGE, ART
        return {'required': {'story_idea':('STRING',{'multiline':True,'default':''}),
                             'page_count':('INT',{'default':12,'min':2,'max':24}),
                             'age_range':('STRING',{'default':DEFAULT_AGE}),
                             'max_characters':('INT',{'default':3,'min':1,'max':6}),
                             'art_style':('STRING',{'multiline':True,'default':''}),
                             'seed':('INT',{'default':0,'min':0,'max':2**53-1})},
                'optional': {'story_flavour':(list(FLAVOURS),), 'read_aloud':(list(LANGUAGE),),
                             'art_preset':(list(ART),)}}
    RETURN_TYPES=('STRING',)
    RETURN_NAMES=('creator_url',)
    FUNCTION='start'
    CATEGORY='Book Builder/Assisted'
    OUTPUT_NODE=True
    @classmethod
    def IS_CHANGED(cls,**kwargs):
        return float('nan')
    def start(self,**values):
        from .assisted_web import launch
        from server import PromptServer
        state=store.create(values)
        from .runtime import settings
        url=f"{settings()['comfy_url']}/book-builder/create/{state['id']}"
        PromptServer.instance.loop.call_soon_threadsafe(launch,state['id'])
        return {'ui':{'text':[url]},'result':(url,)}


class BookAssistedStep:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'session_id':('STRING',),'stage_id':('STRING',),'attempt':('INT',{'min':1})}}
    RETURN_TYPES=('STRING',)
    FUNCTION='run'
    CATEGORY='Book Builder/Assisted'
    OUTPUT_NODE=True
    @classmethod
    def IS_CHANGED(cls,**kwargs):
        return float('nan')
    def run(self,session_id,stage_id,attempt):
        state=store.read(session_id)
        current=store.stage(state,stage_id)
        done=next((c for c in current['candidates'] if c['attempt']==attempt),None)
        if done:
            engine.store.candidate_path(state,done)
            return (str(done['path']),)
        if state['current_stage']!=stage_id or current['status']=='approved':
            raise ValueError('This stage is no longer awaiting generation.')
        intent=json.loads((engine.directory(session_id,stage_id,attempt)/'intent.json').read_text())
        if engine.recover_candidate(state,intent):
            return (f'/book-builder/create/{session_id}',)
        if stage_id in ('story','plan'):
            engine.text_step(state,intent)
            return (f'/book-builder/create/{session_id}',)
        saved=engine.directory(session_id,stage_id,attempt)/'native.api.json'
        if saved.exists():
            graph=json.loads(saved.read_text())
            finals=[(nid,n) for nid,n in graph.items() if n.get('class_type')=='BookAssistedSaveCandidate']
            if len(finals)!=1 or any(finals[0][1]['inputs'].get(k)!=v for k,v in
                                     [('session_id',session_id),('stage_id',stage_id),('attempt',attempt)]):
                raise ValueError('Saved native graph does not match this attempt.')
            from .storage import write_json
            write_json(saved.parent/'generation.json',json.loads(finals[0][1]['inputs']['metadata']))
            return {'result':([finals[0][0],0],),'expand':graph}
        return engine.image_graph(state,intent)


class BookAssistedReference:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'session_id':('STRING',),'path':('STRING',),'sha256':('STRING',)}}
    RETURN_TYPES=('IMAGE',)
    FUNCTION='load'
    CATEGORY='Book Builder/Assisted'
    def load(self,session_id,path,sha256):
        import numpy as np
        import torch
        from PIL import Image
        file=(store.root(session_id)/path).resolve()
        if not file.is_relative_to(store.root(session_id).resolve()):
            raise ValueError('Reference path leaves this book.')
        if hashlib.sha256(file.read_bytes()).hexdigest()!=sha256:
            raise ValueError('Reference changed after the graph was saved.')
        with Image.open(file) as im:
            array=np.asarray(im.convert('RGB'),dtype=np.float32)/255.0
        return (torch.from_numpy(array)[None,...],)


class BookAssistedSaveCandidate:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'session_id':('STRING',),'stage_id':('STRING',),'attempt':('INT',{'min':1}),
                            'metadata':('STRING',),'images':('IMAGE',)},'hidden':{'prompt':'PROMPT'}}
    RETURN_TYPES=('STRING',)
    FUNCTION='save'
    CATEGORY='Book Builder/Assisted'
    OUTPUT_NODE=True
    def save(self,session_id,stage_id,attempt,metadata,images,prompt=None):
        path=engine.save_image(session_id,stage_id,attempt,images,metadata,prompt)
        from .storage import output_image_record
        return {'ui':{'images':[output_image_record(path)]},'result':(str(path),)}


CLASSES=(BookAssistedStart,BookAssistedStep,BookAssistedReference,BookAssistedSaveCandidate)

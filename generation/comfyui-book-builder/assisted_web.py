"""Local UI routes and crash-aware MCP coordination, one job per review stage."""
import asyncio
import json
from pathlib import Path
import sys
import traceback
import jsonschema
from aiohttp import web, ClientSession

from . import assisted_store as store
from . import assisted_engine as engine
from .storage import write_json
from .runtime import generation_root, settings

ACTIVE={}
BASE=generation_root()
STATIC=Path(__file__).parent/'assisted_ui'


async def mcp(name,args):
    process=await asyncio.create_subprocess_exec(settings()['mcp_python'],str(BASE/'mcp/call.py'),name,
        json.dumps(args),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,cwd=str(BASE))
    try:
        stdout,stderr=await asyncio.wait_for(process.communicate(),200)
    except asyncio.TimeoutError:
        process.kill();await process.wait()
        raise RuntimeError('MCP response timed out. Resume checks saved jobs before submitting again.')
    if process.returncode:
        raise RuntimeError(stderr.decode(errors='replace')[-2000:])
    envelope=json.loads(stdout)
    if envelope.get('isError'):
        raise RuntimeError(str(envelope))
    return envelope.get('structuredContent') or json.loads(next(c['text'] for c in envelope['content'] if c['type']=='text'))


async def live(path):
    async with ClientSession() as client:
        async with client.get(settings()['comfy_url']+path,timeout=20) as response:
            response.raise_for_status();return await response.json()


def matches(graph,intent):
    return any(n.get('class_type')=='BookAssistedStep' and all(n.get('inputs',{}).get(k)==intent[k]
               for k in ('session_id','stage_id','attempt')) for n in graph.values() if isinstance(n,dict))


async def locate(intent):
    queue=await live('/queue')
    for entry in queue.get('queue_running',[])+queue.get('queue_pending',[]):
        if matches(entry[2],intent):
            return entry[1],'active'
    history=await live('/history?max_items=200')
    for pid,entry in history.items():
        if matches(entry.get('prompt',[None,None,{}])[2],intent):
            return pid,'completed' if entry.get('status',{}).get('status_str')=='success' else 'failed'
    return None,None


def same_job(state,intent):
    return state.get('job') and all(state['job'].get(k)==intent[k] for k in ('stage_id','attempt'))


async def drive(sid,resume=False):
    intent=None
    try:
        with store.LOCK:
            state=store.read(sid)
            if state['status']=='exporting':
                engine.export_session(state);return
            if state['status'] in ('awaiting_review','complete'):
                return
            intent=state.get('job')
            if not intent:
                if state['status']!='ready':
                    return
                intent=store.next_attempt(state)
            path=engine.directory(sid,intent['stage_id'],intent['attempt'])
            graph={'step':{'class_type':'BookAssistedStep','inputs':{k:intent[k] for k in ('session_id','stage_id','attempt')}}}
            write_json(path/'workflow.api.json',graph)
        # Existing outputs take precedence over a lost CLI receipt or restart.
        if engine.recover_candidate(store.read(sid),intent):
            return
        await mcp('server_info',{})
        pid,status=await locate(intent)
        if status in ('completed','failed'):
            raise RuntimeError('The saved job ended without a valid candidate. Inspect its error or regenerate this stage.')
        if not pid:
            if (path/'submission-started.json').exists() and not resume:
                raise RuntimeError('A submission receipt is missing. Use Resume to reconcile the saved job.')
            validation=await mcp('validate_workflow',{'workflow_path':str(path/'workflow.api.json')})
            write_json(path/'validation.json',validation)
            if validation.get('valid') is not True:
                raise ValueError('ComfyUI rejected this stage graph: '+json.dumps(validation))
            write_json(path/'submission-started.json',{'intent':{k:intent[k] for k in ('session_id','stage_id','attempt')}})
            receipt=await mcp('run_workflow',{'workflow_path':str(path/'workflow.api.json'),'wait':False})
            write_json(path/f"submission-{store.now().replace(':','-')}.json",receipt)
            pid=receipt.get('prompt_id') or receipt.get('data',{}).get('prompt_id')
            if not pid:
                pid,_=await locate(intent)
            if not pid:
                raise RuntimeError('Submission returned no prompt ID. Resume will check the queue before retrying.')
        with store.LOCK:
            state=store.read(sid)
            if same_job(state,intent):
                state['job']['prompt_id']=pid
                if state['status']!='awaiting_review':state['status']='generating'
                store.save(state)
        while True:
            await asyncio.sleep(2)
            state=store.read(sid)
            if not same_job(state,intent) or state['status']=='awaiting_review':
                return
            history=await live('/history/'+pid)
            if pid in history:
                write_json(path/'history.json',history[pid])
                status=history[pid].get('status',{})
                if status.get('completed') or status.get('status_str')=='error':
                    errors=[m[1].get('exception_message','') for m in status.get('messages',[]) if m[0]=='execution_error']
                    raise RuntimeError('This attempt stopped: '+(' '.join(errors) or 'No candidate was saved. You can regenerate or resume.'))
            queue=await live('/queue')
            if not any(e[1]==pid for e in queue.get('queue_running',[])+queue.get('queue_pending',[])):
                # Candidate saving can race this snapshot; re-read before declaring failure.
                if store.read(sid)['status']=='awaiting_review':return
                raise RuntimeError('The job is no longer in ComfyUI. Use Resume to recover this saved step.')
    except Exception as exc:
        with store.LOCK:
            state=store.read(sid)
            if intent is None or same_job(state,intent):
                if state['status'] not in ('awaiting_review','complete'):
                    state.update(status='error',error=str(exc));state['revision']+=1;store.save(state)
        traceback.print_exc()


def launch(sid,resume=False):
    # An old monitor may still be unwinding after a human decision. Its identity
    # differs from the next intent and it cannot mutate the next stage.
    with store.LOCK:
        state=store.read(sid)
        if state['status'] in ('awaiting_review','complete'):
            return
        if not state.get('job') and state['status']=='ready':
            # Allocate before yielding: Resume must see the same immutable intent.
            store.next_attempt(state)
        key=(sid,state['current_stage'],state['job']['attempt'] if state.get('job') else 'export')
        if key not in ACTIVE or ACTIVE[key].done():
            task=asyncio.create_task(drive(sid,resume));ACTIVE[key]=task
            def release(finished):
                if ACTIVE.get(key) is finished:
                    ACTIVE.pop(key,None)
            task.add_done_callback(release)


def public_state(state):
    # All source paths here belong to this session. Expose URLs, not arbitrary files.
    state=json.loads(json.dumps(state))
    state['creator_url']=store.creator_url(state['id'])
    state['can_revise_pages']=True
    for stage in state['stages']:
        for candidate in stage['candidates']:
            if stage['id']==state['current_stage'] and stage['kind'] in ('story','plan'):
                # Validation is a derived view, not a human decision. Recheck the
                # unchanged draft after validator fixes; retain its original report.
                info=candidate['metadata']
                info['validation_error_at_generation']=info.get('validation_error')
                try:
                    content=json.loads(store.candidate_path(state,candidate).read_text())
                    if stage['kind']=='story':
                        from .assisted_story import validate as validate_assisted_story
                        validate_assisted_story(content,state['config'])
                        if state['config'].get('story_craft_version'):
                            from .story_craft import review_guide
                            info['story_guide']=review_guide(content,state['config'])
                    else:
                        from .assisted_plan import validate
                        validate(engine.package(state),content)
                    info['validation_error']=None
                except (ValueError,KeyError,OSError,jsonschema.ValidationError) as exc:
                    info['validation_error']=str(exc)
            candidate['url']=f"/book-builder/books/{state['id']}/{candidate['path']}"
            for ref in candidate['metadata'].get('reference_images',[]):
                ref['url']=f"/book-builder/books/{state['id']}/{ref['path']}"
    return state


async def payload(request):
    origin=request.headers.get('Origin')
    if origin and origin!=f'{request.scheme}://{request.host}':
        raise web.HTTPForbidden(text='Cross-origin changes are not allowed.')
    if request.headers.get('X-Book-Creator')!='1' or request.content_type!='application/json':
        raise web.HTTPForbidden(text='Use the book creator to make changes.')
    if request.content_length and request.content_length>500000:
        raise web.HTTPRequestEntityTooLarge(max_size=500000,actual_size=request.content_length)
    data=await request.json()
    if not isinstance(data,dict):raise ValueError('Expected a JSON object.')
    return data


async def api(request):
    try:
        sid=request.match_info.get('sid')
        if request.method=='GET':
            return web.json_response(public_state(store.read(sid)) if sid else store.listing(),headers={'Cache-Control':'no-store'})
        data=await payload(request)
        if sid and data.get('action') in ('reopen','keep_original'):
            pending=store.read(sid)
            store.expect_revision(pending,data.get('revision'))
            if pending['status']=='error' and pending.get('job'):
                # A lost MCP receipt can mark a still-running render as an error.
                # Never park its intent while ComfyUI could still save the result.
                _,job_status=await locate(pending['job'])
                if job_status=='active':
                    raise store.Conflict('This saved job is still running in ComfyUI. Wait for it to finish before changing pages.')
        with store.LOCK:
            if not sid:
                state=store.create(data);sid=state['id']
            else:
                state=store.read(sid);sid=state['id'];store.expect_revision(state,data.get('revision'))
                action=data.get('action');current=store.stage(state)
                feedback=str(data.get('feedback','')).strip()
                override=str(data.get('prompt_override','')).strip()
                if len(feedback)>5000 or len(override)>6000:raise ValueError('Please keep feedback and prompts under 5,000 / 6,000 characters.')
                if action=='reopen':
                    from .assisted_revision import begin
                    stage_id=data.get('stage_id')
                    if not isinstance(stage_id,str) or not stage_id:
                        raise ValueError('Choose the approved page to revise.')
                    state=begin(state,stage_id)
                elif action=='keep_original':
                    from .assisted_revision import keep_original
                    state=keep_original(state)
                elif action=='resume':
                    if state['status'] not in ('error','queued','generating','ready','exporting'):
                        raise store.Conflict('There is nothing to resume at this step.')
                    # The explicit request allows repeating an interrupted step ONLY
                    # after drive() checks saved candidates, live queue and history.
                elif action in ('approve','regenerate','edit','save_draft'):
                    if state['status'] not in ('awaiting_review','error','ready'):
                        raise store.Conflict('Wait for this generation to finish before deciding.')
                    candidate=next((c for c in current['candidates'] if c['id']==data.get('candidate_id')),None)
                    if current['candidates'] and not candidate:
                        raise ValueError('Select a saved candidate so feedback is attached to the right attempt.')
                    if action in ('approve','edit','save_draft') and not candidate:
                        raise ValueError('Choose the exact candidate to review.')
                    if candidate:store.candidate_path(state,candidate)
                    if action=='approve':
                        record=store.decision(state,candidate,'approve',feedback)
                        state=engine.advance(state,candidate,record)
                    elif action=='save_draft':
                        if current['kind'] not in ('story','plan'):raise ValueError('Only text drafts can be edited as JSON.')
                        from . import assisted_plan
                        from .assisted_story import validate as validate_assisted_story
                        content=data['content']
                        if current['kind']=='story':validate_assisted_story(content,state['config'])
                        else:assisted_plan.validate(engine.package(state),content)
                        store.decision(state,candidate,'revise_text',feedback)
                        intent=store.next_attempt(state,feedback)
                        file=engine.directory(sid,current['id'],intent['attempt'])/'candidate.json';write_json(file,content)
                        state=store.record_candidate(sid,current['id'],intent['attempt'],file,{'method':'human_text_revision','content':content})
                    else:
                        if action=='edit' and (current['kind'] in ('story','plan') or not feedback and not override):
                            raise ValueError('Describe the image edit you want.')
                        if candidate:store.decision(state,candidate,'reject' if action=='regenerate' else 'request_edit',feedback)
                        intent=store.next_attempt(state,feedback,mode='edit' if action=='edit' else 'fresh',
                                                  source_candidate=candidate['id'] if candidate else None,prompt_override=override)
                        state=store.read(sid)
                else:raise ValueError('Unknown creator action.')
        if (data.get('action') not in ('reopen','keep_original')
                and state['status'] not in ('awaiting_review','complete')
                and (state['status']!='error' or data.get('action')=='resume')):
            launch(sid,resume=data.get('action')=='resume')
        return web.json_response(public_state(store.read(sid)),headers={'Cache-Control':'no-store'})
    except store.Conflict as exc:return web.json_response({'error':str(exc)},status=409)
    except (ValueError,KeyError,StopIteration,jsonschema.ValidationError) as exc:return web.json_response({'error':str(exc)},status=400)
    except FileNotFoundError:return web.json_response({'error':'This saved book or candidate was not found.'},status=404)


def register():
    from server import PromptServer
    async def page(request):return web.FileResponse(STATIC/'index.html',headers={'Cache-Control':'no-store'})
    async def static(request):
        name=request.match_info['name']
        if name not in ('creator.js','creator.css'):raise web.HTTPNotFound()
        return web.FileResponse(STATIC/name,headers={'Cache-Control':'no-store'})
    routes=PromptServer.instance.routes
    routes.get('/book-builder/create')(page)
    routes.get('/book-builder/create/{sid}')(page)
    routes.get('/book-builder/creator/static/{name}')(static)
    routes.get('/book-builder/creator/api')(api)
    routes.post('/book-builder/creator/api')(api)
    routes.get('/book-builder/creator/api/{sid}')(api)
    routes.post('/book-builder/creator/api/{sid}')(api)

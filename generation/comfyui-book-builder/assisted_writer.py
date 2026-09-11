"""Complete, persisted local text replies with bounded transport/JSON recovery."""
import json
import urllib.request

from .preview import atomic_view
from .quality import parse_model_json
from .storage import write_exclusive, write_json

MAX_CALLS = 2


def payload_for(config, prompt, schema, seed, tokens):
    payload = {'model': config['ollama_model'], 'messages': [{'role':'user','content':prompt}],
               'stream':False, 'think':True, 'keep_alive':0,
               'options':{'seed':seed % (2**31),'temperature':0.7,'num_ctx':32768,'num_predict':tokens}}
    if config['ollama_model'].split(':')[0].lower() == 'gemma4':
        # Ollama 0.30.8 restarts a thinking completion to enable its grammar.
        # The saved failing Gemma reply ended with done:false after that restart.
        # Keep reasoning, request JSON in the prompt, validate locally afterwards.
        payload['messages'][0]['content'] += '\nRequired output JSON schema:\n'+json.dumps(schema,separators=(',',':'))
    else:
        payload['format'] = schema
    return payload


def complete_json(directory, config, prompt, schema, seed, tokens, check_interrupt):
    raw = directory/'response.txt'
    if raw.exists():
        return parse_model_json(raw.read_text())
    request_file=directory/'request.json'
    if request_file.exists():
        payload=json.loads(request_file.read_text())['payload']
    else:
        payload=payload_for(config,prompt,schema,seed,tokens)
        write_json(request_file,{'model':config['ollama_model'],'prompt':prompt,'schema':schema,
            'seed':seed,'thinking':True,'payload':payload,'writer_version':2})
    endpoint=config['ollama_url'].rstrip('/')
    errors=[]
    try:
        for index in range(MAX_CALLS):
            check_interrupt()
            call_dir=directory if index==0 else directory/f'text-recovery-{index}'
            call_dir.mkdir(parents=True,exist_ok=True)
            if index:
                # Technical recovery stays within this human-requested attempt.
                # Never concatenate a broken partial story onto a new response.
                payload=payload_for(config,prompt,schema,seed,tokens)
                payload['messages'][0]['content'] += ('\nThe previous response ended before producing valid JSON. '
                    'Return a complete document from its beginning through its closing brace. '
                    'Keep the story concise and include every requested page.')
                write_json(call_dir/'request.json',{'payload':payload,'recovery_reason':errors[-1]})
            status={'call':index+1,'max_calls':MAX_CALLS,'status':'writing','prior_errors':errors}
            atomic_view(directory/'writer-status.json',(json.dumps(status,indent=2)+'\n').encode())
            response_file=call_dir/'ollama-response.json'
            try:
                if not response_file.exists():
                    request=urllib.request.Request(endpoint+'/api/chat',json.dumps(payload).encode(),
                                                   {'Content-Type':'application/json'})
                    with urllib.request.urlopen(request,timeout=600) as response:
                        data=response.read(1000001)
                    if len(data)>1000000:raise ValueError('Text reply exceeded one megabyte.')
                    write_exclusive(response_file,data)
                result=json.loads(response_file.read_text())
                content=result.get('message',{}).get('content','')
                if content:
                    write_exclusive(call_dir/'received-content.txt',content.encode())
                if result.get('done') is not True or result.get('done_reason') in ('length','connection_closed'):
                    raise ValueError('The local writer stopped before finishing (done='+str(result.get('done'))+
                                     ', reason='+str(result.get('done_reason'))+').')
                value=parse_model_json(content)
                if not isinstance(value,dict):raise ValueError('The writer must return one JSON object.')
                check_interrupt()
                write_exclusive(raw,content.encode())
                status.update(status='complete',response=str(response_file.relative_to(directory)))
                atomic_view(directory/'writer-status.json',(json.dumps(status,indent=2)+'\n').encode())
                return value
            except (OSError,ValueError,KeyError) as exc:
                # Processing interruptions deliberately propagate without retry.
                check_interrupt()
                errors.append(str(exc))
                if not (call_dir/'error.json').exists():write_json(call_dir/'error.json',{'error':str(exc)})
        atomic_view(directory/'writer-status.json',(json.dumps({'status':'error','errors':errors,
                    'call':MAX_CALLS,'max_calls':MAX_CALLS},indent=2)+'\n').encode())
        raise RuntimeError('The local writer could not finish a valid JSON draft after two saved requests. '
                           'All replies are preserved. Regenerate this step to try again. '+errors[-1])
    finally:
        request=urllib.request.Request(endpoint+'/api/generate',json.dumps({'model':payload['model'],
            'keep_alive':0}).encode(),{'Content-Type':'application/json'})
        try:urllib.request.urlopen(request,timeout=15).close()
        except OSError:pass

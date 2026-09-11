#!/usr/bin/env python3
"""Start the local book creator from this project, reusing the existing ComfyUI."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import urllib.request

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('book_runtime',ROOT/'comfyui-book-builder/runtime.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)


def check(config):
    comfy=Path(config['comfyui'])
    for key in ('python','mcp_python','mcp_server','comfy_bin'):
        if not Path(config[key]).is_file():raise RuntimeError(f'Missing {key}: {config[key]}')
    links={comfy/'custom_nodes/comfyui-book-builder': ROOT/'comfyui-book-builder',
           comfy/'output/books':ROOT/'output/books',
           comfy/'output/codex/books':ROOT/'output/codex/books',
           comfy/'user/default/workflows/childrens-book-generator-v2-assisted.json':
               ROOT/'comfyui/workflows/childrens-book-generator-v2-assisted.json'}
    for path,target in links.items():
        if not path.exists() or path.resolve()!=target.resolve():
            raise RuntimeError(f'Expected the Comfy link {path} -> {target}. See README.md setup instructions.')


def online(config):
    try:
        with urllib.request.urlopen(config['comfy_url']+'/book-builder/creator/api',timeout=2) as response:
            return response.status==200 and isinstance(json.load(response),list)
    except (OSError,ValueError):return False


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',nargs='?',default='start',choices=('start','status','check'))
    args=parser.parse_args();config=runtime.settings();check(config)
    if args.command=='check':print('Source, output links, workflow and local MCP installation are ready.');return
    if args.command=='status':
        print('Book Creator is running.' if online(config) else 'Book Creator is stopped.');return
    if not online(config):
        # Never start a second Comfy process on a port used by another service.
        import socket
        from urllib.parse import urlparse
        url=urlparse(config['comfy_url']);host=url.hostname or '127.0.0.1';port=url.port or 8188
        with socket.socket() as sock:
            sock.settimeout(1)
            if sock.connect_ex((host,port))==0:
                raise RuntimeError('The port is already in use but the creator is unavailable. Inspect the existing server before restarting it.')
        local=ROOT/'.local';local.mkdir(exist_ok=True)
        with (local/'comfyui.log').open('ab') as log:
            process=subprocess.Popen([config['python'],'main.py','--listen',host,'--port',str(port)],
                cwd=config['comfyui'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        (local/'server.json').write_text(json.dumps({'pid':process.pid,'started_at':time.time(),
            'command':[config['python'],'main.py','--listen',host,'--port',str(port)],
            'cwd':config['comfyui'],'log':str(local/'comfyui.log')},indent=2)+'\n')
        for _ in range(50):
            if online(config):break
            if process.poll() is not None:raise RuntimeError('ComfyUI stopped during startup. See .local/comfyui.log.')
            time.sleep(1)
        else:raise RuntimeError('ComfyUI is still starting; check .local/comfyui.log and run status. Do not start another process.')
    print(config['comfy_url']+'/book-builder/create')
    print('Books and all review decisions are saved in '+str(ROOT/'output/books'))


if __name__=='__main__':main()

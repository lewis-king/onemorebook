"""Call the pinned official local MCP using its own Python environment."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

spec = importlib.util.spec_from_file_location('book_runtime', Path(__file__).resolve().parents[1]/'comfyui-book-builder/runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


async def main():
    name, args = sys.argv[1], json.loads(sys.argv[2] if len(sys.argv)>2 else '{}')
    config = runtime.settings()
    env = dict(os.environ, COMFY_BIN=config['comfy_bin'], COMFY_LOCAL_URL=config['comfy_url'],
               COMFYUI_URL='', COMFYUI_HOST='', DO_NOT_TRACK='1', COMFY_NO_TELEMETRY='1')
    params = StdioServerParameters(command=config['mcp_server'], cwd=config['comfyui'], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=180) as session:
            await session.initialize()
            result = await session.call_tool(name, args)
            print(result.model_dump_json(by_alias=True, exclude_none=True))


if __name__ == '__main__':
    asyncio.run(main())

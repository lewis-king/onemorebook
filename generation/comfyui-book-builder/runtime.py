"""Local rendering installation; book source/data live in onemorebook/generation."""
import json
from pathlib import Path


def generation_root():
    return Path(__file__).resolve().parent.parent


def settings():
    base = Path.home() / 'comfy'
    config = {
        'comfyui': str(base / 'ComfyUI'),
        'python': str(base / 'comfy-env/bin/python'),
        'mcp_python': str(base / 'mcp/official-env/bin/python'),
        'mcp_server': str(base / 'mcp/official-env/bin/comfy-mcp'),
        'comfy_bin': str(base / 'mcp/bin/comfy'),
        'comfy_url': 'http://127.0.0.1:8188',
    }
    file = generation_root() / 'comfy.local.json'
    if file.exists():
        overrides = json.loads(file.read_text())
        unknown = set(overrides) - set(config)
        if unknown:
            raise ValueError(f'Unknown local Comfy settings: {sorted(unknown)}')
        config.update(overrides)
    for key in ('comfyui','python','mcp_python','mcp_server','comfy_bin'):
        config[key] = str(Path(config[key]).expanduser().absolute())
    config['comfy_url'] = config['comfy_url'].rstrip('/')
    return config

"""One-time, byte-verified migration; old paths remain compatibility symlinks."""
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[1]
COMFY = Path.home() / 'comfy'
RECORD = ROOT / '.local/migration-20260911'


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}


def main():
    RECORD.mkdir(parents=True, exist_ok=True)
    if (RECORD / 'complete.json').exists():
        raise SystemExit('Migration already completed. See .local/migration-20260911/complete.json.')
    moves = [
        (COMFY / 'ComfyUI/custom_nodes/comfyui-book-builder', ROOT / 'comfyui-book-builder'),
        (COMFY / 'book-workflow-v2', ROOT / 'book-workflow-v2'),
        (COMFY / 'ComfyUI/output/books', ROOT / 'output/books'),
        (COMFY / 'ComfyUI/output/codex/books', ROOT / 'output/codex/books'),
        (COMFY / 'TASKS.md', ROOT / 'TASKS.md'),
    ]
    for source, dest in moves:
        if source.is_symlink() or not source.exists() or dest.exists():
            raise SystemExit(f'Unexpected source/destination; inspect before continuing: {source} -> {dest}')
    with tarfile.open(RECORD / 'source-before.tar.gz', 'x:gz') as archive:
        archive.add(moves[0][0], arcname='comfyui-book-builder')
    before = {str(source): hashes(source) if source.is_dir() else hashlib.sha256(source.read_bytes()).hexdigest()
              for source, _ in moves}
    (RECORD / 'before.json').write_text(json.dumps(before, indent=2)+'\n')
    for source, dest in moves:
        dest.parent.mkdir(parents=True, exist_ok=True)
        source.rename(dest)
        source.symlink_to(dest, target_is_directory=dest.is_dir())
        after = hashes(dest) if dest.is_dir() else hashlib.sha256(dest.read_bytes()).hexdigest()
        if after != before[str(source)]:
            raise RuntimeError(f'Migration verification failed: {dest}')
        print(f'Moved and verified {dest}', flush=True)
    library = COMFY / 'ComfyUI/user/default/workflows'
    workflow_dir = ROOT / 'comfyui/workflows'
    workflow_dir.mkdir(parents=True, exist_ok=True)
    originals = {}
    for source in sorted(library.glob('childrens-book*.json')):
        dest = workflow_dir / source.name
        if dest.exists():
            raise FileExistsError(dest)
        shutil.copy2(source, dest)
        originals[str(source)] = hashlib.sha256(source.read_bytes()).hexdigest()
    assisted = library / 'childrens-book-generator-v2-assisted.json'
    # Only the new assisted workflow is linked; all original library files stay put.
    if assisted.read_bytes() != (workflow_dir / assisted.name).read_bytes():
        raise RuntimeError('Assisted workflow copy differs')
    assisted.unlink()
    assisted.symlink_to(workflow_dir / assisted.name)
    contracts = ROOT / 'contracts'
    contracts.mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'book-workflow-v2/story.schema.json', contracts / 'story.schema.json')
    (RECORD / 'complete.json').write_text(json.dumps({
        'moves': [{'old': str(a), 'new': str(b)} for a,b in moves],
        'original_workflows_sha256': originals,
        'schema_sha256': hashlib.sha256((contracts/'story.schema.json').read_bytes()).hexdigest(),
        'all_moved_files_verified': True,
    }, indent=2)+'\n')


if __name__ == '__main__':
    main()

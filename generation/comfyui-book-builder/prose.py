"""Punctuate generated prose without changing its words, events or art contract."""
import copy
import json
import re

from .story import digest, object_schema
from .storage import write_json


def words(text):
    return re.findall(r"\w+(?:['’]\w+)*", text.replace('’', "'").casefold())


def punctuate_generated_prose(package, config, root, generate=None):
    from .quality import json_model
    generate = generate or json_model
    texts = [p['text'] for p in package['story']['pages']]
    key = digest(texts)
    directory = root/'quality/dialogue'/key[:16]
    schema = object_schema({'texts': {'type': 'array', 'minItems': len(texts), 'maxItems': len(texts),
                                    'items': {'type': 'string', 'minLength': 1}}})
    prompt = (
        'Copy-edit ONLY the punctuation of these children\'s book pages. Return texts in exactly the '
        'same order. Preserve EVERY WORD, including sound effects, character names, and their order. '
        'Do not rewrite, add or remove words. Add conventional quotation marks around direct speech '
        'and punctuate dialogue tags correctly. Keep narration outside speech marks. Use curly double '
        'quotation marks “like this” for speech, never Markdown. For example, This is loud, Mia said. '
        'becomes “This is loud,” Mia said. This example is not a page to include. '
        'Narration-only pages need no invented speech. Preserve existing correct punctuation.\nPages: '
        +json.dumps(texts, ensure_ascii=False))
    for attempt in (1, 2):
        path = directory/f'attempt-{attempt:02d}.json'
        if path.exists():
            record = json.loads(path.read_text())
            if record['source_hash'] != key or record['source_texts'] != texts:
                raise ValueError('Saved punctuation pass belongs to different prose.')
            result = record['result']
        else:
            result = generate(config['ollama_url'], config['review_model'], prompt, schema)
            write_json(path, {'source_hash': key, 'source_texts': texts, 'prompt': prompt,
                             'model': config['review_model'], 'result': result})
        errors = []
        if len(result.get('texts', [])) != len(texts):
            errors.append('Keep exactly one text entry per original page, in order.')
        else:
            for index, (before, after) in enumerate(zip(texts, result['texts']), 1):
                if not isinstance(after, str) or words(before) != words(after):
                    errors.append(f'Page {index}: only punctuation may change; preserve every word and its order.')
        if not errors:
            revised = copy.deepcopy(package)
            for page, text in zip(revised['story']['pages'], result['texts']):
                page['text'] = text
            return revised
        write_json(directory/f'attempt-{attempt:02d}-errors.json', {'issues': errors})
        prompt += '\nCorrect these copy-editing errors: '+json.dumps(errors)
    raise ValueError('Punctuation pass changed story words; no revised text was accepted. See '+str(directory))

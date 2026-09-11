"""Resolve draft length without changing the public story contract or saved inputs."""
from .story import book_schema, validate_package

AUTO_MIN = 8
AUTO_MAX = 16
AUTO_TARGET = 12


def page_bounds(config):
    count = config['page_count']
    if count:
        return count, count
    return config['page_count_min'], config['page_count_max']


def schema(config):
    low, high = page_bounds(config)
    result = book_schema(low, config['max_characters'])
    result['properties']['story']['properties']['pages']['maxItems'] = high
    return result


def validate(value, config):
    pages = value.get('story', {}).get('pages') if isinstance(value, dict) and isinstance(value.get('story'), dict) else None
    if not isinstance(pages, list):
        raise ValueError('The story must contain a pages array.')
    low, high = page_bounds(config)
    if not low <= len(pages) <= high:
        expected = str(low) if low == high else f'{low}–{high}'
        raise ValueError(f'This story needs {expected} pages; the draft has {len(pages)}.')
    # Still validate every public/private field, exact numbering, cast and prose.
    # Only the writer's allowed array length varies; the exported format is unchanged.
    return validate_package(value, len(pages), config['max_characters'])

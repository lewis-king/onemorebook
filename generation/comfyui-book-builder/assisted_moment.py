"""Generate a book from a real day: staged photo intake, writer brief and restyle guidance.

Moment books commemorate an actual day (a birthday, a holiday, a small adventure).
The reader uploads reference photographs with a caption each, plus a free description
of the day. The photographs are restyled into the book's illustration style and act
as scene references, while the captions and description carry their content into the
story text — the local writer works from words, never from pixels.
"""
import hashlib
from pathlib import Path

from .storage import books_root, write_exclusive

MAX_PHOTOS = 14
MAX_DESCRIPTION = 2000
MAX_CAPTION = 500
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

SOURCE_DIR = 'moment-src'
STAGED_DIR = 'moment-uploads'


def staged_path(upload_id):
    """Location of one validated upload awaiting session creation."""
    if not isinstance(upload_id, str) or not upload_id.isalnum() or len(upload_id) > 64:
        raise ValueError('Invalid upload reference.')
    return books_root() / STAGED_DIR / (upload_id + '.png')


def validate_submission(values):
    """Parse and validate the moment part of a create payload.

    Returns {'description': str, 'photos': [{'upload_id', 'caption'}]} with one
    entry per uploaded photograph, in form order. The files themselves are
    checked and moved into the session by intake_photos during store.create.
    """
    moment = values.get('moment')
    if not isinstance(moment, dict):
        raise ValueError('Moment details are missing.')
    description = str(moment.get('description', '')).strip()
    if not description:
        raise ValueError('Describe the day this book should remember.')
    if len(description) > MAX_DESCRIPTION:
        raise ValueError('Keep the description under 2,000 characters.')
    photos = moment.get('photos')
    if not isinstance(photos, list) or not 1 <= len(photos) <= MAX_PHOTOS:
        raise ValueError(f'Choose one to {MAX_PHOTOS} photographs.')
    result = []
    seen = set()
    for index, photo in enumerate(photos):
        if not isinstance(photo, dict):
            raise ValueError('Each photograph needs its caption.')
        upload_id = str(photo.get('upload_id', ''))
        caption = str(photo.get('caption', '')).strip()
        if upload_id in seen:
            raise ValueError('One photograph was added twice.')
        seen.add(upload_id)
        if not caption:
            raise ValueError(f'Give photograph {index + 1} a short caption.')
        if len(caption) > MAX_CAPTION:
            raise ValueError('Keep each caption under 500 characters.')
        staged = staged_path(upload_id)
        if not staged.is_file():
            raise ValueError('An uploaded photograph is missing. Upload it again.')
        result.append({'upload_id': upload_id, 'caption': caption})
    return {'description': description, 'photos': result}


def intake_photos(sid, submission):
    """Move staged uploads into the session and pin their hashes.

    Returns the immutable config entry: one record per photograph with its
    stable id, caption, session-relative path and SHA-256.
    """
    photos = []
    for index, photo in enumerate(submission['photos'], start=1):
        pid = f'moment_{index:02d}'
        source = staged_path(photo['upload_id'])
        data = source.read_bytes()
        target_rel = f'{SOURCE_DIR}/{pid}.png'
        write_exclusive(root_for(sid) / target_rel, data)
        source.unlink()
        photos.append({'id': pid, 'caption': photo['caption'],
                       'path': target_rel, 'sha256': hashlib.sha256(data).hexdigest()})
    return {'description': submission['description'], 'photos': photos}


def root_for(sid):
    from . import assisted_store as store
    return store.root(sid)


def writer_brief(moment):
    """The extra story-writer guidance for a moment book."""
    lines = ['This book celebrates a real day the reader lived. The finished book is a story-time '
             'souvenir of that day, so keep what actually happened recognisably at the heart of the '
             'story. Shape the day lightly into a picture-book arc (a want, small complications, a '
             'warm ending worth rereading); do not replace the real moments with unrelated fiction.',
             '', 'The day, in the grown-up\'s words:', moment['description'], '',
             'Photographs from the day, listed in the order they happened, with captions:']
    for index, photo in enumerate(moment['photos'], start=1):
        lines.append(f"{index}. {photo['caption']} (restyled illustration reference '{photo['id']}')")
    lines += ['', f'This book has exactly {len(moment["photos"])} pages — one per photograph, no more and no '
              'fewer, because it follows what actually happened. Page one recreates photograph 1, page two '
              'recreates photograph 2, and so on, in the order listed above. Do not invent extra beats or '
              'merge two photographs onto one page; if the day needs a little connective tissue, weave it '
              'into the page that belongs to. The cover is illustrated from the story as usual — keep the '
              'photographs on the numbered pages. Use the real people and their names as the cast, and '
              'describe each character\'s appearance so it matches what the captions say about them. The '
              'exact illustrations are prepared separately; your job is the words, faithful to the day.']
    return '\n'.join(lines)


def restyle_brief(photo, style=''):
    """Stage brief: turn one photograph's subjects into an isolated storybook reference.

    The photograph is the only image input — a scenic approved style sample passed
    alongside it kept donating its own content (rainbows, trees, its characters)
    into the memory, so the art style arrives as words instead. Like the character
    and prop references, the result shows just the subjects on a plain backdrop;
    the full scene is composed later at page time.
    """
    return ('Paint the main subjects of this photograph — the people, what they are doing, and the '
            "photograph's key objects — as a children's book illustration reference. The photograph "
            '(Image 1) is the only content guide: keep every face, pose, expression, outfit and object '
            'faithful and clearly recognisable, and keep every distinct object distinct — do not merge '
            'or duplicate repeated shapes. Present the subjects as the clear central focus on a plain, '
            'uncluttered warm-ivory storybook backdrop: do not recreate the photograph\'s background, '
            'setting or scenery here, because the full scene is composed later at page time. Render in '
            'this book\'s illustration style: ' + style + ' No photorealism, no text, lettering or '
            'watermark. '
            f"The grown-up's caption for this photograph: {photo['caption']}")


def plan_guidance(moment):
    """Planner guidance listing the restyled moment references the scenes may cite."""
    lines = ['', 'MOMENT REFERENCES', 'This book commemorates a real day, and it has exactly one story page '
             'per photograph the reader uploaded — no invented pages, none left out. The photographs were '
             'uploaded in the order the day happened. Styled moment references are prepared automatically '
             'from them; cite them by id in a scene\'s asset_refs. Each moment reference counts toward the '
             'six-image budget like any prop or place reference. Every numbered page must recreate exactly '
             'one moment: page 1 uses moment_01, page 2 uses moment_02, and so on. The cover (page 0) is '
             'illustrated from the story as usual and must not use a moment. A plan with an uncited '
             'photograph, an empty page, two moments on a page, a moment on the cover, or pages out of '
             'photograph order cannot be approved.',
             'Available moments, in day order:']
    for photo in moment['photos']:
        lines.append(f"- {photo['id']}: {photo['caption']}")
    return '\n'.join(lines)

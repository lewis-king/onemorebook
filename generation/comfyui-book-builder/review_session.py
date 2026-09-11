"""Keep local review weights only within one asset phase; always release on exit."""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import urllib.request

current = ContextVar('book_review_session', default=None)


@contextmanager
def phase(project, directory):
    if not project['render_settings'].get('review_session_policy'):
        yield
        return
    state={'models':set(), 'directory':directory}
    token=current.set(state)
    try:
        yield
    finally:
        current.reset(token)
        for url, model in state['models']:
            request=urllib.request.Request(url.rstrip('/')+'/api/generate',
                json.dumps({'model':model,'keep_alive':0}).encode(),{'Content-Type':'application/json'})
            try:urllib.request.urlopen(request,timeout=30).close()
            except OSError:pass

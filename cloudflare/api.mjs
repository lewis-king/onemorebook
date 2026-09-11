// The public website only browses completed books and adds stars.
// All Supabase credentials stay in the Pages Function environment.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const BOOK_FIELDS = 'id,title,theme,book_summary,cover_image_prompt,content,age_range,story_prompt,characters,created_at,updated_at,stars';
class HttpError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}
const json = (value, status = 200) => new Response(JSON.stringify(value), {
  status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' },
});

function numberParam(params, name, fallback, min, max) {
  const raw = params.get(name);
  if (raw === null) return fallback;
  if (!/^\d+$/.test(raw) || !Number.isSafeInteger(Number(raw)) || Number(raw) < min || Number(raw) > max)
    throw new HttpError(400, `Invalid ${name}.`);
  return Number(raw);
}

function storageBase(env, id) {
  return `${env.SUPABASE_URL.replace(/\/$/, '')}/storage/v1/object/public/${encodeURIComponent(env.SUPABASE_STORAGE_BUCKET || 'book-imgs')}/${id}`;
}

function bookResponse(row, env) {
  const content = row.content || { pages: [], metadata: {} };
  const metadata = content.metadata || {};
  const base = storageBase(env, row.id);
  return {
    ...row, stars: row.stars ?? 0,
    age_range: metadata.ageRange || row.age_range || '',
    characters: metadata.characters || row.characters || [],
    cover_image_url: content.coverImageUrl || metadata.coverImageUrl || `${base}/cover.jpg`,
    content: { ...content, pages: (content.pages || []).map((p, i) => ({ ...p, imageUrl: p.imageUrl || `${base}/page_${p.pageNumber || i + 1}.png` })) },
  };
}

async function database(env, params, options = {}, fetcher = fetch) {
  if (!env.SUPABASE_URL || !env.SUPABASE_ANON_KEY)
    throw new HttpError(503, 'The book library is not configured yet.');
  const response = await fetcher(`${env.SUPABASE_URL.replace(/\/$/, '')}/rest/v1/books?${new URLSearchParams(params)}`, {
    ...options,
    headers: { apikey: env.SUPABASE_ANON_KEY, Authorization: `Bearer ${env.SUPABASE_ANON_KEY}`,
      'Content-Type': 'application/json', Prefer: 'return=representation', ...options.headers },
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new HttpError(502, 'The book library is temporarily unavailable. Please try again.');
  return response.json();
}

async function addStar(id, env, fetcher) {
  // Conditional updates serialize competing increments in Postgres without
  // trusting the browser's count or requiring a new database function/schema.
  for (let attempt = 0; attempt < 5; attempt++) {
    const rows = await database(env, { select: 'id,stars', id: `eq.${id}`, status: 'eq.complete' }, {}, fetcher);
    if (!rows.length) throw new HttpError(404, 'Book not found.');
    const previous = rows[0].stars;
    const stars = previous ?? 0;
    if (!Number.isSafeInteger(stars) || stars < 0 || stars >= 2147483647)
      throw new HttpError(409, 'This book cannot receive another star.');
    const updated = await database(env, {
      select: 'id,stars', id: `eq.${id}`, status: 'eq.complete', stars: previous === null ? 'is.null' : `eq.${stars}`,
    }, { method: 'PATCH', body: JSON.stringify({ stars: stars + 1 }) }, fetcher);
    if (updated.length) return updated[0];
  }
  throw new HttpError(409, 'Another vote arrived at the same time. Please try again.');
}

export async function handleRequest(request, env, fetcher = fetch) {
  try {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/$/, '');
    if (path === '/api/health' && request.method === 'GET') {
      await database(env, { select: 'id', status: 'eq.complete', limit: '1' }, {}, fetcher);
      return json({ status: 'ok' });
    }
    if ((path === '/api/books' || path === '/api/books/top') && request.method === 'GET') {
      const sort = url.searchParams.get('sortBy') || 'stars';
      const order = url.searchParams.get('order') || 'desc';
      if (!['stars', 'date'].includes(sort) || !['asc', 'desc'].includes(order))
        throw new HttpError(400, 'Invalid sort order.');
      const limit = numberParam(url.searchParams, 'limit', path.endsWith('/top') ? 3 : 9, 1, 50);
      const offset = numberParam(url.searchParams, 'offset', 0, 0, 1000000);
      const rows = await database(env, { select: BOOK_FIELDS, status: 'eq.complete',
        order: `${sort === 'date' ? 'created_at' : 'stars'}.${order}.nullslast,created_at.desc,id.asc`, limit: String(limit), offset: String(offset) }, {}, fetcher);
      return json(rows.map(row => bookResponse(row, env)));
    }
    const match = path.match(/^\/api\/books\/([^/]+)(\/stars)?$/);
    if (match) {
      const [, id, voting] = match;
      if (!UUID.test(id)) throw new HttpError(400, 'Invalid book ID.');
      if (!voting && request.method === 'GET') {
        const rows = await database(env, { select: BOOK_FIELDS, id: `eq.${id}`, status: 'eq.complete' }, {}, fetcher);
        if (!rows.length) throw new HttpError(404, 'Book not found.');
        return json(bookResponse(rows[0], env));
      }
      if (voting && request.method === 'PUT') {
        const origin = request.headers.get('Origin');
        if (origin && origin !== url.origin) throw new HttpError(403, 'Use this website to add a star.');
        if (!request.headers.get('Content-Type')?.toLowerCase().startsWith('application/json'))
          throw new HttpError(415, 'Expected JSON.');
        if (Number(request.headers.get('Content-Length') || 0) > 1024) throw new HttpError(413, 'Request is too large.');
        // Counts in legacy clients are ignored: one request always adds one star.
        let size = 0;
        if (request.body) {
          const reader = request.body.getReader();
          while (true) {
            const { value, done } = await reader.read(); if (done) break;
            size += value.byteLength;
            if (size > 1024) { await reader.cancel(); throw new HttpError(413, 'Request is too large.'); }
          }
        }
        return json(await addStar(id, env, fetcher));
      }
      throw new HttpError(405, 'Method not allowed.');
    }
    throw new HttpError(404, 'API route not found.');
  } catch (error) {
    return json({ error: error instanceof HttpError ? error.message : 'The book library is temporarily unavailable. Please try again.' },
      error instanceof HttpError ? error.status : 502);
  }
}

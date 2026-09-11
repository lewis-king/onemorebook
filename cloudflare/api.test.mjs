import test from 'node:test';
import assert from 'node:assert/strict';
import { handleRequest } from './api.mjs';

const id = '68d227eb-8853-4925-a289-caf98e4c1000';
const env = { SUPABASE_URL: 'https://database.example', SUPABASE_ANON_KEY: 'server-only-test-key' };
const reply = value => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
const get = (path, fetcher) => handleRequest(new Request('https://books.example' + path), env, fetcher);

test('library filters completed books, bounds pagination and uses stable ordering', async () => {
  let called;
  const result = await get('/api/books?sortBy=date&limit=12&offset=9', async (url, options) => {
    called = new URL(url); assert.equal(options.headers.apikey, env.SUPABASE_ANON_KEY);
    return reply([{ id, title: 'Saved book', stars: null, content: { pages: [] } }]);
  });
  assert.equal(result.status, 200); assert.equal(called.searchParams.get('status'), 'eq.complete');
  assert.equal(called.searchParams.get('limit'), '12'); assert.equal(called.searchParams.get('offset'), '9');
  assert.match(called.searchParams.get('order'), /^created_at.desc.*id.asc$/);
  const [book] = await result.json(); assert.equal(book.stars, 0);
  assert.equal(book.cover_image_url, `https://database.example/storage/v1/object/public/book-imgs/${id}/cover.jpg`);
  assert.doesNotMatch(JSON.stringify(book), /server-only-test-key/);
});

test('new explicit artwork URLs and existing legacy content both work', async () => {
  const content = { coverImageUrl: 'https://images.example/cover.png', metadata: { ageRange: '4–7' },
    pages: [{ pageNumber: 1, text: 'First', imageUrl: 'https://images.example/page.png' }, { pageNumber: 2, text: 'Second' }] };
  const response = await get('/api/books/' + id, async () => reply([{ id, content }]));
  const book = await response.json(); assert.equal(book.cover_image_url, content.coverImageUrl);
  assert.equal(book.content.pages[0].imageUrl, content.pages[0].imageUrl);
  assert.match(book.content.pages[1].imageUrl, /page_2.png$/); assert.equal(book.age_range, '4–7');
});

test('invalid queries and IDs never reach the database', async () => {
  for (const path of ['/api/books?limit=0', '/api/books?limit=51', '/api/books?offset=-1', '/api/books?limit=1abc', '/api/books?order=oops', '/api/books/invalid']) {
    const result = await get(path, () => { throw Error('Should not reach the database'); });
    assert.equal(result.status, 400, path);
  }
});

test('unpublished/missing books return 404 and public authoring is unavailable', async () => {
  const missing = await get('/api/books/' + id, async url => {
    assert.equal(new URL(url).searchParams.get('status'), 'eq.complete'); return reply([]);
  });
  assert.equal(missing.status, 404);
  for (const path of ['/api/books', '/api/books/upload', '/api/books/' + id]) {
    const result = await handleRequest(new Request('https://books.example' + path, { method: 'POST' }), env, () => { throw Error('Unexpected DB call'); });
    assert.ok(result.status >= 400 && result.status < 500);
  }
});

test('two simultaneous votes both count, ignoring caller-supplied totals', async () => {
  let stars = 7, patches = 0;
  const database = async (url, options) => {
    const params = new URL(url).searchParams;
    if (options.method === 'PATCH') {
      patches++; const expected = Number(params.get('stars').slice(3));
      if (expected !== stars) return reply([]);
      const update = JSON.parse(options.body); assert.deepEqual(Object.keys(update), ['stars']);
      assert.equal(update.stars, stars + 1); stars = update.stars;
    }
    return reply([{ id, stars }]);
  };
  const vote = () => handleRequest(new Request(`https://books.example/api/books/${id}/stars`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json', Origin: 'https://books.example' }, body: '{"stars":999999}',
  }), env, database);
  const results = await Promise.all([vote(), vote()]);
  assert.equal(stars, 9); assert.ok(patches >= 3);
  assert.deepEqual((await Promise.all(results.map(r => r.json()))).map(r => r.stars).sort(), [8, 9]);
});

test('null stars increment safely and write conflicts are bounded', async () => {
  let calls = 0;
  const vote = fetcher => handleRequest(new Request(`https://books.example/api/books/${id}/stars`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: '{}',
  }), env, fetcher);
  const result = await vote(async (url, options) => {
    if (options.method === 'PATCH') {
      assert.equal(new URL(url).searchParams.get('stars'), 'is.null');
      assert.equal(JSON.parse(options.body).stars, 1); return reply([{ id, stars: 1 }]);
    }
    return reply([{ id, stars: null }]);
  });
  assert.equal((await result.json()).stars, 1);
  const conflict = await vote(async (_url, options) => { calls++; return reply(options.method === 'PATCH' ? [] : [{ id, stars: 1 }]); });
  assert.equal(conflict.status, 409); assert.equal(calls, 10);
});

test('vote requests reject cross-origin writes and oversized streamed bodies', async () => {
  const vote = options => handleRequest(new Request(`https://books.example/api/books/${id}/stars`, options), env, () => { throw Error('Unexpected DB call'); });
  assert.equal((await vote({ method: 'PUT', headers: { Origin: 'https://elsewhere.example', 'Content-Type': 'application/json' }, body: '{}' })).status, 403);
  assert.equal((await vote({ method: 'PUT', body: '{}' })).status, 415);
  assert.equal((await vote({ method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: 'x'.repeat(1025) })).status, 413);
});

test('upstream and missing-configuration failures remain useful and redact details', async () => {
  const upstream = await get('/api/books', async () => new Response('secret database diagnostic', { status: 500 }));
  assert.equal(upstream.status, 502); assert.doesNotMatch(await upstream.text(), /secret database diagnostic/);
  const missing = await handleRequest(new Request('https://books.example/api/books'), {});
  assert.equal(missing.status, 503);
});

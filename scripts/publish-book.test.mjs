import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const hash = value => createHash('sha256').update(value).digest('hex');
async function fixture(t) {
  const directory = await mkdtemp(path.join(tmpdir(), 'onemorebook-publication-test-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  await mkdir(path.join(directory, 'pages'));
  const story = JSON.stringify({ metadata: { title: 'Test export' }, pages: [{ pageNumber: 1, text: 'Test page.' }] });
  const assets = { 'cover.png': 'fixture cover bytes', 'pages/page-001.png': 'fixture page bytes' };
  const manifest = { status: 'complete', approval_mode: 'human', session_id: 'test-' + randomUUID(), story_sha256: hash(story),
    approvals: Object.entries(assets).map(([stage, bytes]) => ({ stage, sha256: hash(bytes), decision_id: randomUUID() })) };
  await writeFile(path.join(directory, 'story.json'), story);
  await writeFile(path.join(directory, 'manifest.json'), JSON.stringify(manifest));
  for (const [name, bytes] of Object.entries(assets)) await writeFile(path.join(directory, name), bytes);
  // Even a regression cannot contact Supabase from this test process.
  const guard = path.join(directory, 'no-network.mjs');
  await writeFile(guard, 'globalThis.fetch = () => { throw new Error("NETWORK_FORBIDDEN_IN_TEST"); };');
  const run = (...args) => spawnSync(process.execPath, ['--import', guard, 'scripts/publish-book.mjs', '--export', directory, ...args],
    { cwd: root, encoding: 'utf8', timeout: 10000 });
  return { directory, manifest, run };
}

test('approved dry runs are local and resume the same publication checkpoint', async t => {
  const f = await fixture(t);
  const first = f.run(); assert.equal(first.status, 0, first.stderr);
  const result = JSON.parse(first.stdout);
  assert.equal(result.mode, 'dry-run'); assert.equal(result.images, 2);
  const checkpoint = path.join(root, '.local/publications', result.id);
  assert.equal(result.checkpoint, checkpoint);
  t.after(() => rm(checkpoint, { recursive: true, force: true }));
  const before = await readFile(path.join(checkpoint, 'state.json'), 'utf8');
  assert.deepEqual(JSON.parse(before).uploaded, []);
  const second = f.run(); assert.equal(second.status, 0, second.stderr);
  assert.equal(JSON.parse(second.stdout).id, result.id);
  assert.equal(await readFile(path.join(checkpoint, 'state.json'), 'utf8'), before);
});

test('publication refuses an export without human approval before any upload', async t => {
  const f = await fixture(t); f.manifest.approval_mode = 'automated';
  await writeFile(path.join(f.directory, 'manifest.json'), JSON.stringify(f.manifest));
  const result = f.run('--publish'); assert.equal(result.status, 1);
  assert.match(result.stderr, /completed, human-reviewed export/);
  assert.doesNotMatch(result.stderr, /NETWORK_FORBIDDEN_IN_TEST/);
});

test('publication refuses artwork changed after approval', async t => {
  const f = await fixture(t);
  await writeFile(path.join(f.directory, 'pages/page-001.png'), 'unapproved replacement');
  const result = f.run('--publish'); assert.equal(result.status, 1);
  assert.match(result.stderr, /Image differs from its approved export: pages\/page-001.png/);
  assert.doesNotMatch(result.stderr, /NETWORK_FORBIDDEN_IN_TEST/);
});

test('publication refuses story changes after export', async t => {
  const f = await fixture(t);
  await writeFile(path.join(f.directory, 'story.json'), '{"metadata":{"title":"Changed"},"pages":[]}');
  const result = f.run('--publish'); assert.equal(result.status, 1);
  assert.match(result.stderr, /Story differs from the approved export/);
  assert.doesNotMatch(result.stderr, /NETWORK_FORBIDDEN_IN_TEST/);
});

// Import a completed, human-approved local export into existing Supabase storage.
// Defaults to a dry run. Publication is resumable; existing assets are never replaced.
import { readFile, writeFile, mkdir, rename } from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const exportArg = args[args.indexOf('--export') + 1];
if (!args.includes('--export') || !exportArg || exportArg.startsWith('--')) {
  console.error('Usage: node scripts/publish-book.mjs --export generation/output/books/BOOK/export [--publish]'); process.exit(1);
}
const directory = path.resolve(exportArg);
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const digestFile = async p => sha(await readFile(p));
const manifest = JSON.parse(await readFile(path.join(directory, 'manifest.json')));
if (manifest.status !== 'complete' || manifest.approval_mode !== 'human') throw Error('Publish only a completed, human-reviewed export.');
const story = JSON.parse(await readFile(path.join(directory, 'story.json')));
if (await digestFile(path.join(directory, 'story.json')) !== manifest.story_sha256) throw Error('Story differs from the approved export.');
const approvals = new Map(manifest.approvals.map(a => [a.stage, a]));
const files = [{ local: 'cover.png', remote: 'cover.png' }, ...story.pages.map(p => ({
  local: `pages/page-${String(p.pageNumber).padStart(3, '0')}.png`, remote: `page_${p.pageNumber}.png`,
}))];
if (!story.pages.length || new Set(story.pages.map(p => p.pageNumber)).size !== story.pages.length) throw Error('Invalid page numbering.');
for (const file of files) {
  const approval = approvals.get(file.local);
  if (!approval || !approval.decision_id || await digestFile(path.join(directory, file.local)) !== approval.sha256)
    throw Error(`Image differs from its approved export: ${file.local}`);
  file.sha256 = approval.sha256;
}
const exportSha = sha(JSON.stringify([manifest.session_id, manifest.story_sha256, files.map(f => f.sha256)]));
// A new accepted export revision gets a separate publication; rerunning it resumes the same ID.
const bytes = Buffer.from(createHash('sha256').update('onemorebook:' + exportSha).digest().subarray(0, 16));
bytes[6] = (bytes[6] & 15) | 80; bytes[8] = (bytes[8] & 63) | 128;
const hex = bytes.toString('hex');
const id = `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
const checkpoint = path.join(root, '.local', 'publications', id);
await mkdir(checkpoint, { recursive: true });
let state;
try { state = JSON.parse(await readFile(path.join(checkpoint, 'state.json'))); }
catch (e) { if (e.code !== 'ENOENT') throw e; state = { id, exportSha, exportDirectory: directory, createdAt: new Date().toISOString(), uploaded: [] }; }
if (state.exportSha !== exportSha) throw Error('Publication checkpoint mismatch.');
const save = async () => {
  const temporary = path.join(checkpoint, `state.${process.pid}.tmp`);
  await writeFile(temporary, JSON.stringify(state, null, 2) + '\n');
  await rename(temporary, path.join(checkpoint, 'state.json'));
};
await save();
console.log(JSON.stringify({ title: story.metadata.title, id, pages: story.pages.length, images: files.length, exportSha, checkpoint, mode: args.includes('--publish') ? 'publish' : 'dry-run' }, null, 2));
if (!args.includes('--publish')) process.exit(0);

try { process.loadEnvFile(path.join(root, 'backend/.env')); } catch (e) { if (e.code !== 'ENOENT') throw e; }
const base = process.env.SUPABASE_URL?.replace(/\/$/, '');
const key = process.env.SUPABASE_ANON_KEY;
if (!base || !key) throw Error('Configure SUPABASE_URL and SUPABASE_ANON_KEY in the environment or backend/.env.');
const bucket = process.env.SUPABASE_STORAGE_BUCKET || 'book-imgs';
const headers = { apikey: key, Authorization: `Bearer ${key}` };
const publicUrl = filename => `${base}/storage/v1/object/public/${encodeURIComponent(bucket)}/${id}/${filename}`;
async function request(route, options = {}) {
  const response = await fetch(base + route, { ...options, headers: { ...headers, ...options.headers }, signal: AbortSignal.timeout(60000) });
  if (!response.ok) {
    const detail = await response.text();
    throw Error(`Supabase ${options.method || 'GET'} ${route.split('?')[0]} failed (${response.status}): ${detail.slice(0, 400)}`);
  }
  return response;
}
const metadata = { ...story.metadata, createdAt: state.createdAt };
const content = { id, metadata, coverImageUrl: publicUrl('cover.png'),
  pages: story.pages.map(p => ({ ...p, imageUrl: publicUrl(`page_${p.pageNumber}.png`) })),
  generationExportSha256: exportSha,
};
const row = {
  id, title: metadata.title, theme: metadata.theme, book_summary: metadata.bookSummary,
  cover_image_prompt: metadata.coverImagePrompt, main_character_descriptive_prompt: metadata.mainCharacterDescriptivePrompt,
  style_reference_prompt: metadata.styleReferencePrompt, age_range: metadata.ageRange,
  story_prompt: metadata.storyPrompt, characters: metadata.characters, content, status: 'pending', stars: 0,
};
await writeFile(path.join(checkpoint, 'book-row.json'), JSON.stringify(row, null, 2));
const existing = await (await request(`/rest/v1/books?id=eq.${id}&select=id,status,content`)).json();
if (existing.length && existing[0].content?.generationExportSha256 !== exportSha) throw Error('Book ID collision; preserving existing row.');
if (!existing.length) {
  await request('/rest/v1/books', { method: 'POST', headers: { 'Content-Type': 'application/json', Prefer: 'return=representation' }, body: JSON.stringify(row) });
  state.inserted = true; await save();
}
for (const file of files) {
  // Check the public object first so a resumed import never replaces existing bytes.
  const current = await fetch(publicUrl(file.remote), { signal: AbortSignal.timeout(60000) });
  if (current.ok) {
    if (sha(Buffer.from(await current.arrayBuffer())) !== file.sha256) throw Error(`Remote asset collision: ${file.remote}`);
  } else {
    if (![400, 404].includes(current.status)) throw Error(`Cannot verify remote image: HTTP ${current.status}`);
    const data = await readFile(path.join(directory, file.local));
    await request(`/storage/v1/object/${encodeURIComponent(bucket)}/${id}/${file.remote}`, {
      method: 'POST', headers: { 'Content-Type': 'image/png', 'Cache-Control': 'max-age=31536000', 'x-upsert': 'false' }, body: data,
    });
    const verified = await fetch(publicUrl(file.remote), { signal: AbortSignal.timeout(60000) });
    if (!verified.ok || sha(Buffer.from(await verified.arrayBuffer())) !== file.sha256) throw Error(`Uploaded image verification failed: ${file.remote}`);
  }
  if (!state.uploaded.includes(file.remote)) state.uploaded.push(file.remote);
  await save(); console.log(`Verified ${file.remote}`);
}
if (existing[0]?.status !== 'complete') {
  const result = await (await request(`/rest/v1/books?id=eq.${id}&status=eq.pending`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json', Prefer: 'return=representation' },
    body: JSON.stringify({ content, status: 'complete' }),
  })).json();
  if (!result.length) throw Error('Publication status changed; inspect the saved row before resuming.');
}
state.status = 'complete'; state.url = `https://onemorebook.ai/book/${id}`; await save();
console.log(`Published: ${state.url}`);

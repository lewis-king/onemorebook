# YOLO review mode live — 2026-09-19 (latest)

The creator start form offers **Assisted** (unchanged default: human approves every step) and **YOLO**: a local AI judge (gemma4:31b, `config.review_model`) reviews each landed candidate — story/plan text, style-take ranking, reference cleanliness, and page checks against brief, cast references and moment photographs — then approves, regenerates with its corrections (max 3 per stage), or parks for a human when uncertain or exhausted. Automated decisions are recorded `source: 'yolo'`; `judge-report.json` sits in each judged attempt; exports stamp `approval_mode`. Mid-book switch via the sidebar button / `set_approval_mode`; human surgery after completion re-judges and version-exports normally. Proven e2e unattended: book-20260919123550-4f152ddd03 completed 17 stages in ~35 min; Kimi adjudication of every stage found one prompt-level slip (style take occupancy), fixed. Suite: **417 tests**.

Source: `assisted_yolo.py` (new), `assisted_store` (approval_mode config, decision source), `assisted_web` (`maybe_yolo` judge loop, `launch_judge` recovery, `set_approval_mode`), `assisted_engine` (manifest), `assisted_ui` (mode radios, judge status, pause button), `tests/test_assisted_yolo.py`. The birthday moment book (book-20260913110255-32289c92b3) is untouched, still Assisted, paused at `characters/emilia.png`.

---

# From-a-moment books — 2026-09-13

The assisted creator's start screen offers two modes: **From an idea** (unchanged) and **From a moment**. A moment book commemorates a real day: Lewis uploads up to fourteen reference photographs, gives each a short caption, and writes a free description of the day (a few cues are enough). Photographs are uploaded to `POST /book-builder/creator/upload` (validated, normalised to PNG, staged under `books/moment-uploads/`), then moved into the new session as `moment-src/moment_NN.png` with SHA-256 pinned in `config.moment` at creation. Uploads are single-use and the create payload stays small JSON.

The story writer (local Gemma, words only) receives the description and captions through an added moment brief; it keeps the real people, names and events recognisable inside a normal picture-book arc. Photographs are **never restyled upfront**: after the art style and the reusable references (characters, props, places, states) are approved, each page that cites a `moment_*` asset receives the **original photograph as a direct image input** at the moment's plan slot — assembled as cast board first (one image, however many characters), then the plan's asset slots in order. The scene brief binds the render to the memory by image number, and the engine appends that binding to the final prompt after any rewrite, so the photograph can never be silently dropped from the instruction. The original photograph appears beside each page candidate for comparison, and page edits carry it as ground truth. The planner still cites `moment_*` ids in scene `asset_refs` (schema-restricted to uploaded ids, six-image budget unchanged); validation still requires exactly one moment per numbered page, in upload order, never on the cover.

Source: `assisted_moment.py` (validation/intake/briefs/guidance), `assisted_store.config/create`, `assisted_web.upload` + `source_photo_url`, `assisted_engine.image_inputs` (photo slot, edit ground truth, final-prompt memory binding), `assisted_plan.stages` (no moment stages; `source_photo`/`photo_index` on scenes), `assisted_ui` compare view for photo-backed pages. Legacy saved states that still contain `moments/*` restyle stages keep working: the engine still handles kind `moment` stages. New sessions default to `mode: scratch`; every saved session and the public story contract are unchanged. Full pinned suite passes **401 tests**. The live birthday book was migrated on disk (14 restyle stages removed, page stages now carry `source_photo`/`photo_index`, resume point moved to the first pending reference).

---

# Cover title typography — 2026-09-11 (latest)

Cover prompts now request the exact book title in quotation marks as readable lettering, with a display font and placement chosen to suit the story mood and artwork. The instruction asks for thumbnail legibility, clear space away from faces and focal action, and no additional words. Interior page prompts retain the no-lettering rule. This is applied to the legacy/automatic prompt builder, the assisted planner's cover stage, and both story-craft prompt variants; the public story contract is unchanged.

Focused automatic and assisted tests pass, and the full pinned creator suite passes **374 tests**. Source is committed and pushed as `ca7d319`; startup commands are documented in `README.md` and the parent project README. Existing saved books and immutable prompts are unchanged; the new rule applies to future story sessions and newly prepared cover prompts.

# Broken-to-complete bridge state repair — 2026-09-11 (latest)

Book `book-20260911164447-3eeb90ba81` is paused in the assisted creator at the new pending reference `props/bridge_complete_page3.png` (revision 83):
http://127.0.0.1:8188/book-builder/create/book-20260911164447-3eeb90ba81

The approved page 3 candidate is the arrangement source. The new reference preserves its exact Button-Bridge order, spacing, colours and alignment while completing the final gap with the Pearlescent Button. Page 11 is routed to this new state. The earlier `bridge_complete` state is retired from page 11 but retained for the cover; all original attempts and decisions remain immutable. Approve or regenerate this reference in the UI before page 11 resumes; no candidate was approved automatically.

Generic workflow fix committed as `25dc968` and pushed: the private planner now scans for objects that are built, broken, repaired, stacked or otherwise changed and creates a reusable `prop_state` for each persistent form. A derived state can inherit an earlier state and retire only the superseded page visibility, preserving continuity across transitions. Full pinned suite: 371 tests pass. ComfyUI was safely restarted idle after the source update (queue empty).

# Milo accepted; Cloudflare Pages preview deployed — 2026-09-11 (latest)

Lewis completed and explicitly accepted **Milo and the Sun-Seeds**: "a successful finish of a book I'm happy with". Saved creator status complete, revision121, final page12; approved page11 is attempt4. Export: output/books/book-assisted-20260910213535-1b28c7aec5/export/. Preserve this accepted finish; the visual failures in earlier handovers describe older attempts. No generation, revisions or approvals are pending for this book.

Current requested work moved to the reader website in the parent onemorebook directory: replace Netlify/Render with Cloudflare Pages + Functions, retaining Supabase books/storage and stars. The code is pushed and the tested production preview is live at https://onemorebook.pages.dev. See ../DEPLOYMENT.md for the full handover. The custom domain remains on Netlify pending the Cloudflare zone and 123-reg nameserver change.

Before that pause, the empty Cloudflare Pages project onemorebook was created and the approved Milo export was imported into Supabase as 21df2344-4b8e-5f14-b198-03ac4112f6e4. All 13 public image hashes matched the approved export before status complete. Do not import it again to deploy the site. Its publication checkpoint is ../.local/publications/21df2344-4b8e-5f14-b198-03ac4112f6e4/. No existing books or real votes changed.

Pages API/frontend and local/hosted verification are complete. The server-side Supabase secret is uploaded to Pages; no domain/zone/nameserver/DNS changes were applied. onemorebook.ai still serves the old Netlify site. Local preview: http://localhost:8788/book/21df2344-4b8e-5f14-b198-03ac4112f6e4 (start with pnpm run build:pages then pnpm run dev:pages from the parent directory). Source/backups/tests/browser screenshots are in ../.local/cloudflare-migration-20260911/.

The assisted generator remains the selected creation mode. Acceptance of this book is not evidence that full automatic generation is ready. Full automatic experiments and Rainbow remain deferred; do not start them while the website migration is the active task.

---

# Page11 tower verified; live reference display fixed — 2026-09-11 (latest)

Lewis approved tower attempt2 (decision968d09aef71943a2a63b38748b6267bc). Page11 attempts2 and3 used it correctly as Image4: native graphs, prompt text and input hashes verified. The small-pot thumbnail Lewis reported came from old attempt1 while the new generation ran. UI now labels the old preview and displays the running job's actual model/references beside its prompt; historical details remain separate and accurate. Live polling, preparation, edit, completion, navigation, mobile and historical inspection browser checks pass. UI-only, live on browser refresh; no restart, assistant generations or approvals.

Remaining VISUAL FAILURE: page11 attempts2 and3 both draw TWO pots despite the correct three-pot input. Attempt2 also distorts Pip's wings. Do not mistake correct wiring for visual success. Latest captured state revision113, pages/page-011.png, awaiting_review; Lewis is actively testing, so recheck before acting. No assistant job is scheduled. Do not approve a candidate on his behalf.

Checkpoint .local/live-reference-display-20260911/ contains actual input graph/hash evidence, source before/after, browser tests/screenshots, state snapshots and REVIEW.md. Original candidate images remain unchanged. Shared assembled-prop architecture from the previous handover is still live. Assisted mode remains selected; full automatic books/Rainbow deferred.

---

# Reusable assembled props — 2026-09-11 (latest)

Live shared architecture: private prop_state assets declare source_assets and visible_pages; dependency ordering generates/reviews components then the assembled reference. Scene routing rejects loose components alongside the state and enforces its page schedule. Scene prompt preparation includes prior story events. Planner tests produced the Sun-Seeds tower on pages9–11 and a reusable completed kite for a different story. Detection still depends on local Gemma; human review remains required. Source: assisted_prop_states.py, assisted_plan.py, assisted_prompt_context.py, assisted_engine.py and assisted_reference_updates.py. Public story contract unchanged.

Current book http://127.0.0.1:8188/book-builder/create/book-20260910213535-1b28c7aec5 is revision107 awaiting_review at NEW props/prop_pot_tower.png. Latest attempt2 is a clean three-pot tower extracted from approved page10, then edited to remove an invented saucer. Visually inspected; human approval pending. Do NOT approve for Lewis or resubmit completed jobs a4612392-8d4c-480d-bccf-97d2cab4a8b5 / c1919c95-22bc-48d0-9446-09024bdbb84c. Queue empty at handover; check again because Lewis is actively testing.

Approving the tower will start page11 attempt2 through the app, using tower rather than the single small pot. Saved page11 brief puts Milo on the smallest/top pot with medium and large beneath. Its obsolete prompt_base pointer was cleared; previous attempt and prompt history are untouched. Original plan/public story remain byte-identical. Immutable creator/plan-updates/289de54682484344a4678184c0b817ff.json supplies the effective export plan; all earlier stages and 476 original files preserved. Source page10 is now a reference dependency, protected from independent revision. Page11 has NOT yet been regenerated or approved.

367 tests pass, both planner outputs validate, live read-only browser check passes. Exact source before/after, planner prompts/replies, reload checks, image graphs/seeds/receipts/history, screenshots and verification: .local/assembled-props-20260911/ (read REVIEW.md). All work and attempts saved. Assisted creation remains selected; automatic full-book experiments and Rainbow are deferred.

---

# Reopen approved pages and shorter book URLs — 2026-09-11 (latest)

Implemented and live. Select an approved page or cover, then Revise this page/cover. This pauses the previous stage and opens the selected illustration for fresh generation/editing. Approval replaces that page and returns to the saved stage/job/status/error; Keep the original restores its exact earlier approval/prompt while retaining new candidates and feedback. `page_revision` is durable across shutdowns. Story and shared references stay locked. Dependent scene references, nested revision, running jobs and stale revisions are rejected. For error states with a possibly lost MCP receipt, the API checks the actual queue/history before parking work. No real page was reopened or approved by the assistant.

Replacing a page in a completed book triggers a new immutable export under exports/<revision>/, updates Read your book and records export history; the old export and URLs remain intact. New book IDs use book-<14-digit timestamp>-<10-hex hash>. Existing book-assisted-… creator URLs switch in the browser to the short alias while resolving the same original directory, canonical saved ID and MCP job identity. No historical files, generation prompts or seeds were renamed.

Verification: 358 tests pass, including 10 revision/alias/API/export tests; browser checks cover reopen/edit/replace/keep-original, busy state, locked references, paused stage, short URL and 390px layout. All browser POSTs intercepted; no image generation or human decisions made. Backend safely reloaded with an empty queue and all six creator states unchanged. Live read-only browser confirms the shorter current-book URL and enabled Revise this page control.

Current book: http://127.0.0.1:8188/book-builder/create/book-20260910213535-1b28c7aec5 . Last live state revision98, page10 awaiting_review. Lewis is actively testing; recheck before submitting anything. Checkpoint .local/page-revisions-20260911/ has source before/after, state/hash snapshots, tests.log, browser/live evidence, screenshots and reload verification. Assisted mode stays selected; full automatic books and Rainbow remain deferred.

---

# One Prompt section in the assisted creator — 2026-09-11 (latest)

Lewis found historical versus next-generation prompt sections confusing. UI-only simplification is live on refresh, with no backend restart: one Prompt section uses the saved full-scene regeneration prompt, or the actual submitted prompt during generation (including image edits). Preparing states never claim the previous prompt is rendering. Original prompts that differ, model/seed and reference provenance remain under the selected Attempt details disclosure. Selecting an old attempt does not replace the saved regeneration prompt. Approved/story candidates show their historical prompt. Edit prompt is now inside this section; Copy prompt uses the corrected current prompt, never silently reverting to an older candidate's prompt. Explicit overrides still follow the existing backend path.

Browser verification covers saved base, old-attempt inspection, copying/editing/submission (POST intercepted), active image edit, preparation, approved scene, story and mobile width. No JS errors, generations, approvals or server restarts. Checkpoint .local/single-prompt-20260911/ contains source before/after, fixture, screenshots and browser-verification.json. All saved creator states are unchanged across this UI change. Last captured real state revision76 at page5 with four candidates; Lewis is testing actively, so inspect live state/queue before acting. Full automatic books and Rainbow remain deferred.

---

# Fixed base prompts wired into Regenerate — 2026-09-11 (latest)

Lewis insists corrections must be baked into page5 and the generic app workflow, so clicking Regenerate with NO feedback uses the corrected base. This is now installed/live. Source assisted_prompt_base.py + assisted_store.py + assisted_engine.py + assisted_prompt_context.py; UI exposes “Base prompt for the next generation”. First new fresh-scene preparation uses local Gemma reasoning against approved prose/brief/reference designs and saves the complete prompt. Later blank regenerations reuse it verbatim; feedback/explicit full-scene overrides revise the saved base. Image-edit instructions NEVER replace the full-scene base. Base revision is pinned to each new intent, signed against scene/story/design/reference context and recorded with immutable history. Saved old intents/native graphs remain unchanged; changed context causes new preparation. Human approval still required; model prompt preparation is not guaranteed semantic/visual validation.

Actual page5 base a9debb85d9724a2da5bfa688582d71a5 is the exact successful fresh prompt from consistency-tests/scene-relationships-20260911. It has seeds embedded in the central sunflower head, one Pip head bow/visible blue neck feathers, and named animal descriptions. No need to retype feedback. The app displays historical old candidate prompts separately from the next-generation base; refreshing loads the updated interface.

Lewis clicked Regenerate during deployment: page5attempt2 job f6576926-9f99-4e4d-8e9d-5960c6df63db used old code/prompt and finished before reload/install. Preserved. Corrected base installed at revision72, following that result. Next click should be attempt3 with scene_prompt_version1 and the pinned base above. Do not resubmit attempt2 or rewrite its old prompt. Check live state/queue before acting; user is testing actively.

348 tests pass. Live browser displays exact base and intercepted empty-feedback Regenerate request is correct; native graph preflight matches successful prompt byte-for-byte without writer/inference. Official MCP validation is saved in .local/prompt-base-20260911/preflight-validation.json. All earlier reference/candidate/decision files/public contract preserved, no assistant image submissions or approvals this change. Checkpoint .local/prompt-base-20260911/: source before/after, creator snapshots before user run and immediately before installation, installed-base.json, preflight graph, browser verification and REVIEW.md. Only prompt_base/revision/timestamp were changed by the installation. Full automatic books and Rainbow remain deferred.

---

# Page/illustration synchronization — 2026-09-11 (latest)

Lewis stresses page prose and illustration prompts MUST stay in sync. His closest previous image still failed on Pip's neck bow and detached sunflower seeds. Added generic shared planner/rewrite guidance for actor/action/target/story state, accessory ownership/attachment, and object-part/effect placement. Rewrites receive page text + actual image input numbers + current reference stage design briefs. Edits still receive only their selected image; notes cannot invent extra reference inputs. Human prompt overrides and saved graphs unchanged. Source: assisted_prompt_context.py, assisted_engine.py, assisted_plan.py. New plans and requested feedback revisions use it; plain re-render of an old unchanged approved brief is NOT retroactively corrected.

Two isolated tests FINISHED using local Gemma4 revisions and Flux2.dev Turbo8: fresh 20f25655-6c51-402d-8d85-c9a970f356c6, 55.32s; edit c86349a2-4c56-4907-b101-22bc9b4ca3c8, 30.29s. Fresh fixes the two reported faults and retains three characters, but simplifies the garden/layout. Edit FAILS: removes Milo's scarf and leaves detached seeds. Do not approve or select for Lewis. Gallery http://127.0.0.1:8188/book-builder/books/consistency-tests/scene-relationships-20260911/index.html . Exact graphs, reference data, text replies, outputs and REVIEW.md in that folder. No more jobs scheduled; do not resubmit.

Final edit guidance additionally requests species/visible feature plus name. That wording and the explicit page-prose authority sentence were finalized after the two text requests; do not claim their exact final wording has been visually verified. The fresh correction is evidence for this feedback case only, not guaranteed semantic validation. Human-assisted approval remains selected.

339 full tests, four final focused checks, saved source before/after, verified official MCP outputs and idle backend reloads. Checkpoint .local/scene-relationships-20260911/. All six creator states/public schema unchanged. Milo remains at page5 awaiting_review; no real approval or candidate replacement. Earlier long identity-insertion candidate remains archived, NOT activated. Full automatic books and Rainbow remain deferred.

---

# Targeted identity/reference comparison — 2026-09-11 (latest)

Lewis explicitly authorized a few targeted image comparisons and asked the assistant to inspect them. Completed five recipes at two matching seeds: nine fresh local FLUX2.dev Turbo8 renders plus the unchanged original page5 image. This batch is FINISHED; queue empty at verification. No further jobs scheduled and no human approvals or book candidates changed. All six creator.json files and public contract are byte-identical to the checkpoint.

Comparison: http://127.0.0.1:8188/book-builder/books/consistency-tests/assisted-identity-20260911/index.html . Exact graphs/seeds/references, original control, outputs, official MCP validation/submission/history/fetch and per-image visual observations: output/books/consistency-tests/assisted-identity-20260911/. Read REVIEW.md and comparison.json before any follow-up. Checkpoint .local/assisted-identity-20260911/verification.json. Do not resubmit completed graphs.

Best overall image: bound-board-seed2_00001_.png (explicit full identity + shared cast board). Correct three characters, correct Milo pointing, garden retained; extra neck bow on Pip and detached seeds remain. Results by recipe (correct cast, NOT whole-page passes): names-only shared0/2; full identities shared1/2; full identities separate0/2; explicit count shared0/2; concise source roles separate2/2. The final pair lost the garden and shifted relative sizes, so separate portraits are not an established improvement overall. Shared3-reference runs45–55s; separate5-reference runs80–85s. One scene/two seeds is too small for general success-rate claims. Explicit identities fixed the acting character in all these variants but did not consistently fix duplication. BFL supports explicit subject/source mapping; brackets are not special syntax.

IMPORTANT: candidate identity-binding code was tested (343 technical tests including8new) but visual evidence did not justify deploying it. All four candidate source/test files are archived under .local/assisted-identity-20260911/candidate/. Active assisted_engine.py and existing test restored byte-for-byte; new assisted_identity.py/test removed from active source after archiving. Backend was never reloaded with the candidate. The prior simple creator + flexible8–16pages/target12changes remain live. Do not mistake archived candidate code for installed functionality.

Suggested next controlled experiment (NOT performed or scheduled): keep shared board/references/settings/seeds fixed and change only to concise identity/action prose. Separately address seed-to-flower spatial relationship. Do not add more runs or revive full automatic books/Rainbow without the current user direction. Assisted approval remains selected; Milo and the Sun-Seeds remains at page5 awaiting_review as before.

---

# Simple creator and flexible story length — 2026-09-11 (latest)

Lewis wants one optional idea paragraph and Generate. His examples inform implicit craft, not genre/art/voice controls. Audience remains 4–7. Latest explicit preference: twelve illustrated story pages as the writer's starting point, freedom to use 8–16 when the story needs it, and NO page-count control on the creation form. This is implemented and live.

New simple-form configs use picturebook-2, page_count=0, page_count_min=8, page_count_max=16, page_count_target=12. Local Gemma chooses the count while planning. Validation still enforces the unchanged public contract. Candidate guides show actual length; approval locks that exact manuscript; later plan/pages/export follow actual count. Old configs/fixed-length saved workflow inputs remain intact. Legacy picturebook-1 remains for explicit presets; no existing session was rewritten.

Verification: 335 tests, seven final target checks, desktop/mobile blank-input/browser tests, safe idle reloads preserving every session file, original schema byte-identical. Checkpoint .local/simple-creator-20260911/verification.json and source-before/source-after archives. One blank-input text-only sample book-assisted-20260911110107-6db0271483 (Oona and the Echo-Jar) chose14 pages/372 words, local Gemma with reasoning, one70.02s response. It predates the final soft12target addition, is hidden as verification_only and remains awaiting_review with no approvals/images. Do not resubmit. Editorial gaps are recorded in sample-review.md, not repaired/approved.

Lewis is actively reviewing Milo and the Sun-Seeds, book-assisted-20260910213535-1b28c7aec5. Last checked at page5 awaiting_review; check current state before any work. He reported an extra central animal in page5attempt1. Investigation found actual three-character reference correctly wired once, but assisted image_inputs appends names-only cast labels and relies on the brief for species/clothing. This brief omitted those identities despite planner instructions. The older automatic flux_prompt compiler has explicit name/identity/action mapping; assisted path does not enforce that. This gap is NOT fixed by today's story-form changes. Evidence and proposed controlled comparison: .local/simple-creator-20260911/duplication-investigation/REVIEW.md. No image generation or candidate decisions were performed for this investigation.

Human-assisted review remains selected. Full automatic books and Rainbow remain deferred. Do not claim complete generator quality from unit tests or a valid text sample.

---

# Story craft improvements — 2026-09-11

Implemented and live in the assisted creator. Audience defaults to **shared reading ages 4–7**. Lewis's additional key reference is **Sammy Feels Shy**, probably his daughter's favourite Big Bright Feelings book. Research also covers Bea's Bad Day, Julia Donaldson/illustrators, I Am a Tiger, Once Upon a Giraffe and developmental studies, with evidence limits: `docs/STORY-CRAFT-RESEARCH.md`.

New sessions use `story_craft_version=picturebook-1`, choices for story flavour (surprise/adventure/comedy/feelings/wonder), read-aloud style (patterned/prose/rhyme), and material-based art preset (painted/graphic/paper). Custom art overrides a preset. Prompts put story experience, causal goals, read-aloud rhythm, emotional credibility and words/pictures interplay before compact visual contracts. Intentional false dialogue/pretence must not change physical species or summon extra characters. Shyness/belonging guidance supports voluntary participation; quietness is not a defect. New private planner gets the same guidance. No image graph/model/sampling changes.

Public schema unchanged. Old sessions without the craft version retain their saved configs and legacy writing/planning guidance. This includes Lewis's current **Milo and the Sun-Seeds** book (`book-assisted-20260910213535-1b28c7aec5`), which he is actively reviewing around page 3. Check live state before touching anything. Do not make his decisions or interrupt his queue. Current human-review mode remains; automatic books and Rainbow are deferred.

Human story review includes measured word counts and optional editorial questions, never an automatic score. New Comfy library copy: `childrens-book-generator-v2-assisted-storycraft.json` (original preserved). Separate API graph passed official MCP validation. 328 tests and desktop/mobile browser checks pass. Backend reloaded safely while idle; all four pre-existing session files unchanged across restart.

Text-only verification `book-assisted-20260911104330-d81a8f131e` produced **The Glip-Glop-Bloop**, eight pages/205 words, in 51.23 seconds on local Gemma 4 with reasoning, one response and no structural repairs. Status awaiting_review at story, no approvals or images. Hidden from normal listing with verification_only. Direct URL: http://127.0.0.1:8188/book-builder/create/book-assisted-20260911104330-d81a8f131e . Do not resubmit. Some editorial issues remain (unrequested bubbles in page 1 brief, Markdown emphasis on sounds); this is not a certified good book or a literary benchmark.

Checkpoint: `.local/story-craft-20260911/verification.json`, test/browser records, readable `sample-review.md`, exact sample request/response in its stage folder, source-before/source-after archives. No hand-touched real story, approved candidate or public contract. Future prompt changes should preserve saved version behaviour and exact attempt requests. The implementation work is complete; broad book quality still requires human-reviewed evidence.

# Reference budget fixed — 2026-09-11

Lewis found the artificial four-prop/place limit. The assisted planner and renderer now share a six-input-image budget matching BFL's recommendation for Flux2.dev. Visible characters occupy one shared cast image; five prop/place references are permitted alongside it. Scenes without characters can use six prop/place references. At most one location remains. Unknown references and actual total overflow have distinct errors. No references are silently dropped.

The current user session book-assisted-20260910213535-1b28c7aec5 is now at PLAN, awaiting_review: Lewis approved the story after the migration handover. Saved candidate plan:1 had been rejected solely because page 9 has five prop/place references. It now validates (one cast + five = six). The page revalidates pending text/plan drafts when displaying them; original validation reports, JSON, hashes, decisions and creator state stay unchanged. No regeneration or approval was performed. Refresh the creator to review the existing plan normally. Do not approve for Lewis.

320 tests pass, including actual renderer reference packing for five-plus-cast and six-without-cast, overflow/unknown errors, and non-mutating revalidation. Live API verified the old rejection clears; no new jobs/decisions. Checkpoint and evidence: .local/reference-budget-20260911/. Source: https://docs.bfl.ml/guides/prompting_editing_overview. Full automatic book and Rainbow remain deferred.

---

# Current handover — 2026-09-11

The book creator has moved into this generation directory at Lewis's request. Source is `comfyui-book-builder/`, books are `output/books/`, legacy books are `output/codex/books/`, workflow copies are `comfyui/workflows/`, and the unchanged public contract is `contracts/story.schema.json`. Historical work/checkpoints remain in `book-workflow-v2/`. Old ComfyUI locations are symlinks for compatibility, not extra copies.

Start/reuse ComfyUI and this creator with `python run.py start` from here. URL: http://127.0.0.1:8188/book-builder/create. Server PID/log are in `.local/server.json` and `.local/comfyui.log`. The runtime uses the existing Comfy Python and pinned official MCP environment under `~/comfy`; models were not moved or changed. No automatic book stage is launched at startup.

## User book ready for review

http://127.0.0.1:8188/book-builder/create/book-assisted-20260910213535-1b28c7aec5

- Title: **Milo and the Sun-Seeds**, twelve pages, cast Milo/Pip/Bramble.
- Current stage: story. Status: awaiting_review. No human approval has been made by the assistant.
- Attempt 1 is the user's failed response from the screenshot: `done:false`, broken JSON and repeated words. Preserved verbatim.
- Attempt 2 job: `9ecc3713-9d81-4d4c-9531-af86db8e24cb`. Completed in 82.20 seconds, one local Gemma4:31b request, reasoning enabled. `done:true`, `done_reason:stop`; no formatting repairs or contract errors.
- Candidate: `output/books/book-assisted-20260910213535-1b28c7aec5/creator/stages/story/attempt-0002/candidate.json`.
- Do not resubmit or approve it without Lewis's decision. He can approve/regenerate in the creator.

## Fixes

- `assisted_web.launch` now allocates an immutable intent before scheduling, so concurrent Resume calls share one task. Completion callbacks can only remove their own task.
- `assisted_writer.py` persists complete local replies and permits at most two requests for incomplete/malformed JSON. Gemma keeps thinking enabled, with the JSON schema in the prompt and strict local validation after generation. This avoids the Ollama 0.30.8 thinking-to-grammar restart involved in the saved failure. Never accept a truncated reply or infer human quality approval from structural checks.
- Root lookup and output image records support the moved files and Comfy's output aliases. The creator uses `generation/mcp/call.py` with the pinned official MCP Python instead of depending on a Node executable in another project.

## Verification and recovery

Records are in `.local/migration-20260911/`:

- Every moved file byte-hashed before/after migration; source backup `source-before.tar.gz`. Originals/schema hashes are in `complete.json` and `before.json`.
- 312 unit/API tests pass (`tests-writer.log`), including the reproduced Resume race, output symlinks and bounded text recovery.
- Browser tests pass in `browser/ui-test-result.json`; decisions there use mocked fixture endpoints only.
- The image saving/fetch verification job `56a469a8-eefb-4a33-b07b-809a6983cc92` copies existing pixels through the real assisted reference/saver nodes. It performs no image inference. Its verification-only session is `book-assisted-20260911063121-86ce0fe478`, hidden from the normal list, with no approvals. Native graph, validation, submission, history and fetch receipts are saved. Do not resubmit.
- Earlier live story session `book-assisted-20260910211408-f116aee5e9` and image test `book-assisted-20260910211942-97d65cced6` were moved intact. Neither was approved.

The original automatic generator is still unaccepted. Assisted human review is the active mode. Preserve the older accepted book and all rejected candidates. Rainbow remains deferred. Feedback is stored for future generic improvements, not automatic model training.

Final migration checks: 9,252 historical output files unchanged, 76 old page/image URLs pass, four assisted sessions unchanged through restart, real saved image pixels and fetched file match. The twelve-page draft passes the app backend's actual `UploadStorySchema.shape.story` validator. Live browser shows the new story with approval enabled; no decisions submitted. Queue empty. See `.local/migration-20260911/verification.json`.

# Story ending and cast-quality pass — 2026-09-12

New books now default to a 14-page starting point while retaining the open 8–16 page range; the writer may choose fewer or more when the arc earns it. Existing saved configurations are unchanged. The Comfy starter node and legacy fixed-length node default are also 14 for newly created runs.

Story-writing prompts now require a specific final consequence and an earlier planted payoff/callback. They explicitly reject premise repetition, identity announcements, generic thank-yous and unexplained magic fixes, and ask for a final two-page self-check. New prompts also ask for pronounceable, distinct names and varied species/roles when the premise allows, without forcing exotic casts or rejecting deliberate same-species stories.

The Gemma4 automatic editorial review now has private checks for `specific_payoff`, `character_name_quality` and `cast_variety`; a failed review remains fail-closed and the automatic writer retries with the concrete review report. The assisted creator still pauses for Lewis's human approval by design. No book was generated, approved or altered for this change.

# Pocket-Sized Lion ending revision — 2026-09-12

Lewis supplied a weak 12-page candidate, **The Pocket-Sized Lion**, whose ending stopped at Leo and Pip chatting about the weather. The original candidate remains unchanged at `output/books/book-20260912065334-b03404f8db/creator/stages/story/attempt-0001/`.

A text-only regeneration was requested with feedback requiring a 14-page arc, a concrete consequence of Leo's dandelion identity, Pip's choice, Arthur's reaction and a callback. Attempt 2 is now awaiting human review at `http://127.0.0.1:8188/book-builder/create/book-20260912065334-b03404f8db`; it has 14 pages/373 words. Pages 13–14 have Leo shaking his mane to “spread seeds”, bouncing Pip and Arthur onto the mossy rock from page 1, with Arthur's closing reaction. No images or approvals were made.

The full Gemma4 editorial review was run separately and saved at `creator/stages/story/attempt-0002/editorial-review.json`. It passed all checks, including `specific_payoff`, `character_name_quality`, `cast_variety`, page-by-page action/cast checks and continuity. This is evidence for the text candidate only; Lewis's approval is still required before planning or artwork.

# Ending-closure pass — 2026-09-12

Lewis identified the remaining weakness precisely: a final page can contain a valid consequence yet
still feel as though the book simply stops. New story prompts now require a recognisable closing beat
after the resolution: a visible aftermath or settling image, a shared final reaction or emotional
landing, and a final sentence with satisfying read-aloud cadence. They explicitly reject stopping
mid-action or on ordinary small talk. The legacy, picturebook-1 and picturebook-2 writers all carry
the same guidance so future books receive it regardless of saved craft version.

Gemma4's editorial review now records a separate `ending_closure` check alongside `specific_payoff`.
This keeps a concrete plot consequence and the reader's sense of completion as two related but
independent checks. QA schema versions were bumped to 1.43/1.12 (production) and 1.40/1.11
(preview). The regression suite passes 375 tests. No image generation or book approval was performed.

# Pocket-Sized Lion closure revision — 2026-09-12

Lewis asked for the final page to make the ending unmistakable. Attempt 3 is a saved human text
revision of attempt 2; attempts 1 and 2 remain preserved. Its final page now shows the seeds settling,
a tiny dandelion blooming beside the page-one mossy rock, Pip's smallest roar, Arthur's slow clap and
Leo's smile, followed by the closing line: “From then on, whenever the jungle heard a little roar, it
knew a dandelion was growing nearby.” This adds aftermath, shared reaction, a callback and a clear
read-aloud ending signal without changing the comic premise.

The revised candidate is awaiting human review at `http://127.0.0.1:8188/book-builder/create/book-20260912065334-b03404f8db`.
Gemma4's full text review and continuity audit are saved at
`output/books/book-20260912065334-b03404f8db/creator/stages/story/attempt-0003/editorial-review.json`;
both passed, including `specific_payoff` and `ending_closure`. No artwork was generated and no
approval was made.

# Art inspiration field — 2026-09-13 (latest)

Both creation forms gain an optional **Inspire the art** box (≤300 characters): anything the child loves right now — a show, a game, a toy ("she's loving demon hunters at the moment"). It is stored as `config.art_inspiration`, reaches the story writer (which may let it colour the visual bible and world details) and is injected into every art-style take with a fixed guardrail: *cute, colourful, age-appropriate storybook interpretation — gentle and friendly, never scary or dark*. Books already underway can add inspiration through the style step's Regenerate feedback instead.

Source: `assisted_store.config` (validation), `assisted_engine.text_step/image_inputs`, `assisted_ui` form fields. Verification: full pinned suite **397 tests pass**, including new coverage (config cap/trim, style prompts carry the inspiration on takes 1–4, plain prompts untouched, writer prompt receives it). ComfyUI restarted idle.

---

# Four art-style takes per book — 2026-09-13 (latest)

The art style anchors every later stage, so its stage now presents four distinct takes instead of one: attempt 1 is the story's planned direction; attempts 2–4 append seeded medium/mood emphases (bold flat cartoon, watercolour, crayon, storybook realism, minimalist, gouache — distinct per book via `config.seed`). After each fresh style attempt lands, `continue_style_variations` queues the next take until four candidates exist, so the filmstrip fills itself while the reader watches; any human decision (approve, regenerate with feedback, revise) stops the chain, and revision of an already-approved style also walks through four takes. The reader approves exactly one candidate as before.

Source: `assisted_engine.py` (`STYLE_TAKES`, `style_take`, `continue_style_variations`), `assisted_web.drive` auto-chain, `assisted_ui` style-step hint and "style option N of 4" progress. Verification: full pinned suite **394 tests pass**, including new `test_style_takes.py` (first attempt unmodified, takes 2–4 distinct and deterministic, prompt injection, chain stops at four and yields to human decisions). ComfyUI restarted idle; saved books unchanged — the current birthday book can use it via Revise this reference on its style.

---

# References revisable; cast before moments — 2026-09-13 (latest)

Lewis asked to change the art style a few generations in and found only pages could be reopened. Any approved reference (style, character, moment, prop, place, state) can now be reopened with **Revise this reference**; approving the replacement recomputes dependents from the stage reference graph and resets every approved downstream stage (moments, portraits, pages…) to pending, resuming generation from the next stage — old attempts stay visible for comparison, and Keep the original restores everything. Pages that supply an extracted reference stay protected; story and plan stay fixed. In moment books the canonical cast is now generated immediately after the art style, before the photograph restyles, so the characters exist before any scene that needs them.

Source: `assisted_revision.py` (revisable kinds, transitive `_dependents`, reference `finish` with invalidation), `assisted_plan.stages` ordering, `assisted_ui` reopen button for reference kinds with a downstream-regeneration warning. Verification: full pinned suite **391 tests pass**, including new reference-revision tests (style replacement invalidates approved portraits and resumes; keep-original restores downstream approvals; pending stages untouched) and updated moment-ordering tests. ComfyUI restarted idle; existing saved sessions unchanged (stage order is fixed at plan approval).

---

# From-a-moment books implemented — 2026-09-13 (latest)

Feature request: generate a book from a real day, not only from an idea. Implemented in the assisted creator and awaiting Lewis's first real try.

- Start screen mode toggle: **From an idea** (existing) / **From a moment**. Moment flow: upload 1–6 reference photographs, caption each, describe the day (a few cues suffice), then Generate. Uploads go to the new `POST /book-builder/creator/upload` (origin + creator-header checked, image validated, PNG-normalised, ≤25 MB, ≤4096 px, staged under `books/moment-uploads/`); `store.create` moves them into the session (`moment-src/moment_NN.png`) with SHA-256 pinned in `config.moment`. Uploads are single-use.
- Story stage: the local writer receives the description and every caption via a moment brief (real names/people/events stay recognisable inside a normal arc; souvenir tone, rereadable ending). Words only — the writer never sees pixels.
- After `style.png` is approved, each photograph gets a restyle stage (kind `moment`): photograph as Image 1, style as Image 2, existing Flux2 reference-latent graph — photo-real input restyled into the book look. UI shows the original photograph next to each candidate. Human approval required, Regenerate/Edit work as for any reference.
- Page-photo parity: a moment book has exactly one page per uploaded photograph (`config.page_count` is set to the photo count) — no invented pages, none left out. The cover is illustrated from the story as usual and may not use a moment. Plan validation enforces it: every numbered page must cite exactly one moment, each moment exactly one page, moments only on numbered pages, pages in photograph order. Rows are drag-and-drop reorderable (grip handle; arrows remain for accessibility) and the form shows the live "N photographs → N pages" note.
- Backwards compatible: `mode` defaults to `scratch`; all saved sessions, exports, the public story contract and candidate provenance unchanged. Export includes `moments/*.png` as extra approved assets (publisher still uploads cover/pages only).
- Verification: full pinned suite **385 tests pass**, including 10 new `test_moment_books.py` tests (submission validation, single-use intake, writer/plan/restyle text, photo-first reference wiring with approval hashes pinned only to approved stages, upload endpoint accept/reject). No inference run, no approvals made. ComfyUI was not running at handover — start with `python run.py start`, then open http://127.0.0.1:8188/book-builder/create.
- Watch for on first real run: whether one restyle attempt sufficiently matches each photo (feedback/Edit loops are the escape hatch), and whether the planner cites moments on the right pages.

---

# Milo accepted; Cloudflare Pages preview deployed — 2026-09-11 (latest)

Lewis completed and explicitly accepted **Milo and the Sun-Seeds**: "a successful finish of a book I'm happy with". Saved creator status complete, revision121, final page12; approved page11 is attempt4. Export: output/books/book-assisted-20260910213535-1b28c7aec5/export/. Preserve this accepted finish; the visual failures in earlier handovers describe older attempts. No generation, revisions or approvals are pending for this book.

Current requested work moved to the reader website in the parent onemorebook directory: replace Netlify/Render with Cloudflare Pages + Functions, retaining Supabase books/storage and stars. The code is pushed and the tested production preview is live at https://onemorebook.pages.dev. See ../DEPLOYMENT.md for the full handover. The custom domain remains on Netlify pending the Cloudflare zone and 123-reg nameserver change.

Before that pause, the empty Cloudflare Pages project onemorebook was created and the approved Milo export was imported into Supabase as 21df2344-4b8e-5f14-b198-03ac4112f6e4. All 13 public image hashes matched the approved export before status complete. Do not import it again to deploy the site. Its publication checkpoint is ../.local/publications/21df2344-4b8e-5f14-b198-03ac4112f6e4/. No existing books or real votes changed.

Pages API/frontend and local verification are ready. No Cloudflare Supabase secret, hosted deployment, domain/zone or DNS changes were applied. onemorebook.ai still serves the old Netlify site. Local preview: http://localhost:8788/book/21df2344-4b8e-5f14-b198-03ac4112f6e4 (start with pnpm run build:pages then pnpm run dev:pages from the parent directory). Source/backups/tests/browser screenshots are in ../.local/cloudflare-migration-20260911/.

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

# Migration verified and ready for Lewis — 2026-09-11


Final migration checks: 9,252 historical output files unchanged, 76 old page/image URLs pass, four assisted sessions unchanged through restart, real saved image pixels and fetched file match. The twelve-page draft passes the app backend's actual `UploadStorySchema.shape.story` validator. Live browser shows the new story with approval enabled; no decisions submitted. Queue empty. See `.local/migration-20260911/verification.json`.

---

# Current work — migration to onemorebook/generation — 2026-09-11T06:34:04.748804+00:00

Lewis returned and requested migrating book creation into `~/Workspace/onemorebook/generation`, keeping ComfyUI as its engine, and fixing the incomplete-story error. That instruction supersedes the previous pause and the earlier no-app-migration restriction for this generation directory. Assisted human review remains selected; no automatic full-book or Rainbow runs are authorized.

Source, all books (including legacy outputs), workflow copies, original story schema and historical work are now here. Compatibility symlinks retain old ComfyUI paths/URLs. Read `README.md` and `RESUME.md`. Start from here with `python run.py start`. The app frontend/backend are unchanged.

The user session `book-assisted-20260910213535-1b28c7aec5` failed in its first story attempt because Ollama returned `done:false` and truncated/repetitive JSON. Attempt 1 is preserved. After the reasoning-enabled writer compatibility fix, attempt 2 completed a twelve-page story, **Milo and the Sun-Seeds**, in 82.20 seconds, one local Gemma request. Contract validation passed, no formatting repairs. Current stage: story, awaiting_review. NO approval was made; let Lewis approve or revise it in the creator.

Resume duplicate-submission race fixed. Initial migrated suite: 312 tests pass; browser desktop/mobile checks pass. Official MCP stage generation, output saving and fetch verified from generation/. Detailed receipts/checks: `.local/migration-20260911/`. Do not repeat completed verification jobs. Read `RESUME.md` for exact IDs and remaining handover checks.

---

# Paused at Lewis's request — 2026-09-10T21:31:42.810887+00:00

The assisted creator is installed and ready for a first human test at http://127.0.0.1:8188/book-builder/create. Lewis is tired and explicitly requested stopping until tomorrow. Do not resume inference or development automatically; await his return. No real approvals have been made. The current ComfyUI queue at pause: {"queue_running": [], "queue_pending": []}. Interface/server stays available; do not stop the user's ComfyUI.

Previous implementation turn was progress: installed interface, 305 passing tests, live story/image/edit and restart evidence. This continuation checked current state: both saved sessions still await human review, no approvals, no running/pending jobs. Found one real race in assisted_web.launch: a new task key initially uses revision when job=None, while Resume uses attempt after drive allocates an intent. Resume during first validation can create a second driver. Added a regression test `AssistedAPITests.test_resume_during_first_validation_cannot_submit_same_attempt_twice` to test_assisted_creator.py; it uses only mocked MCP/temporary output (no real generation or approval). No production code was changed in this continuation.

NEXT TOMORROW: fix launch by allocating the intent synchronously under store.LOCK before computing a stable (session,stage,attempt) key, then ensure only one ACTIVE task owns it. Make done callbacks remove only their own task. Run the new regression, existing assisted tests, then reload only after checking the live queue. This is a pending safeguard, not a reason to rerun image experiments. Let Lewis test the interface and make the actual creative decisions. Existing first-test flow works; avoid clicking Resume while a live submission is already starting until this guard is installed.

---

# Assisted creator installed — 20260910T212850Z

The user's current milestone is ready to try at http://127.0.0.1:8188/book-builder/create. New top-level workflow: `childrens-book-generator-v2-assisted.json`; original automatic workflow and public schema unchanged. Source is `ComfyUI/custom_nodes/comfyui-book-builder/assisted_*.py` and `assisted_ui/`. Read `book-workflow-v2/assisted-creator/README.md` before changing/resuming it.

Human approves the story, private visual plan, style, every character/prop/place/state variant, cover and each page. Reject + feedback produces a fresh attempt; Edit uses the selected image as its source. All prior candidates, exact graph/seed/prompt/reference hashes and human decisions are saved. Local Gemma4 with thinking handles text; Flux2 Turbo 8 handles images. No real candidate has been approved by the assistant. Do not restart automatic book experiments or Rainbow. Long-term one-click automatic quality is NOT accepted. Earlier approved stages are currently locked; revising an approved story/design requires a new assisted session. Feedback is persisted and used in the requested retry, not automatic model training.

Verification: 305 unit/API tests pass, desktop/mobile browser interaction tests pass, new API workflow validates through official MCP, and live story plus isolated text-to-image/edit tests pause at awaiting_review. Fixture-only full export checks exact public contract and every approval. First streaming Gemma response disconnected; buffered JSON response works. A generated `characters//Bea` reference was normalized only against the exact declared name; raw response and correction retained. Markdown-fenced JSON replies are parsed using the existing strict single-document helper. Completed native image graphs are reused on interrupted attempts; completed candidate files recover if shutdown preceded state update.

Live story test: `book-assisted-20260910211408-f116aee5e9`, 2-page Nori/Bea draft, stage story, candidate attempt2, NOT approved. It resumed its saved reply after restart without more text inference. Isolated image test (hidden from normal book list): `book-assisted-20260910211942-97d65cced6`, stage style.png, candidate1 new riverside illustration (~33.5s), candidate2 sunset edit; neither approved. Job1 `8eac6cf5-d0eb-48b2-9288-d434fa445367`; final edit job `69b1f1c9-ea17-4dbb-9533-b2731279b8f6`. Both fetched; exact receipts/history saved under assisted-creator. Do NOT resubmit them. UI test dummy human decisions exist only in temporary unit/browser fixtures, not these real candidates.

ComfyUI latest PID1683259, launched with existing comfy-env, port8188. Final restart verified both sessions/candidate hashes survive and queue stays empty. See restart-verification.json, server.json, full-tests.log and ui-test-result.json. Original stage outputs, Glimmer-Shell work and accepted old book remain intact. Official MCP is still pinned and working.

---

# Priority changed — 20260910T205131Z

# Active work: interactive assisted book creator

The user changed the immediate approach: build a local book-creator HTML app alongside the workflow. Generate linearly and pause for human approval after story, reference assets (style, characters, props, locations), cover and each page. Reject with feedback causes regeneration; retain all attempts, allow choosing earlier candidates, persist decisions/progress through shutdown. Automatic image/editorial retry experiments are stopped. Long-term automation remains a future goal, driven by this real feedback. Do not start a full automatic book or Rainbow.

Implementation direction: local /book-builder/create UI + durable per-session state and decision history; separate ComfyUI jobs for each stage, submitted through official MCP from a background coordinator. Never block ComfyUI waiting for human input. Schema checks remain mandatory; human approval must be explicit and distinct from automatic QA. Public story JSON stays exactly compatible with onemorebook. New assisted workflow at top of workflow library, collision checked. No original overwritten. No work in onemorebook app.

Before this pivot, three isolated Flux tests completed and are saved in foundation-contact-20260910. Lewis explicitly accepted contact-page3-seed2_00001_.png as perfect for Luna reaching/getting the shell in the crevice, and said results look much better. Prior assistant floating-shell rejection was too strict. Other two tests are not explicitly accepted. Cheek-specific optional question remains unanswered; do not infer approval. Full-book generation remains paused.

Old test IDs: 906117e0-e490-4fbc-a7b0-344997bbf5f2; b1e07f5d-6acb-46a5-a2ed-1c23c5b052ef; e673e0e7-1879-4330-a4ae-320a49c3be35. All completed/fetched/native graph verified; do not repeat. Official MCP works. Queue and Ollama empty at pivot. Production image compiler and QA unchanged. Experimental v19 compiler and QA1.42 changes remain under foundation-contact-20260910/candidate only; do NOT copy whole candidate into production. The reviewer routing candidate's final test has a fixture KeyError ollama_url, not an installed failure. Reviewer live probes: Gemma misreads accepted shell location; local Qwen3.5 observer + Gemma action comparison accepts it and rejects wrong-action control. No more reviewer tuning now.

---

# MCP migration completed — 20260910T202219Z

Official Comfy-Org `comfy-mcp==0.10.0` / `comfy-cli==1.20.0` replaced the old artokun MCP. Codex server is `comfy-mcp`; executable `mcp/official-env/bin/comfy-mcp`, `COMFY_BIN=mcp/bin/comfy`, explicit localhost8188/workspace. Old `comfyui` config entry and npm server package removed. Restart Codex/new session to refresh native tool schemas; `mcp/client.mjs` and `node mcp/call.mjs` already use official tools. Read `MCP-SETUP.md` and updated `AGENTS.md`; actual39 tool schemas in `mcp/official-migration/tools.json`. Old experiment scripts use incompatible tool names; port before running, preserve graph seeds/results and never automatically repeat completed jobs.

Verified real configured stdio handshake, system/model/node discovery, and book API graph validation (zero errors/warnings, no paid nodes). Image-copy smoke job `164e2c59-c454-40c2-ab15-7776f451f5a4` completed and fetched pixels match source; no model inference. Workflows/schema matched prior checkpoint. ComfyUI remained running PID1611360, queue empty; existing book gallery reachable. No book, model or custom-node changes during migration. Backup path: `mcp/official-migration/backup.txt`; detailed verification there. The book-generator goal remains paused/unaccepted; resume isolated foundation tests only when continuing that work. Rainbow remains deferred.

---

# Latest status — 20260910T193156Z

First foundation fix batch saved. Story reasoning fix installed and ComfyUI reloaded; 282 installed tests pass. Image compiler trials remain experimental: shorter prose fixed duplication in one matched test but prop contact still fails. Full books remain paused; children's generator is not accepted; Rainbow and Qwen image work remain deferred. See `book-workflow-v2/RESUME.md` and `foundation-fixes-20260910/REVIEW.md` for exact completed jobs, evidence and next isolated checks.

---

# ACTIVE FIXES — 2026-09-10T19:06:53.875959+00:00

The user requested work on the audited fixes. Candidate changes and isolated test evidence are in `book-workflow-v2/foundation-fixes-20260910/`. Full-book generation remains paused. The audit below is historical; no new book or repeated four-case audit submission is authorized.

---

# ComfyUI tasks — 2026-09-10T18:26:06.367907+00:00

1. **Children's book generator first; not accepted. Full-book runs are paused.** The user requested a systematic documentation/prompt/workflow audit and explicitly authorized targeted image generation. Four isolated tests are now complete; no automatic retries or new full-book run were submitted.
2. Review the evidence in `book-workflow-v2/audit-20260910/REVIEW.md` and the comparison: http://127.0.0.1:8188/book-builder/books/consistency-tests/flux-foundations-20260910/index.html
3. Before further work, read `book-workflow-v2/RESUME.md`, inspect live queue and saved receipts. Do not resubmit the four completed cases or the cancelled book. Preserve exact seeds and native graphs.
4. Current findings: basic Flux2 wiring checks pass; simple three-character scenes avoid duplicates on one seed; shared-sheet vs separate-portrait scale tradeoff remains; Gemma misses a known two-mouth defect; local face edit partly succeeds but changes expression. Active Gemma story writing and production story review have thinking disabled. No production code/schema/workflow changes were made during this audit.
5. Optional user preference on shared cast sheet vs separate portraits is pending. No response is acceptance. Continue toward validated building blocks; do not infer authorization to restart full-book validation.
6. Keep Qwen image experiments and Rainbow Paint by Numbers Image + Video Gen deferred until Lewis is happy with the book generator. The Rainbow request is preserved in the historical task files.

Goal tools remain paused. Local inference only. No subagents authorized. Preserve the accepted older candidate `book-2026090831-0625d03d46/renders/44539e3997c0/book.html`, original workflows, schema and all rejected attempts.
Previous handovers: `book-workflow-v2/audit-20260910/handover-before/` and `book-workflow-v2/flux-turbo-book-20260910/scene-continuity/staging-recovery/historical-TASKS.md`.

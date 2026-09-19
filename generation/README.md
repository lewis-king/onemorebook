# Book Creator

Create books locally, reviewing each step before the next one runs. This directory owns the generation code, editable workflow copies, story contract, saved books and development records. ComfyUI and the model installations remain in `~/comfy` and supply the rendering engine.

## Start here

```bash
cd ~/Workspace/onemorebook/generation
/home/lewis/comfy/comfy-env/bin/python run.py start
```

Open **http://127.0.0.1:8188/book-builder/create**. The command starts the existing ComfyUI with its Python environment, or reuses it if the creator is already available. It does not start a book or submit any generation jobs. Logs are in `.local/comfyui.log`.

```bash
/home/lewis/comfy/comfy-env/bin/python run.py status
/home/lewis/comfy/comfy-env/bin/python run.py check
```

### After a reboot

Run this single command from any terminal:

```bash
cd ~/Workspace/onemorebook/generation && /home/lewis/comfy/comfy-env/bin/python run.py start
```

Then open:

```text
http://127.0.0.1:8188/book-builder/create
```

The launcher starts ComfyUI and the local Book Creator together, reuses an already-running instance, and records its PID and log in `generation/.local/`. Use `status` to check whether it is running and `check` to verify the migrated paths and pinned MCP installation. Do not start a second `main.py` process on port 8188.

The same creator is available when ComfyUI is started normally with `../comfy-env/bin/python main.py` from its checkout. The app frontend/backend do not need to be running.

## Create and review

1. Click **Generate**, or first add an idea in the single optional box. It can describe the subject, tone, characters or illustration style. The default audience is shared reading at **ages 4–7**.
2. Review the story, then the private illustration plan.
3. Approve each style, character, object and location reference, then the cover and each page.
4. **Approve & continue** records your selected attempt and starts the next stage. **Regenerate** creates another candidate, with optional feedback. **Edit this image** changes the selected image while preserving unaffected details.
5. Choose an older attempt whenever it is better. Every attempt and your feedback stays saved.
6. To revisit an approved illustration, select its page (or the cover) in the sidebar and click **Revise this page**. You can regenerate or edit it, then **Approve replacement & return** to where you left off. **Keep the original & return** restores the prior approval while retaining your new attempts. Finish any running generation or existing revision first. Story and shared reference approvals remain fixed.

Each scene keeps a saved prompt for fresh generations. Its first preparation uses the approved page prose and current reference designs. **Regenerate** with empty feedback reuses it with the next attempt's seed; feedback revises it for subsequent attempts. Image edits remain separate from the full scene prompt. The single **Prompt** section beneath the candidate shows what Regenerate will use, or the exact prompt rendering while a job runs. **Edit prompt** lets you supply the complete prompt directly. Expand **Attempt details** for the selected candidate's model, reference images and original prompt when it differs. Choosing an older attempt does not replace the saved regeneration prompt. Earlier plans, attempts and approval records stay intact.

While a new attempt runs, **Prompt** shows that job's actual model and reference images as soon as preparation finishes. The previous preview is labelled as a saved attempt, with its original inputs kept under its own details. This distinguishes the image still on screen from the generation in progress.

After every stage is approved, the session's `export/` folder contains `book.html`, `story.json`, page/cover images, a contact sheet and import instructions. If you revise a completed book, approving the replacement creates a new version under `exports/<revision>/`; **Read your book** opens the latest version, and earlier exports remain available at their original URLs. The public story JSON follows [the original app contract](contracts/story.schema.json); production/reference data lives in separate files. When the final page is approved, **Publish to library** runs the hash-checked Supabase publisher from the creator and shows the public reader URL. Uploads are resumable and retain a local publication log; a failed upload can be retried from the same button.

New book IDs use `book-<timestamp>-<hash>`. Existing `book-assisted-…` creator URLs open the same saved book and switch to the shorter URL in the browser. Historical output directories, image links and generation records are preserved.

## Assisted or YOLO review

Every new book chooses a review mode on the start form. **Assisted** (the default) is the flow above: you approve every step. **YOLO** hands each candidate to a local AI judge (the configured review model, Gemma 4 by default) which checks the story/plan drafts, ranks the four art-style takes, and reviews every reference, cover and page against its brief, the approved character designs and — for from-a-moment books — the original photograph. Approved stages advance automatically; rejected ones regenerate with the judge's corrections, up to three retries per stage, then the stage parks for your decision. The judge fails closed: any uncertainty or error parks the stage rather than approving. You can switch modes mid-book with **Pause the AI judge / Let the AI judge finish** in the sidebar, and revise anything after the book completes — revising a page re-exports a new version as usual. Every automated decision is recorded with `source: 'yolo'` alongside human decisions, a `judge-report.json` is saved in each judged attempt, and the export manifest records the book's `approval_mode`.

## Story craft and length

The creator chooses its voice, approach and visual direction to suit the optional idea, or invents freely when it is blank. The books Lewis recommended inform craft principles; they are not categories or templates. Rhythm, humour, emotional credibility, coherent actions and satisfying endings stay in the internal guidance.

For new books started in the simple form, the writer starts from **12 illustrated story pages** and can choose **8–16**, plus the cover, when a shorter or longer story works better. This happens during planning. This is an editorial range for digital reading screens, not a print-book pagination rule. Each candidate keeps its own length. Approval selects that exact manuscript, and planning/export follow its actual page count. Existing books and explicit fixed-length workflow inputs retain their lengths.

Story review shows the candidate's actual page/word counts and a few optional questions. These support your judgment, not an automated quality score. Local Gemma plans and revises within its reasoning-enabled request; it does not independently certify the story. Your approval still controls every stage.

Saved prompt versions remain available: legacy configs keep their previous instructions, `picturebook-1` preserves explicitly selected creative presets, and new simple-form books use `picturebook-2`. Research, edition page counts and evidence limits are in [Story craft research](docs/STORY-CRAFT-RESEARCH.md).

## Files

| Path | Contents |
| --- | --- |
| `comfyui-book-builder/` | Python nodes, creator web routes/interface, prompts and tests |
| `comfyui/workflows/` | Editable copies of the book workflows, including the assisted starter |
| `comfyui/childrens-book-generator.json` | Your existing original workflow, preserved |
| `contracts/story.schema.json` | Original onemorebook public contract |
| `output/books/` | Existing and new books, references, attempts, feedback and exports |
| `output/codex/books/` | Older legacy results, preserved |
| `book-workflow-v2/` | Full development history, checkpoints and experiment records |
| `mcp/call.py` | Adapter to the pinned official local Comfy MCP |
| `.local/` | Server log/PID record, migration checks and verification results |

Outputs, historical experiments and local machine settings are ignored by Git; they remain on disk. Source, workflow copies and contracts can be versioned with the app. Back up `output/` and `book-workflow-v2/` as well as the Git repository if moving machines.

## Resume after shutdown

Run `python run.py start`, reopen the saved book, and use **Resume saved step** if needed. Resume checks saved candidates, queue and history before submitting work. A completed stage does not render again. An interrupted sampler restarts from its saved seed and graph. An exhausted text request can be retried with **Regenerate**; its prior response is kept.

The ComfyUI starter workflows create a **new** session each time they run. The new `childrens-book-generator-v2-assisted-storycraft` copy includes the story/art choices and a 4–7 default; the original assisted starter remains available with its saved values. Resume saved sessions in the creator instead.

## Local models and approvals

Text uses local `gemma4:31b` with reasoning enabled. Art uses the existing local Flux2.dev + Turbo LoRA, eight steps. Technical recovery for interrupted/invalid JSON replies is limited to two persisted calls per requested attempt; it cannot approve a story or image. Schema validation remains mandatory and creative approval is yours.

Scenes use up to six input reference images, following [BFL's recommendation for FLUX.2.dev](https://docs.bfl.ml/guides/prompting_editing_overview). The visible characters share one cast image, leaving five images for props/places (at most one location). Scenes without characters can use all six slots for props/places. This is a per-scene budget; a book can have more reusable assets overall.

The private planner also tracks **assembled or changed props** across the whole manuscript: a tower built from pots, a filled basket or a repaired toy. Each `prop_state` records its source props, complete appearance and the pages that show it. The workflow generates and pauses for approval of the components first, then the assembled reference using those component images. Relevant scenes use that complete reference instead of also receiving loose copies of its parts. A later mention of one part retains the established assembly and support; scene prompt preparation receives earlier story events as context.

Validation checks dependencies, the page schedule and reference routing. These checks cannot guarantee that the planner notices every meaningful change or that an image renders correctly; your review remains essential. An explicitly requested correction to an existing book can add a reference review step using an earlier approved scene as its visual source. The original approved plan and attempts remain unchanged; a separate saved amendment supplies the corrected scene references and export plan.

The Gemma writer requests JSON through the prompt and validates it locally. This avoids the thinking-to-grammar restart involved in the interrupted Ollama 0.30.8 reply. See [Ollama thinking](https://docs.ollama.com/capabilities/thinking), [structured outputs](https://docs.ollama.com/capabilities/structured-outputs), and the [pinned server implementation](https://github.com/ollama/ollama/blob/v0.30.8/server/routes.go). This is a local compatibility workaround; reasoning remains enabled and incomplete replies are never treated as complete drafts.

## Connection and installation

Defaults point at the existing `~/comfy` installation. If it moves, copy `comfy.local.example.json` to `comfy.local.json` and adjust the paths. The MCP installation stays pinned to `comfy-mcp==0.10.0` / `comfy-cli==1.20.0`; the creator calls it from its own Python environment. No npm bridge is needed by the creator.

This migration installed these filesystem links:

- `~/comfy/ComfyUI/custom_nodes/comfyui-book-builder` → this directory's `comfyui-book-builder/`
- `~/comfy/ComfyUI/output/books` → `output/books/`
- `~/comfy/ComfyUI/output/codex/books` → `output/codex/books/`
- The assisted workflow in the ComfyUI library → `comfyui/workflows/childrens-book-generator-v2-assisted.json`
- `~/comfy/book-workflow-v2` and `~/comfy/TASKS.md` → their moved copies here

Existing saved book URLs and historical absolute paths continue through these links. Other ComfyUI output types and original workflow library files remain in place. `tools/migrate_from_comfy.py` records the one-time migration; do not rerun it after completion. Its hash inventory is in `.local/migration-20260911/`.

## Tests

```bash
cd ~/Workspace/onemorebook/generation
~/comfy/comfy-env/bin/python -m unittest discover -s comfyui-book-builder/tests -q
```

The suite covers the public contract, saved approvals/feedback, reference integrity, export, path aliases, bounded writer recovery and concurrent Resume submissions. Full automatic quality experiments and Rainbow Paint by Numbers remain deferred while we use the assisted creator.

### New-book defaults and editorial review

New books start from a 14-page target and may settle anywhere from 8–16 pages when the story needs it. The writer and Gemma4 editorial gate require an earned ending with a visible consequence and specific payoff, plus a distinctive, readable cast; failed automatic reviews are retried with their concrete issues. Existing saved books/configurations retain their original settings.

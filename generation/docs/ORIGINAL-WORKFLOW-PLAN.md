# Children's book generator: revision 2.1

The generator keeps the original dependency order but executes it automatically: outline and story, common style, every character reference, cover and pages, then the complete book. The original workflow and earlier outputs remain intact. New output is under `ComfyUI/output/books/`.

## Required contract

The public document is exactly the original `id`, `pages`, `metadata` schema in [story.schema.json](book-workflow-v2/story.schema.json). Page fields remain `text`, `pageNumber`, `imagePrompt`, `charactersPresent`, `isMainCharacterPresent`. Metadata fields and character-name arrays retain their original casing and types. Automation and quality information live in separate documents.

The app at `/home/lewis/Workspace/onemorebook` is used only to verify its actual upload validator. Delivery remains manual JSON/image import. No app migration or application changes are included.

## Production flow

1. **Plan a story with a reason to turn the page.** A local writer outlines a concrete goal, problem, purposeful attempts, surprise and earned resolution. An editorial call checks cause and effect, character agency, continuity and cast constraints before prose is written.
2. **Write and edit the whole book.** Generate the exact public story plus a private cast/style plan. Check structure and every page's prose/image agreement. Repair rejected drafts. Preserve an accepted story across image-setting changes.
3. **Approve canonical references.** Render an empty style image, followed by one plain-background portrait per named character. Fix species, appearance, clothing, footwear and relative physical sizes. Review every reference before using it.
4. **Illustrate each scene.** Default to local Flux2.dev using the canonical portraits for the characters named on that page. Use the common style reference when a character slot is free. Never chain the previous page's identity into the next.
5. **Check and repair artwork.** Count visible figures independently of the brief, compare each identity and outfit to its portrait, and check scene/action, anatomy, unwanted lettering and style. Compare measured sizes where pose and perspective permit. Retry rejected candidates with corrections and fresh deterministic seeds. Eligible isolated size defects use a measured cutout, uniform resize and masked background repair, followed by another full review.
6. **Export approved deliverables.** Save exact story JSON, every character, cover and numbered page artwork, readable HTML/text, contact sheet, import mapping and optional PDF. Completion requires approvals tied to the exact story and image hashes.

## Controls and recovery

Default book: ages 4–6, twelve pages plus cover, up to four named characters and at most three visible in one scene. Leave the idea blank to invent a new story, or supply a premise. Randomized seeds make new books; the same seed and settings resume approved work. Render settings create separate renditions. Five attempts are allowed per story/outline and per asset; an unresolved failure stops without publishing a completed book.

All failed candidates, seeds, prompts, editorial notes, visual observations and repair measurements are retained in `quality/`. A reviewer interruption does not discard an already rendered candidate. Existing files are never replaced by different content.

## Evidence and acceptance

The original Qwen-based twelve-page run completed its files but failed visually: missing, merged and duplicated characters. Its [visual review](book-workflow-v2/runs/2364a254-600e-48f5-bff5-58680b28b807/visual-review.md) remains the baseline.

Controlled native-model comparisons retained three distinct identities with Flux2 where Qwen merged the animals. Prompt-only size instructions and a size montage were insufficient. A measured SAM cutout plus masked Flux2 background repair corrected an oversized fox while preserving the other characters. Grounding DINO independently measured the bad fox at 1.86 times its specified proportion and the repaired fox at 1.03 times. The current calibrated gate rejects the former and accepts the latter.

Twenty-five automated checks cover the public contract, character routing, native dependency order, safe/exclusive writes, exact-byte approval, retries, interrupted-review resume, export gates, geometry and masked repair. Complete-book verification is still in progress; successful code tests and individual-image calibration alone are not a completed-book acceptance result.

Current implementation: [node pack](ComfyUI/custom_nodes/comfyui-book-builder/README.md). Research and failures as well as successes: [consistency investigation](book-workflow-v2/consistency-research/README.md). User instructions and final run status: [book-workflow-v2](book-workflow-v2/README.md).

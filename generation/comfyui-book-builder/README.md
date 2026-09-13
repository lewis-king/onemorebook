# Children's Book Builder 2.1

Local ComfyUI nodes for story planning, editorial review, reference-based illustration, visual checks, bounded repairs and export. The public story schema is unchanged. User instructions and actual run records are in [book-workflow-v2](../../../book-workflow-v2/README.md).

## Execution

Four visible stages expand into native ComfyUI nodes. Each stage waits for the previous stage's approved output. No manual disabling, queue recursion or image reloading is required.

1. Write a private outline; independently check its causal plot and repair rejected outlines before prose.
2. Generate the story and private production plan. Validate the exact public schema, page sequence, cast and main-character flags. Review the narrative and each page's prose/image correspondence. Save the accepted story before rendering.
3. Generate an empty style reference and a plain-background canonical portrait for every character. Portraits use permanent appearance only; behavioural notes and later story marks cannot define the baseline. Each reference must pass visual review.
   In from-a-moment books, every uploaded photograph is then restyled into an isolated storybook reference: the photograph is the only image input and the approved art style is conveyed in words, because a scenic style sample offered alongside kept donating its own scenery into the memory. The original appears beside each candidate until you approve the restyle.
4. Render the cover and every page using only the required canonical portraits. Never use the preceding page as the identity reference.
5. Review each candidate: blind figure inventory, identities and outfits against portraits, requested scene/action, anatomy, style, unwanted lettering and relative size. Uncertain or rejected artwork is not published.
6. Retry with corrections and a different deterministic seed. Eligible isolated size defects use measured cutouts, uniform resizing and masked Flux2 background inpainting. Repeated action failures can use an authored pose diagram with the previous scene; these desired coordinates never drive physical resizing. The diagram has two bounded planning attempts and is saved for resume. Recheck every resulting image.
7. Export only when the exact story and every required asset have matching approvals and SHA-256 records.

Defaults allow five attempts per outline/story and five per asset, including repairs. Exhaustion stops with the asset name and reasons; it never exports an unresolved book as complete. Writer transport failures have three bounded retries. An interrupted visual review preserves its image for review on resume.

## Local models

- Writer: `gemma4:31b`, via Ollama chat with the schema in both the request and prompt. Gemma uses ordinary structured output; Qwen3.5 remains selectable with thinking enabled. Existing saved books retain their original writer settings for resume.
- Reviewer: `gemma4:31b`, with separate calls and structured evidence. Reviews remain fallible.
- Renderer: `flux2_dev_fp8mixed.safetensors`, `mistral_3_small_flux2_bf16.safetensors`, `flux2-vae.safetensors`; native reference latents, Euler, 28 steps, guidance 4, 1024 square.
- Qwen Image/Edit 2509 remains selectable. Its style stage uses the matching eight-step Lightning LoRA; edit uses the base model at 40 steps/CFG 4.
- Geometry: `models/grounding-dino-tiny/`, the official IDEA-Research detector, runs on CPU. Its 689 MB safetensors checkpoint was added using the already installed Transformers library.
- Cutouts: the existing `models/sams/sam_vit_b_01ec64.pth`, also on CPU.

Ollama models unload after each call. Before review, ComfyUI model memory is freed. Native ComfyUI manages image-model offloading. These nodes use no hosted language or image API.

## Scale and repair limits

The detector queries all visible subject kinds together. Ambiguous species labels retain their boxes for comparison of actual detector crops against canonical portraits; uncertain or overlapping assignments cannot drive resizing. The vision reviewer checks pose, visibility, depth and interactions. Comparable whole-body measurements are checked against private cast heights, allowing ordinary illustration proportions while rejecting large drift. Kneeling, occluded, held or interacting characters require additional checks before any resize.

A repair requires otherwise correct cast, identity, appearance and scene, with one independent character having a size defect. SAM refines detector boxes. The character is uniformly reduced with its feet staying on the same ground line. Flux2 samples only the exposed background; a final pixel composite restores unmasked pixels. Unsupported geometry falls back to a fresh canonical render. Language-model-generated boxes failed calibration and never drive resizing.

Flux scenes now default to a single shared cast sheet for two or more visible characters with explicit heights. This preserved distinct identities and substantially better proportions on a cover and an action-scene comparison; whole-book verification is still in progress. Single-character scenes use a portrait and style reference. The older option to add a size guide alongside individual portraits stays off. A shared seed alone is not an identity mechanism.

## Contract, output and resume

`story.json`, `book.json` and the story node's STRING output retain the original `id`, `pages` and `metadata` document, including exact camelCase fields, name arrays and presence flags. See [story.schema.json](../../../book-workflow-v2/story.schema.json). Outline, production, measurements, references, retries and approvals stay separate.

New books live under `ComfyUI/output/books/book-<seed>-<story-settings-hash>/`, with renditions in `renders/<render-settings-hash>/`. Earlier `output/codex/books/` results remain intact.

| File | Purpose |
| --- | --- |
| `story.json`, `book.json` | Exact app-facing story |
| `style.png`, `characters/<id>.png` | Approved references |
| `cover.png`, `pages/page-NNN.png` | Approved illustrations |
| `pages/page-NNN.txt`, `story.md` | Exact prose |
| `book.html`, `contact-sheet.png` | Readable book and overview |
| `manifest.json`, `asset-plan.json` | Completion, production, prompts, references and seeds |
| `render-settings.json` | Renderer/review settings and model-file metadata |
| `quality-report.json`, `quality/` | Approvals, candidates, hashes and repair evidence |
| `IMPORT-TO-ONEMOREBOOK.md` | Manual import and character-file mapping |
| `book.pdf`, `layout/` | Optional raster illustrated edition |

Fixed seed and unchanged settings resume approved work. New seeds create new books. Changed image settings create a new rendition without rewriting the accepted story. Different content never overwrites existing files. The optional `story_json` input preserves an edited public story and creates a separate production plan; it must still pass review.

## Verification

Run `./comfy-env/bin/python -m unittest discover -s ComfyUI/custom_nodes/comfyui-book-builder/tests -v` from the workspace root. Tests cover schema preservation, cast routing, dependency order, safe paths, exact-byte approvals, bounded retries, outage resume, export gates, measured scale and masked repair graphs. Actual image calibration and book runs are recorded in `book-workflow-v2/consistency-research/`.

Primary references: [ComfyUI Flux2](https://docs.comfy.org/tutorials/flux/flux-2-dev), [Ollama structured output](https://docs.ollama.com/capabilities/structured-outputs), [Grounding DINO](https://huggingface.co/IDEA-Research/grounding-dino-tiny), [Segment Anything](https://github.com/facebookresearch/segment-anything).

# OneMoreBook

A bedtime-story library built with SolidJS, Cloudflare Pages Functions and Supabase. The public site browses completed books, displays their illustrations and accepts stars. Book creation runs separately on your own machine through the assisted creator.

The Cloudflare migration is prepared locally. **It has not been deployed.** See [deployment and current status](DEPLOYMENT.md) before publishing.

| Directory | Purpose |
| --- | --- |
| `frontend/` | SolidJS/Vite library and responsive book reader |
| `functions/`, `cloudflare/` | Cloudflare Pages API for reading books and adding stars |
| `generation/` | Local assisted creator, ComfyUI workflows and saved books; [setup](generation/README.md) |
| `scripts/` | Explicit publication of approved local exports to Supabase |
| `backend/` | Preserved Express backend; not required by the Pages website |
| `docs/legacy-hosting/` | Previous Netlify/Render configuration for rollback |

## Local preview

Use Node.js 22 or newer and pnpm. From the repository root:

```bash
pnpm install --frozen-lockfile
pnpm --dir frontend install --frozen-lockfile
cp .dev.vars.example .dev.vars  # only when .dev.vars does not already exist
# Set SUPABASE_ANON_KEY in .dev.vars using your existing Supabase configuration.
pnpm run build:pages
pnpm run dev:pages
```

Open http://localhost:8788. It runs the static site and API in Cloudflare’s local runtime, connecting to the existing Supabase project. Clicking a star in this preview changes a real vote. Automated tests mock writes.

For frontend hot reload, `pnpm run dev` runs Vite on http://localhost:5173 with `/api` proxied to the local Pages runtime on port 8788. Stop an already running preview first to free that port.

## Verify and publish

```bash
pnpm run check:pages
```

This checks the API, type-checks/builds the frontend and compiles Pages Functions locally. It does not deploy or import books. The Supabase key belongs in server settings, never a `VITE_` variable.

Deployment and book publication are separate, explicit actions described in [DEPLOYMENT.md](DEPLOYMENT.md). A Git push does not deploy the current Direct Upload Pages project.

## Book creator

```bash
cd ~/Workspace/onemorebook/generation
/home/lewis/comfy/comfy-env/bin/python run.py start
```

Open http://127.0.0.1:8188/book-builder/create. Human approval remains part of this workflow. Existing attempts, reference images and immutable exports stay local. See [generation/README.md](generation/README.md).

After a reboot, the same command starts both the local ComfyUI engine and Book Creator, or reuses them if they are already running. To check the setup without starting anything:

```bash
/home/lewis/comfy/comfy-env/bin/python ~/Workspace/onemorebook/generation/run.py status
/home/lewis/comfy/comfy-env/bin/python ~/Workspace/onemorebook/generation/run.py check
```

# OneMoreBook frontend

SolidJS, TypeScript and Vite. The website lists completed Supabase books, opens the illustrated reader and accepts stars. Creation/upload screens are excluded from public routing; use the local assisted creator instead.

From the repository root, run `pnpm run dev` for Vite hot reload at http://localhost:5173 and the local Cloudflare API on port 8788. `pnpm run dev:pages` serves an already built production preview at http://localhost:8788.

All browser API calls use `/api` on the same origin. Credentials are runtime secrets in Pages Functions, not frontend environment variables. `pnpm --dir frontend build` runs TypeScript checks and writes `frontend/dist`.

Deploy from the repository root so Wrangler includes `functions/` as well as the static build. See [DEPLOYMENT.md](../DEPLOYMENT.md). Supabase continues to serve image content directly.

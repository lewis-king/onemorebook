# Legacy Express backend

This TypeScript/Supabase backend is preserved for reference and rollback. The Cloudflare Pages website uses `../cloudflare/api.mjs` and `../functions/` instead and does not need a Render server.

The local book publication script can read the existing private `backend/.env` for `SUPABASE_URL`, `SUPABASE_ANON_KEY` and `SUPABASE_STORAGE_BUCKET`. Do not commit that file.

To run the legacy backend intentionally, install its dependencies and use `pnpm run dev:backend` from the repository root. It is no longer part of the default development/build commands. The old Render configuration is archived under `../docs/legacy-hosting/`.

See [deployment instructions](../DEPLOYMENT.md) for the current website architecture.

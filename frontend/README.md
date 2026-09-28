This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Environment

Copy `.env.example` to `.env.local` and fill in the two Supabase values:

```bash
cp .env.example .env.local
```

```
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
```

Get both from the Supabase project dashboard: **Project Settings → API**.
The anon key is safe to expose in the browser — it identifies the
project, not a user.
**These are optional.** Without them the app builds and runs fine — `isAuthConfigured`
is false, `supabase` is null, and the sign-in UI says so plainly instead of erroring
(`src/lib/supabase.ts:25-27`). The studio itself needs no login at all.

Missing config *used* to `throw` at module load, which took down every page because the
root layout imports `AuthProvider`. That is fixed, and `scripts/check-frontend.sh`
builds with no Supabase config on purpose so it stays fixed.

## Running it

**Don't start this on its own.** The studio is useless without the API that computes
every number — `npm run dev` gives you a UI whose requests go nowhere. Start both:

```bash
cd ..
./scripts/keystone-local.sh            # API + studio on http://127.0.0.1:3000/studio
./scripts/keystone-local.sh --offline  # no AI at all: the engine + all 56 designs, $0
```

On macOS the **Keystone** Desktop shortcut does the same thing (`./setup.sh` builds it).

The launcher deliberately runs a **production build**, not `next dev`: the dev server's
hot-reload socket once failed to connect and silently took hydration down with it — the
page rendered, you could type, and the Generate button stayed dead forever. Use
`npm run dev` when you are editing this code, not when you want to use the app.

`NEXT_PUBLIC_API_URL` is inlined **at build time**, so a bundle built against a
different API address is stale even when every source file is older than it. The
launcher records the address next to the build and rebuilds when it changes.

## Deploying

There is nothing to deploy to. **Keystone runs on each person's own machine** (#24,
2026-09-12) — it is not a hosted website. The council runs on the Claude Code CLI, i.e.
on your own subscription with nothing billed, and a browser cannot reach a CLI on the
visitor's laptop, so a server calling it would be one account answering everybody.

*(This section used to be `create-next-app`'s stock "Deploy on Vercel" boilerplate,
which was wrong three times over: not Vercel, not Cloudflare, not deployed.)*

## Learn More

Read `AGENTS.md` in this directory first — this is **not** the Next.js most references
describe, and the guides in `node_modules/next/dist/docs/` are the current source.

- [Next.js Documentation](https://nextjs.org/docs)

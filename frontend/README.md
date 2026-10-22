# Indeed Job Scraper — Frontend

Vue 3.5 single-page app for the read-only Indeed job scraper API. It shows the
master job list, one job's full detail, cookie-session health with the scrape
run history, and the application ledger with the sent messages.

The UI is a **read-only** console. It never writes to the scraper state
directory.

---

## Requirements

| Tool | Version used |
|---|---|
| Node.js | v26.10.0 |
| pnpm | v12.6.0 (`/home/hyperion/.local/bin/pnpm`) |
| Backend | FastAPI on `http://127.0.0.1:8001` (see `../docs/api-contract.md`) |

## Commands

Run all commands from this directory (`frontend/`):

```bash
pnpm install       # install dependencies
pnpm type-check    # vue-tsc --noEmit  (TypeScript strict mode, no `any`)
pnpm build         # type-check + production build into dist/
pnpm dev           # Vite dev server on http://127.0.0.1:5173
pnpm preview       # serve the production build on http://127.0.0.1:4173
```

If `pnpm` is not on your `PATH`:

```bash
/home/hyperion/.local/bin/pnpm install
/home/hyperion/.local/bin/pnpm type-check
/home/hyperion/.local/bin/pnpm build
/home/hyperion/.local/bin/pnpm dev
```

## Dev server and the API proxy

`vite.config.ts` proxies `/api` → `http://127.0.0.1:8001`, so the browser only
ever makes same-origin requests and no CORS setup is needed in development.

The client itself never talks to `8001` directly: `API_BASE_URL` defaults to
`/api`, so the browser calls `/api/jobs` on `http://127.0.0.1:5173` and Vite
forwards it to the backend on `8001`.

```ts
server: {
  host: '127.0.0.1',
  port: 5173,
  strictPort: true,
  proxy: {
    '/api': { target: 'http://127.0.0.1:8001', changeOrigin: true },
  },
}
```

The backend does **not** need to be running for the dev server to start — the
SPA shell renders either way, and each view shows its error state with a retry
button until the API comes up.

Two environment variables are available:

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8001` | Where the dev proxy forwards `/api` |
| `VITE_API_BASE_URL` | `/api` | The path the client requests from the browser |

```bash
VITE_API_PROXY_TARGET=http://127.0.0.1:8931 pnpm dev
```

## Routes

| Path | View | What it shows |
|---|---|---|
| `/` | `JobsView` | Master job list: search, filters, sorting, pagination |
| `/jobs/:shortId` | `JobDetailView` | One job, every field from the contract |
| `/session` | `SessionView` | Session presence / status / expiry + scrape run history |
| `/applications` | `ApplicationsView` | Ledger table, status summary, sent messages |

## Project layout

```
frontend/
├── index.html                  SPA shell (mounts #app)
├── vite.config.ts              Vite 8 config + /api dev proxy
├── tsconfig.json               TypeScript strict mode
├── package.json
└── src/
    ├── main.ts                 createApp + Pinia + Router
    ├── App.vue                 header, nav, <RouterView>
    ├── env.d.ts
    ├── api/
    │   ├── client.ts           typed fetch client + contract interfaces
    │   └── format.ts           dash(), timestamp/relative-time helpers
    ├── stores/
    │   ├── jobs.ts             job list, facets, filters, sort, pagination
    │   ├── session.ts          session metadata + run history
    │   └── applications.ts     ledger, status summary, sent messages
    ├── components/
    │   ├── EmptyState.vue      no-data state
    │   ├── ErrorState.vue      error state + retry (used by every view)
    │   ├── FilterBar.vue       location / company / status dropdowns
    │   ├── JobTable.vue        job list table with sortable columns
    │   ├── LoadingState.vue    loading state
    │   ├── MessageList.vue     sent messages (body as pre-wrap text)
    │   ├── Pagination.vue      real pagination driven by `total`
    │   ├── RunTable.vue        scrape run history table
    │   ├── SearchBar.vue       debounced (~250 ms) search input
    │   ├── SessionCard.vue     cookie session metadata card
    │   └── StatusBadge.vue     coloured status pill
    ├── router/index.ts         the 4 routes
    ├── styles/
    │   ├── tokens.css          design tokens (spacing, color, radius, type)
    │   └── base.css            base layer + shared primitives
    └── views/
        ├── ApplicationsView.vue
        ├── JobDetailView.vue
        ├── JobsView.vue
        └── SessionView.vue
```

## Design system

No UI framework, no component library, no Tailwind. Everything is plain CSS
driven by custom properties in `src/styles/tokens.css`:

- **Spacing** — `--space-0` … `--space-9` (4 px base scale)
- **Color** — `--color-bg`, `--color-text`, `--color-accent`, `--color-danger`,
  `--color-warning`, `--color-success`, `--color-info`, plus `-soft`/`-border`
  variants; a `prefers-color-scheme: dark` block overrides the light palette
- **Radius** — `--radius-sm` … `--radius-xl`, `--radius-pill`
- **Typography** — `--font-sans`, `--font-mono`, `--text-xs` … `--text-2xl`,
  `--weight-regular` … `--weight-bold`

## Behaviour notes

- **Three states everywhere.** Every view renders a loading state, an empty
  state, and the shared `ErrorState` (with a retry button) when a fetch fails.
  A failed request never leaves a blank page.
- **Sparse data.** Empty strings are normal in this dataset (3 of 98 jobs have
  no company, 3 have no location). Every optional field renders through
  `dash()` from `src/api/format.ts` and shows `—` — never `undefined` or
  `null`.
- **Message bodies are text.** `MessageList` renders `body` with `{{ }}`
  interpolation inside a `pre-wrap` element. It never uses `v-html`, so a
  message can never inject markup.
- **Server-side search.** The search box debounces ~250 ms (and flushes
  immediately on Enter); filtering, sorting and pagination are all performed
  by the backend. The page size can be changed from the pagination bar.
- **Facets.** The location, company and status dropdowns are populated from
  `GET /api/jobs/facets`. If that request fails the dropdowns degrade
  gracefully and a small note is shown — the list itself still works.
- **No cookie values.** The session view only ever displays the metadata the
  API returns (counts, ids, timestamps, expiry).

## Type safety

`tsconfig.json` runs with `strict: true` plus `noUncheckedIndexedAccess`,
`exactOptionalPropertyTypes`, `noImplicitOverride`, `noUnusedLocals` and
`noUnusedParameters`. There is no `any` anywhere in `src/`.

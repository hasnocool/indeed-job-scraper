# API Contract — Indeed Job Scraper Backend

**Status:** frozen for implementation. Both the FastAPI backend (`api/`) and the
Vue frontend (`frontend/`) are built against this document. Do not change a
shape here without changing it in both places.

---

## 1. Overview

| | |
|---|---|
| Backend | FastAPI, Python 3.14, package `api/app` |
| Backend URL | `http://127.0.0.1:8001` |
| API prefix | `/api` |
| Interactive docs | `http://127.0.0.1:8001/docs` (Swagger UI) |
| OpenAPI JSON | `http://127.0.0.1:8001/openapi.json` |
| Frontend | Vue 3.5 + Vite 8 + TypeScript + Pinia + Vue Router |
| Frontend URL | `http://127.0.0.1:5173` |
| Dev proxy | Vite proxies `/api` → `http://127.0.0.1:8001` (no CORS in dev) |

> **Port note:** port 8000 on this machine is occupied by an unrelated
> service, so the backend runs on **8001**. Override the Vite proxy with
> `VITE_API_PROXY_TARGET` if the backend moves.


### Data source

The backend is **read-only over the existing scraper state**. It reads the
files the scraper already writes and never writes to them.

| Source | Path (relative to repo root) | Used by |
|---|---|---|
| Master job dataset | `data/master/jobs_master.json` | `/api/jobs*` |
| Scrape runs | `data/runs/jobs_*.json` | `/api/runs` |
| Cookie session | `data/cookies/current.json` | `/api/session` |
| Application ledger | `data/applications/ledger.jsonl` | `/api/applications*` |
| Sent messages | `data/messages/sent.jsonl` | `/api/messages` |

All paths resolve from the repo root, which is the **parent** of the `api/`
package directory. `INDEED_STATE_DIR` overrides the state root when set.

---

## 2. HARD SAFETY RULES

1. **Never return cookie values.** `data/cookies/current.json` holds a live
   Indeed credential. `/api/session` returns only metadata (counts, ids,
   timestamps, expiry). Cookie `name`/`value` pairs must never appear in any
   response body, log line, or error message.
2. **Read-only.** No endpoint mutates `data/`. There are no POST/PUT/DELETE
   endpoints in this contract.
3. **Missing files are not errors.** `data/applications/` and `data/responses/`
   do not exist yet on a fresh clone. Those endpoints return empty collections
   with HTTP 200, never 404.
4. **Never crash on a malformed record.** Skip unreadable entries rather than
   failing the whole response.

---

## 3. Shared JSON conventions

- JSON field names are **snake_case** everywhere (API responses and the
  TypeScript client). This matches the Python source, so there is no
  translation layer.
- Timestamps are ISO-8601 strings exactly as stored on disk
  (e.g. `"2026-10-21T02:52:14.981108+00:00"`). The backend does **not**
  reformat them.
- Missing/empty string fields are `""`, never `null`. Empty lists are `[]`.
- All list endpoints return a **wrapper object**, never a bare array, so
  pagination metadata can be added without breaking clients.

---

## 4. Endpoints

### 4.1 `GET /api/health`

```json
{ "status": "ok", "version": "0.1.0", "state_dir": "/abs/path/to/data" }
```

Always HTTP 200 when the process is up.

---

### 4.2 `GET /api/jobs`

The master dataset, filtered and paginated.

**Query parameters**

| Name | Type | Default | Notes |
|---|---|---|---|
| `q` | string | `""` | Case-insensitive substring over `title`, `company`, `location`, `snippet`, `salary` |
| `location` | string | `""` | Case-insensitive substring match on `location` |
| `company` | string | `""` | Case-insensitive substring match on `company` |
| `status` | string | `""` | One of `new`, `updated`, `unchanged` (exact match). Empty = all |
| `limit` | int | `50` | 1–500 |
| `offset` | int | `0` | ≥ 0 |
| `sort` | string | `last_seen` | One of `last_seen`, `first_seen`, `title`, `company`, `salary` |
| `order` | string | `desc` | `asc` or `desc` |

**Response 200**

```json
{
  "total": 98,
  "limit": 50,
  "offset": 0,
  "items": [ /* Job[] */ ]
}
```

`total` is the count **after** filtering, before pagination.

---

### 4.3 `GET /api/jobs/{short_id}`

One job by its 12-char `short_id` (the first 12 hex chars of the fingerprint).

**Response 200** — a single `Job` object.
**Response 404** — `{"detail": "Job not found"}` when no job has that `short_id`.

---

### 4.4 `GET /api/jobs/facets`

Filter values for the UI dropdowns.

```json
{
  "total": 98,
  "locations": ["Port Alberni, BC", "Tofino, BC", "Ucluelet, BC"],
  "companies": ["Beyond Bilingual Inc.", "Coastal Coffee"],
  "status_counts": { "new": 26, "updated": 6, "unchanged": 66 }
}
```

- `locations` and `companies` are sorted alphabetically, de-duplicated, and
  **exclude empty strings**.
- `status_counts` includes every status present in the dataset.
- `total` is the unfiltered job count.

---

### 4.5 `GET /api/session`

Cookie session **metadata only**. See safety rule 1.

```json
{
  "has_session": true,
  "session_id": "20261021-153600-eca523",
  "status": "active",
  "source": "refresh",
  "created_at": "2026-10-21T15:36:00.118967Z",
  "updated_at": "2026-10-21T16:00:25.066926Z",
  "cookie_count": 31,
  "auth_cookie_count": 8,
  "expires_at": "2026-11-21T15:36:00Z",
  "expired": false
}
```

- `status` is the raw value from the file (`active`, `expired`, `revoked`, …)
  or `"none"` when there is no session file.
- `auth_cookie_count` counts cookies whose name is one of the auth cookies the
  scraper cares about: `SESS`, `CTK`, `SUB`, `LV`, `LD`, `UIMF`, `IRS`, `CSRF`.
- `expires_at` is the earliest expiry among those auth cookies, as an ISO-8601
  UTC string, or `null` when unknown (browser-session cookies) or absent.
- `expired` is `true` when `expires_at` is in the past.
- When no session file exists: `has_session` is `false`, `session_id` is `""`,
  `status` is `"none"`, counts are `0`, `expires_at` is `null`,
  `expired` is `false`. Still HTTP 200.

---

### 4.6 `GET /api/runs`

Scrape run history, newest first.

**Query parameters:** `limit` (int, default 20, 1–200), `offset` (int, default 0).

```json
{
  "total": 5,
  "limit": 20,
  "offset": 0,
  "items": [
    {
      "file": "jobs_20261021-160025.json",
      "scraped_at": "2026-10-21T16:00:25.184300+00:00",
      "query": "(all jobs)",
      "locations": ["Ucluelet, BC", "Tofino, BC", "Port Alberni, BC"],
      "pages_fetched": 27,
      "total_jobs": 98,
      "stopped_reason": "Ucluelet, BC: end of results"
    }
  ]
}
```

`stopped_reason` is `""` when the run recorded none.

---

### 4.7 `GET /api/applications`

Entries from the application ledger (`data/applications/ledger.jsonl`).

**Query parameters:** `limit` (int, default 50, 1–500), `offset` (int, default 0),
`status` (string, default `""` — exact match on the ledger `status` field).

```json
{
  "total": 12,
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "jk": "d908957804ef576c",
      "company": "Beyond Bilingual Inc.",
      "title": "Bilingual Branch Wholesale Product Specialist",
      "status": "submitted",
      "at": "2026-10-21T16:34:00+00:00",
      "indeed_url": "https://www.indeed.com/viewjob?jk=d908957804ef576c"
    }
  ]
}
```

- The ledger is append-only JSONL; the **last** entry for a given `jk` wins
  (it may be re-written as a job moves from `reserved` → `submitted`).
- `at` is the entry's timestamp field, or `""` if absent.
- `indeed_url` is `""` when absent.
- Missing ledger file → `{"total": 0, "limit": ..., "offset": ..., "items": []}`.

---

### 4.8 `GET /api/applications/summary`

Counts by ledger status.

```json
{
  "total": 12,
  "status_counts": { "reserved": 1, "submitted": 9, "failed": 2 }
}
```

`status_counts` includes every status present; an empty ledger gives
`{"total": 0, "status_counts": {}}`.

---

### 4.9 `GET /api/messages`

Sent Indeed messages, newest first.

**Query parameters:** `limit` (int, default 50, 1–500), `offset` (int, default 0).

```json
{
  "total": 3,
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "conversation_id": "Q09OVkVSU0FUSU9OX1NFUlZJQ0VfRU5DUllQVEVELy8v...",
      "company": "Beyond Bilingual Inc.",
      "kind": "general",
      "status": "sent",
      "body": "Hello Brad,\n\nThank you for reaching out...",
      "detail": "",
      "at": "2026-10-21T22:10:40.250719+00:00"
    }
  ]
}
```

`body` may be long; the frontend must render it as pre-wrap text, not HTML.

---

## 5. `Job` object

This is the exact shape of one entry in `data/master/jobs_master.json`. The API
returns these fields **verbatim** — no renaming, no coercion.

```json
{
  "jk": "d908957804ef576c",
  "title": "Bilingual Branch Wholesale Product Specialist (Spanish)",
  "company": "Beyond Bilingual Inc.",
  "location": "Port Alberni, BC",
  "salary": "From $18.75 an hour",
  "schedule": "Full-time",
  "posted": "",
  "snippet": "",
  "url": "https://www.indeed.com/viewjob?jk=d908957804ef576c",
  "matches": ["Port Alberni, BC"],
  "fingerprint": "bd78dcb1cceb46a8cd2f4ab652d32d3a02b25b6f377d6c57beddb6c289a027ad",
  "short_id": "bd78dcb1cceb",
  "status": "new",
  "first_seen": "2026-10-21T02:52:14.981108+00:00",
  "last_seen": "2026-10-21T02:52:14.981108+00:00",
  "seen_count": 1,
  "duplicate_of": ""
}
```

Field notes:

| Field | Type | Notes |
|---|---|---|
| `jk` | string | Indeed job key. Always present. |
| `title` | string | Job title. Can be `""`. |
| `company` | string | Employer. Can be `""`. |
| `location` | string | Free text; varies in format (`"Tofino, BC"`, `"British Columbia"`, `""`). |
| `salary` | string | Free text, `""` when Indeed showed none. |
| `schedule` | string | e.g. `"Full-time"`. |
| `posted` | string | Free text, often `""`. |
| `snippet` | string | Job description excerpt, often `""`. |
| `url` | string | Indeed link. |
| `matches` | string[] | Which searched locations surfaced it. |
| `fingerprint` | string | SHA-256 hex of the 5 canonical fields. |
| `short_id` | string | First 12 chars of `fingerprint`. Unique per job. |
| `status` | string | `new` \| `updated` \| `unchanged`. |
| `first_seen` / `last_seen` | string | ISO-8601 timestamps. |
| `seen_count` | int | How many runs saw this posting. |
| `duplicate_of` | string | `short_id` of the canonical posting, or `""`. |

> **Real data is sparse.** In the current dataset 3 of 98 jobs have an empty
> `company`, and 3 have an empty `location`. Every UI surface must handle
> empty strings — render a placeholder like `—`, never `"undefined"` or
> `"null"`, and never crash on a missing key.

---

## 6. TypeScript client contract

The frontend must use a typed client whose interfaces mirror the JSON above
exactly.

```ts
export interface Job {
  jk: string
  title: string
  company: string
  location: string
  salary: string
  schedule: string
  posted: string
  snippet: string
  url: string
  matches: string[]
  fingerprint: string
  short_id: string
  status: string
  first_seen: string
  last_seen: string
  seen_count: number
  duplicate_of: string
}

export interface JobListResponse {
  total: number
  limit: number
  offset: number
  items: Job[]
}

export interface JobFacets {
  total: number
  locations: string[]
  companies: string[]
  status_counts: Record<string, number>
}

export interface SessionInfo {
  has_session: boolean
  session_id: string
  status: string
  source: string
  created_at: string
  updated_at: string
  cookie_count: number
  auth_cookie_count: number
  expires_at: string | null
  expired: boolean
}

export interface RunInfo {
  file: string
  scraped_at: string
  query: string
  locations: string[]
  pages_fetched: number
  total_jobs: number
  stopped_reason: string
}

export interface ApplicationEntry {
  jk: string
  company: string
  title: string
  status: string
  at: string
  indeed_url: string
}

export interface MessageEntry {
  conversation_id: string
  company: string
  kind: string
  status: string
  body: string
  detail: string
  at: string
}
```

---

## 7. Frontend requirements

**Stack:** Vue 3.5 (`<script setup lang="ts">`, Composition API only), Vite 8,
TypeScript, Vue Router 5, Pinia 3. No UI framework — plain CSS with custom
properties. No component library.

**Routes**

| Path | View | Purpose |
|---|---|---|
| `/` | `JobsView` | Master job list: search, filter, sort, paginate |
| `/jobs/:shortId` | `JobDetailView` | One job, full fields |
| `/session` | `SessionView` | Session health + scrape run history |
| `/applications` | `ApplicationsView` | Ledger table + status summary + sent messages |

**Behaviours that must work**

1. The jobs list loads from `GET /api/jobs` and shows `total` + `items`.
2. Typing in the search box filters the list (debounced ~250 ms, or on Enter).
3. Location / company / status dropdowns populate from `GET /api/jobs/facets`.
4. Pagination shows the real `total` and lets the user page through results.
5. A job row links to `/jobs/:shortId`; the detail view shows every `Job` field.
6. The session view shows whether a live session exists and its expiry.
7. The applications view shows the ledger table and the sent-messages list.
8. Every view has a loading state, an empty state, and an error state with a
   retry action. A failed fetch must never render a blank page.
9. Empty-string fields render as `—`, never as `undefined`/`null`.
10. The Vite dev server proxies `/api` to `http://127.0.0.1:8001`.

**Definition of done for the frontend:** `pnpm type-check` and `pnpm build`
both pass, and `pnpm dev` renders all four routes against a running backend.

---

## 8. Definition of done for the backend

1. `uvicorn app.main:app --reload` starts from inside `api/` with no import errors.
2. `GET /api/health` returns 200.
3. `GET /api/jobs` returns **98** jobs from the real dataset in this repo.
4. `GET /api/jobs/facets` returns the real distinct locations and companies.
5. `GET /api/session` returns metadata only — assert that no response body
   contains a cookie `value`.
6. `GET /api/runs`, `/api/applications`, `/api/applications/summary` and
   `/api/messages` all return 200, with empty collections where files are absent.
7. `GET /api/jobs/{short_id}` returns one job; an unknown id returns 404.
8. `GET /api/docs` serves Swagger UI.
9. The backend **reuses** `indeed_scraper` (config, export loaders, workspace
   paths) rather than re-implementing file parsing.
10. A `pyproject.toml` declares the backend's dependencies and the package
    layout; `uv sync` works.

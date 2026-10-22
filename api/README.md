# Indeed Job Scraper — API backend

Read-only FastAPI backend over the scraper's state directory (`data/`).
It implements the frozen contract in [`../docs/api-contract.md`](../docs/api-contract.md)
exactly: same field names, same query parameters, same status codes.

**The backend never writes to `data/`.** Every endpoint is a `GET`.

---

## Requirements

- Python 3.14
- [`uv`](https://docs.astral.sh/uv/) (the repo's copy lives at `~/.local/bin/uv`)

## Install

```bash
cd api
uv sync
```

This creates `api/.venv` and installs FastAPI, uvicorn, pydantic (plus the
scraper's own runtime deps that the reused loader modules need) and the test
tools.

## Run the server

```bash
cd api
uv run uvicorn app.main:app --reload --port 8000
```

Then:

- API root: <http://127.0.0.1:8000>
- Swagger UI: <http://127.0.0.1:8000/docs>
- OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>

Equivalent one-liner without the venv on `PATH`:

```bash
cd api && ~/.local/bin/uv run uvicorn app.main:app --reload --port 8000
```

The frontend's Vite dev server proxies `/api` → `http://127.0.0.1:8000`, so no
CORS configuration is required in development.

## Run the tests

```bash
cd api
uv run pytest
```

## Smoke-test every endpoint

```bash
cd api
uv run uvicorn app.main:app --port 8000 &   # or run it in another terminal

curl -s localhost:8000/api/health
curl -s 'localhost:8000/api/jobs?limit=2' | head -c 400
curl -s localhost:8000/api/jobs/facets
curl -s localhost:8000/api/session
curl -s localhost:8000/api/runs
curl -s localhost:8000/api/applications
curl -s localhost:8000/api/applications/summary
curl -s localhost:8000/api/messages
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/api/jobs/doesnotexist
```

---

## Layout

```
api/
├── pyproject.toml          # dependencies + package layout (hatchling)
├── README.md
├── app/
│   ├── __init__.py
│   ├── main.py             # app factory, middleware wiring, /docs
│   ├── paths.py            # repo-root + state-dir resolution, read-only paths
│   ├── models.py           # pydantic response models (contract §6)
│   ├── safety.py           # cookie-leak guard (runtime) + scan helpers
│   ├── routers/            # thin HTTP layer
│   │   ├── health.py
│   │   ├── jobs.py
│   │   ├── session.py
│   │   ├── runs.py
│   │   ├── applications.py
│   │   └── messages.py
│   └── services/           # file reading + caching
│       ├── cache.py
│       ├── jobs.py
│       ├── session.py
│       ├── runs.py
│       ├── applications.py
│       └── messages.py
└── tests/
    ├── conftest.py
    ├── test_health.py
    ├── test_jobs.py
    ├── test_session.py
    ├── test_runs.py
    ├── test_applications.py
    ├── test_messages.py
    └── test_safety.py
```

## How the scraper package is reused

The API reuses `indeed_scraper` rather than re-implementing file parsing:

| Reused | Used for |
|---|---|
| `indeed_scraper.config.Config.load()` | resolves the state dir (honours `INDEED_STATE_DIR`) and exposes `runs_dir` / `master_dir` / `cookies_dir` / `current_cookie_file` |
| `indeed_scraper.export.load_jobs()` | parses the master dataset and the run files (structured **or** legacy JSON) |
| `indeed_scraper.apply.workspace.load_master_jobs()` | validates the master records against the scraper's own `Job` model |
| `indeed_scraper.apply.workspace.LEDGER_FILENAME` | the application-ledger filename |
| `indeed_scraper.apply.responses_dir()` | the recorded-responses directory |
| `indeed_scraper.cookies.CookieSession` | parses `data/cookies/current.json`; `auth_cookies()` and `expires_at()` give the auth-cookie count and expiry |
| `indeed_scraper.messages.store.LEDGER_FILENAME` | the sent-messages filename |

`indeed_scraper` lives at the repository root, not inside `api/`, so
`app/paths.py` puts the repository root on `sys.path` before importing it.
That is the only coupling between the two trees.

### Two deliberate deviations from a straight copy-paste

1. **No `mkdir`.** `workspace.ledger_path()` and `workspace.responses_dir()`
   create their directories as a side effect. The backend is read-only, so
   `app/paths.py` calls them only when the directory already exists and
   otherwise derives the same path from the module's filename constants.
   `indeed_scraper.messages.store.sent_ledger_path()` is avoided for the same
   reason (it `chmod`s and creates `data/messages/`).
2. **No `CookieStore`.** `CookieStore.__init__` calls `config.ensure_dirs()`,
   which creates directories under `data/`. The API parses the session file
   directly with the reused `CookieSession` model instead.

## Safety

- `data/cookies/current.json` holds a **live Indeed credential**.
- `GET /api/session` returns metadata only: ids, timestamps, counts, expiry.
  Cookie `value`s and the `user_agent` are never returned.
- `app/safety.py` installs a runtime guard: every response body is scanned
  before it leaves the process. A body containing a `"value"` key, a cookie
  value, or a long cookie value as a substring is replaced with a 500 and the
  offending value is **never** logged.
- `api/tests/test_safety.py` asserts that no endpoint leaks a cookie value.

# Indeed Job Scraper

Collects job listings from Indeed for a set of locations, driven by a real,
signed-in browser session.

**Default scope:** every job (**no keyword filter**) in **Ucluelet, BC**,
**Tofino, BC** and **Port Alberni, BC** on ca.indeed.com.

The scraper signs a human in once, saves the resulting cookie list, reuses it
until it expires, and asks for a fresh sign-in only when Indeed rejects it.

## How it works

1. **Sign in (once).** login opens a visible Chromium window at Indeed. You
   sign in (email/password, Google or Apple, 2FA if enabled). The moment Indeed
   issues the SESS session cookie the flow captures the whole Indeed cookie
   list and writes it to disk.
2. **Use it until it expires.** scrape loads that cookie list into a persistent
   Chromium profile and runs the search. Cookies are re-captured after every
   run, so rotations are recorded against the same session.
3. **Detect expiry.** Cookies carry their own expiry timestamps; the session is
   considered unusable shortly before the earliest auth cookie expires, and an
   Indeed redirect to secure.indeed.com/auth means the session was revoked.
   Either way the scraper stops, marks the session, and offers a fresh sign-in
   instead of silently returning partial results.

## Install

    python3 -m pip install -r requirements.txt
    python3 -m playwright install chromium   # only if the browser is missing
    python3 -m indeed_scraper doctor         # checks browser, network, session

## Quick start

    # 1. Sign in to Indeed (a browser window opens; finish there)
    python3 -m indeed_scraper login

    # 2. Scrape all jobs in the three default BC locations
    python3 -m indeed_scraper scrape

    # 3. Inspect the saved session / cookie list / expiry
    python3 -m indeed_scraper status
    python3 -m indeed_scraper cookies --json

The legacy entry point still works and forwards every flag to scrape:

    python3 job_scraper_with_rate_limiting.py --pages 2

## Commands

| Command | Purpose |
| --- | --- |
| login | Open a browser and wait for you to sign in; save the cookie list. |
| verify | Confirm Indeed still accepts the saved cookies. |
| scrape | Search the locations with the saved session and write JSON/CSV. |
| status | Show the session, expiry and recent cookie history. |
| cookies | Print the cookie list in use (--json for the raw list). |
| doctor | Check Python, Playwright, Chromium, state dir and Indeed reachability. |
| organize | Replay the scrape history into the deduplicated master dataset. |
| apply | Apply to postings from the master dataset (guarded, see below). |
| resume | Resume an interrupted application from its saved draft. |
| check-responses | Refresh the response status of every submitted application. |

## Search options

    python3 -m indeed_scraper scrape \
      --location "Ucluelet, BC" \
      --location "Tofino, BC" \
      --location "Port Alberni, BC" \
      --location "Nanaimo, BC" \
      --pages 5 \
      --delay 8

| Option | Default | Meaning |
| --- | --- | --- |
| --query/-q | empty | Keywords. Empty means every job. |
| --location/-l | Ucluelet, Tofino, Port Alberni | Repeatable; results are deduped across locations. |
| --pages/-n | 10 | Maximum result pages per location. |
| --site | ca.indeed.com | Indeed host; www.indeed.com for US searches. |
| --delay | 7 s | Pause between result pages (keep it at 5 s or more). |
| --headless | off | Headless is usually blocked by Indeed/Cloudflare. |
| --csv | on | Also write jobs_latest.csv. |
| --relogin | on | Sign in again automatically if the session is rejected. |

A page that redirects to the sign-in wall stops the run with a clear
"session no longer valid" error instead of returning partial results.

## Where things are stored

Persistent data lives under ``data/`` (git-ignored). The directory tree is:

    data/
    +-- chrome-profile/            persistent Chromium browser profile (keeps cf_clearance)
    +-- cookies/
    |   +-- current.json           the cookie list currently in use
    |   +-- sessions/*.json        every session snapshot ever captured
    |   +-- history.jsonl          append-only log: saved / refreshed / expired / revoked
    +-- runs/                     **per-run exports**: ``jobs_YYYYMMDD-HHMMSS.json``
    +-- latest/                   **most-recent mirror**: ``jobs_latest.json`` +
                                   ``jobs_latest.csv`` (identical to latest run)
    +-- master/                   **cross-run deduped organized output**:
                                   ``jobs_master.json`` and ``jobs_master.csv``
    +-- legacy/                   old CSV dumps (scanned only for compatibility)

The special ``.indeed-state/`` directory is no longer used; state root defaults to
``data/`` under the repo root. Set ``INDEED_STATE_DIR`` to override.

### Cookie expiry model

- **Expiry:** the earliest expiry among auth cookies (SESS, CTK, SUB, LV, LD,
  UIMF, IRS, CSRF). When auth cookies are browser-session cookies, the expiry is
  unknown and the session is used until Indeed rejects it.
- **Rotation:** every save/refresh is appended to history.jsonl; rotated cookie
  names are listed on refresh events.
- **Revocation:** an Indeed redirect to secure.indeed.com/auth marks the session
  revoked and triggers re-login (unless --no-relogin).
- **Privacy:** the cookie list is a credential - keep .indeed-state/ private and
  out of version control.

## CSV conversion

    python3 -m indeed_scraper organize   # writes data/master/jobs_master.json + .csv
    python3 -m indeed_scraper scrape      # appends new run, refreshes data/master

## Project layout

    indeed_scraper/
    +-- cli.py        typer commands
    +-- config.py     paths, search scope, pacing
    +-- cookies.py    typed cookies, session store, expiry, history
    +-- browser.py    Playwright profile + challenge detection
    +-- auth.py       interactive sign-in, session capture, reuse/verify
    +-- scraper.py    multi-location search, extraction, dedupe
    +-- export.py     JSON/CSV writers
    +-- errors.py     typed failures
    api/              FastAPI backend serving the scraper's data read-only
    frontend/         Vue 3 + Vite frontend for the backend
    docs/             shared API contract for api/ and frontend/
    tests/            cookie store, export and search-scope tests

## Web app (api/ + frontend/)

Two sub-projects sit on top of the scraper: a **read-only API** over the files
the scraper already writes, and a **Vue frontend** that renders them. The
scraper itself stays the only thing that writes to `data/`.

    docs/api-contract.md      the frozen contract both sides implement

### api/ — FastAPI backend

    cd api
    uv sync
    uv run uvicorn app.main:app --reload --port 8001

Serves JSON under `http://127.0.0.1:8001/api` (`/api/docs` for Swagger UI):
`/api/health`, `/api/jobs`, `/api/jobs/{short_id}`, `/api/jobs/facets`,
`/api/session`, `/api/runs`, `/api/applications`, `/api/applications/summary`
and `/api/messages`.

The API **never** exposes cookie values — `/api/session` returns session
metadata only, because the cookie list is a live Indeed credential.

### frontend/ — Vue 3 frontend

    cd frontend
    pnpm install
    pnpm dev          # http://127.0.0.1:5173, proxies /api to :8001

Four routes: the job list (`/`), a job's details (`/jobs/:short_id`), session
health and scrape history (`/session`), and the application ledger with sent
messages (`/applications`).

Run the backend first — the frontend proxies `/api` to
`http://127.0.0.1:8001`. Set `VITE_API_PROXY_TARGET` to point elsewhere.


## Notes

- Indeed requires a signed-in session for pagination and increasingly gates
  bot-like traffic behind Cloudflare. The scraper therefore runs a visible
  browser, paces pages, and lets you clear any challenge by hand.
- Keep the page delay at 5 seconds or more and avoid parallel runs.
- Scraping is subject to Indeed's Terms of Service; use for personal research.

## Deduplication and organization

### Hash design

The fingerprint is a ``sha256`` hexdigest computed from canonical JSON of five
fields: ``title``, ``company``, ``location``, ``salary``, ``schedule`` (``
FINGERPRINT_FIELDS ``).  The ``json.dumps`` call uses ``sort_keys=True,
ensure_ascii=False, separators=(",",":")`` over a ``dict`` keyed by field name
→ value, encoded ``utf-8``.

**Why these fields are excluded:**

- ``jk`` + ``url`` — identical content under different job keys is caught (re-post
  detection across runs).
- ``posted`` — relative-age drift between runs makes identical jobs appear
  "different" if posted dates shift.
- ``snippet`` — variable truncation and formatting differences between runs.
- ``matches`` — per-run location context; the same job may match different
  location sets in different runs.

**Benefits (cross-run dedup):**

- **Re-post detection:** identical content under different ``jk``/``url`` is caught
  via the fingerprint; the ``duplicate_of`` field links duplicates to the
  canonical job.
- **Change detection:** ``updated`` status flags jobs whose content fingerprint
  changed between runs; ``unchanged`` confirms stability.
- **12‑char stable job IDs:** ``short_id()`` returns the first 12 hex chars of
  the fingerprint, providing a readable, consistent identifier.
- **Idempotent regeneration:** ``data/runs/*.json`` are the sole source of truth;
  deleting ``data/master/`` and running ``organize`` rebuilds everything without
  needing a re-scrape.
- **Stable 12-char job IDs** for display and CSV export.

### ``organize`` command usage

```bash
# Refresh the master directory from historical runs
python3 -m indeed_scraper organize

# Output includes:
# - A rich summary table (runs ingested, unique jobs, total postings, new/updated/unchanged counts, duplicates)
# - A job listing table sorted by (company, title, location) with columns:
#   Job ID, Company, Title, Location, Posted, Salary, Status, Dup
#
# If data/runs/ is empty, a friendly message is printed and no files are written.
```

> **Known issue - the job description is not being captured.** The card
> extractor reads the description with a CSS selector that no longer matches
> Indeed's current markup, so `snippet` is empty in **98 of 98** records of
> `data/master/jobs_master.json` (every run), `posted` is empty in 40 of 98, and
> the exported `jobs_master.csv` has an empty **Job Description** column in
> 98 of 98 rows. Nothing warns about it, because the extractor tests use
> hand-written DOM with no description element in the fixture.
>
> The fix needs a real capture of the current Indeed DOM - the selector cannot
> be rewritten blind - and a live capture was refused by Indeed, so the defect
> is still open. `tests/test_extraction_completeness.py` is the drift gate and
> is marked `xfail(strict=True)` until it is fixed; the `organize` summary now
> prints a per-field fill rate, so the drift is visible without reading a test.

> **Known issue - the job description is not being captured.** The card
> extractor reads the description with a CSS selector that no longer matches
> Indeed's current markup, so `snippet` is empty in **98 of 98** records of
> `data/master/jobs_master.json` (every run), `posted` is empty in 40 of 98, and
> the exported `jobs_master.csv` has an empty **Job Description** column in
> 98 of 98 rows. Nothing warns about it, because the extractor tests use
> hand-written DOM with no description element in the fixture.
>
> The fix needs a real capture of the current Indeed DOM - the selector cannot
> be rewritten blind - and a live capture was refused by Indeed, so the defect
> is still open. `tests/test_extraction_completeness.py` is the drift gate and
> is marked `xfail(strict=True)` until it is fixed; the `organize` summary now
> prints a per-field fill rate, so the drift is visible without reading a test.

## Applying to jobs

The `apply` command fills Indeed-hosted application forms from a profile you
control. It is deliberately conservative: every irreversible step is guarded.

```bash
# 1. One-time: write the operator profile (0600, outside the repository)
mkdir -p ~/.config/indeed_scraper && chmod 700 ~/.config/indeed_scraper
$EDITOR ~/.config/indeed_scraper/profile.json

# 2. Rehearse: fill the form, write a draft, submit nothing
python3 -m indeed_scraper apply --dry-run --limit 3

# 3. Apply for real, confirming each submission
python3 -m indeed_scraper apply --limit 3

# 4. Resume an interrupted application
python3 -m indeed_scraper resume <job-id>

# 5. Check how the applications are going
python3 -m indeed_scraper check-responses
```

The profile holds what a form needs: `name`, `email`, `phone`, `resume_path`,
`cover_letter`, `screening_answers`, plus `work_authorization`,
`salary_expectations`, `availability`, `notice_period` and `visa_sponsorship`.
An empty string means *not supplied* - the flow refuses to invent a value and
raises a `FieldMissingError` naming the question instead.

### What the flow guarantees

- **Idempotent:** every application is reserved in `data/applications/ledger.jsonl`
  *before* the browser is touched, keyed by the same SHA-256 fingerprint the
  master dataset uses. A posting is never applied to twice. The apply path and
  the resume path share one guard, so a posting left in `submitting` by a killed
  run is never re-submitted by a `resume`.
- **A submission is only recorded when it is CONFIRMED:** the submit control is
  clicked at most once, and a positive signal - a confirmation in the page, the
  title, or a post-submit URL - must be observed before the ledger says
  `submitted`. A click with no signal is recorded as `unconfirmed`: it may have
  reached the employer, so it is never retried automatically and never counted
  as a success.
- **No unattended submits by default:** an unattended submission needs the
  policy's `unattended_submit` switch, and `--dry-run` never submits at all.
- **No fabricated answers:** a required field with no value in the profile stops
  the flow and names the question. A form with no applicant inputs at all is a
  refusal, not a quiet success.
- **The shared session is protected:** a challenge (CAPTCHA / Cloudflare /
  sign-in wall) stops the run instead of being retried, so the working scrape
  session is never poisoned.
- **Resumable:** each attempt writes `data/applications/drafts/<job-id>/draft.json`
  so an interrupted fill can be picked up with `resume`. The draft is a receipt:
  it lists only the fields that actually reached the form.
- **Rate limited:** `RiskBudget` caps applications per day (2 by default) and
  enforces a minimum delay between submissions. An `unconfirmed` attempt counts
  against the cap, because a click that may have gone out cannot be un-sent.
  The cap and the delay are set in the operator's policy file
  (`max_applications_per_day` and `min_delay_minutes`), which is the ceiling.
  `INDEED_MAX_APPS_PER_DAY` and `INDEED_MIN_DELAY_MINUTES` may **tighten** that
  ceiling for a single run — they can lower the cap and raise the delay, but
  never raise the cap or shorten the delay. A command-line flag
  (`--max-per-day`, `--min-delay`) behaves the same way.

### Exit codes

`apply` reports its outcome in the exit code, so an automated caller can tell
success from total failure:

| Code | Meaning |
| --- | --- |
| `0` | something was submitted, or the dry run did exactly what it was asked to do, or there was nothing to do |
| `2` | nothing was submitted and at least one attempt failed |
| `3` | the run was blocked by a challenge (CAPTCHA / auth wall) |

### Browser driver

The flow prefers the browser-harness MCP's Chrome, attached over CDP
(`INDEED_HARNESS_CDP`, default `http://127.0.0.1:9222`), and falls back to the
repository's own persistent profile. The fallback matters: Indeed's bot
protection rejects the harness' headless browser, while the warmed local
profile carries the `cf_clearance` cookie and works.

### Autonomy policy

Whether the agent acts on its own is an explicit, operator-owned setting in
``~/.config/indeed_scraper/policy.json`` (0600), not a hard-coded rule:

```json
{
  "level": "manual",
  "unattended_submit": false,
  "max_applications_per_day": 2,
  "min_delay_minutes": 30,
  "allow_binding_commitments": false
}
```

| Level | Permission | Submissions | Replies |
| --- | --- | --- | --- |
| `manual` | none | asked every time | drafted only |
| `auto` | may submit unattended | sent unattended **only if** `unattended_submit` is true | drafted only |
| `full` | may submit unattended | sent unattended **only if** `unattended_submit` is true | sent unattended |

**The level is a permission, not a decision.** An unattended submission also
requires the separate `unattended_submit` switch, which is OFF unless the
operator writes it into the policy file. This matters because the level alone
used to be enough: with a policy file saying `"level": "full"` the operator's
real applications went out with no prompt at all.

`--autonomy manual|auto|full` can only **lower** the ceiling for one run; it
can never raise it above what the file allows. `--max-per-day` can only lower
the daily cap and `--min-delay` can only raise the delay, for the same reason.

### Replies fail closed

A recruiter message is classified as `offer`, `interview`, `question`,
`general` or `unknown`. Only a message matching a known **safe** shape is
`general`; anything unrecognised is `unknown`, and `unknown` is *not* "safe to
send alone" - it is drafted for the operator.

One thing stays gated in every level: a reply that **accepts an offer** or
agrees to contractual terms. That is a binding commitment made on the
operator's behalf, and it is only sent unattended when
`allow_binding_commitments` is true.

## The operator profile

The profile is what the agent puts on a form. It lives outside the repository at
``~/.config/indeed_scraper/profile.json`` (0600):

```bash
# create the template with the right permissions
python3 -m indeed_scraper profile init

# check it, and whether the resume is usable
python3 -m indeed_scraper profile show

# point it at your real resume PDF
python3 -m indeed_scraper profile set-resume ~/Documents/my-resume.pdf
```

The resume is **validated before anything is applied**: it must exist, be a
PDF, and be a real document (at least 1 KB). A placeholder is refused with an
explicit message, because a stub would be uploaded to an employer.

## Resume formats

A resume is one document in many shapes. The `resume-doc` command converts
between them, so a resume you keep in Markdown can be sent as a Word
document, checked as JSON, or fed to another tool as TOML.

| Format | Extension | Notes |
| --- | --- | --- |
| Word | `.docx` | Reads and writes the styled document. |
| Markdown | `.md` | Headings for the sections, bullets for the items. |
| Plain text | `.txt` | The same content with no decoration. |
| JSON | `.json` | The full tree, one object per line-group. |
| YAML | `.yaml` / `.yml` | The same tree as JSON. |
| TOML | `.toml` | The same tree, with the sections as tables. |

```bash
# see what is supported
python3 -m indeed_scraper resume-doc formats

# convert a Word resume to YAML
python3 -m indeed_scraper resume-doc convert ~/Documents/resume.docx resume.yaml

# and back again - any format converts to any other
python3 -m indeed_scraper resume-doc convert resume.yaml resume.docx
```

The target's extension picks the format. Every format parses into one
canonical model and renders back out of it, so **a resume survives the round
trip through any format unchanged** - the same name, contact, summary,
skills, jobs with their periods and bullets, education and closing note come
back out. That guarantee is what the test suite pins, using both of the real
resume documents as fixtures.

As a library:

```python
from pathlib import Path
from indeed_scraper.resume import convert_file, parse_file

resume = parse_file(Path("resume.docx"))              # read into the model
convert_file(Path("resume.docx"), Path("resume.toml"))  # or convert in one step
```

## Replying to recruiters

Indeed's candidate inbox is a separate web app (``messages.indeed.com``)
reached with the same saved session.

```bash
# Read the inbox and draft replies without sending them
python3 -m indeed_scraper messages --dry-run --limit 5

# Send the replies the policy allows
python3 -m indeed_scraper messages --limit 5
```

Each incoming message is classified (``offer``, ``interview``, ``question``,
``general``, ``unknown``) and answered from the operator profile: interview
replies quote the stated availability, and a question the profile can answer is
answered from ``screening_answers``. A question it cannot answer is drafted for
the operator instead of being guessed. A message that matches no known shape is
``unknown``, and an unknown message is **drafted, never sent alone** - the
classifier fails closed. Every decision - sent or drafted - is appended to
``data/messages/sent.jsonl``, so an unattended reply can be audited afterwards,
and a conversation that already received a reply is never answered twice.

## Syncing with Indeed's application tracker

Indeed records what happened to every application you made (Applied,
Interviewing, **Offer received**, Hired, Not selected by employer, ...). The
`sync` command reads that tracker and mirrors the status into the local
ledger:

```bash
python3 -m indeed_scraper sync
```

An application whose status is `offer` or `hired` is reported as needing your
attention and is never acted on automatically - the agent prepares, you decide.

### Scope and limits

External ATS pages (Greenhouse, Lever, Workday, ...) are detected and recorded
as `external_portal_deferred` rather than automated - each portal has a
different DOM, and a generic form filler would be unreliable. Offer acceptance
and contract signing are never automated: those create binding commitments the
agent cannot verify.

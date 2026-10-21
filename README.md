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
| organize | Replay run files and refresh the deduped master dataset (no browser needed). |

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

## Data layout

Persistent data lives under ``data/``. The scrape history (``runs/``) and the
organized master list (``master/``) are versioned so the mirror keeps a second
copy; the session cookies (``cookies/``) and the browser profile
(``chrome-profile/``) are secrets and are never committed. The tree:

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
    tests/            cookie store, export and search-scope tests

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
# - A rich summary table (runs ingested, unique jobs, duplicate postings, new/updated/unchanged counts)
# - A job listing table sorted by (company, title, location) with columns:
#   Job ID, Company, Title, Location, Salary, Posted, Status
#
# If data/runs/ is empty, a friendly message is printed and no files are written.
```

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

Everything lives under .indeed-state/ (git-ignored):

    .indeed-state/
    +-- chrome-profile/            persistent Chromium profile (keeps cf_clearance)
    +-- cookies/
    |   +-- current.json           the cookie list currently in use
    |   +-- sessions/*.json        every session snapshot ever captured
    |   +-- history.jsonl          append-only log: saved / refreshed / expired / revoked
    +-- output/
        +-- jobs_<timestamp>.json  structured results for one run (per-location stats)
        +-- jobs_latest.json       most recent run
        +-- jobs_latest.csv        most recent run as CSV

Set INDEED_STATE_DIR or INDEED_SITE to relocate state or target a different
Indeed host.

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

    python3 parse_json_file_to_csv.py                       # newest output JSON
    python3 parse_json_file_to_csv.py .indeed-state/output/jobs_20261020-195619.json

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

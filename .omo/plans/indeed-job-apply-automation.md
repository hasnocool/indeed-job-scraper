# Plan — Autonomous Job Application Capability (browser-harness driven)

Origin: hyperplan adversarial review (5 members, 3 rounds, 34 findings, 8 proposals killed) + ulw-plan planner.
Repo: `/home/hyperion/Forks/indeed-job-scraper` · baseline `72f4fd2` (local == GitHub mirror).

## Objective
Ship a verified job-application capability that reaches real Indeed postings through the browser-harness
browser, fills forms from an operator-approved profile without fabricating values, is idempotent and
rate-limited, records durable resumable state, surfaces employer responses, and leaves the working
98-job scraper pipeline and its live session intact.

## Tier
HEAVY — new module layer, session/auth handling, external integration, shared-session risk surface.

## Resolved gates (defaults chosen; operator ratification pending)
| Gate | Decision | Rationale |
|---|---|---|
| OQ1 autonomy | operator approval at every transition; offer-accept/sign NEVER automated | debate convergence; legal-commitment risk |
| OQ2 external portals | DEFER | 98/98 master jobs are Indeed-hosted (measured); no external ATS to test against |
| OQ3 browser-harness | attach over CDP (`connect_over_cdp`) + seed cookies from `data/cookies/current.json` | no second login, no profile copy |
| OQ4 Gmail | DEFER from v1 | no credentials; needs a second profile + second CAPTCHA surface |
| OQ5 boundary | `indeed_scraper/apply/` subpackage (not a separate service) | shared session/profile forbids a service split |
| OQ6 risk budget | 2 applications/day, 30 min minimum delay, stop on challenge | conservative default; configurable |
| OQ7 apply.py | REWORK — split into the subpackage, preserve behaviour and tests | 445 LOC violates the 250-LOC house rule |

## Hard constraints
HC-1 no autonomous offer acceptance / signing / attestation · HC-2 never fabricate a field ·
HC-3 application idempotency before every submit (append-only ledger, atomic reserve BEFORE the browser
action) · HC-4 no unattended submit · HC-5 ToS risk budget · HC-6 selector/DOM interaction only, never
pixel clicks · HC-7 the shared session and `data/chrome-profile/` must not be poisoned ·
HC-8 secrets 0600, outside git.

## Evidence-driven findings that shaped this plan
- F1 The browser-harness owns a separate headless Chrome (`--headless=new`, profile
  `~/.config/browser-harness/chrome-profile`, CDP `127.0.0.1:9222`, `BU_CDP_URL` already set to it).
- F2 The repo CAN attach to it: `playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")` → 1 context.
- F3 Cookie seeding works: 52 Indeed cookies added; the harness profile then held 47 incl. the Passport token.
- F4 **Indeed blocks the headless harness browser** (Cloudflare "Request Blocked", Ray ID) even with valid
  cookies; the repo's own headed profile carrying `cf_clearance` works. The driver therefore supports both,
  and the Indeed path uses the warmed profile.
- F5 Harness discovery scans fixed profile dirs for `DevToolsActivePort` + live `SingletonLock`;
  `~/.config/chromium-browser` is one, so a repo-launched browser can be published to it.
- F6 The uncommitted `apply.py` (445 LOC) already does form fill, confirm gate, dry-run and challenge
  detection, but has NO ledger, NO pacing, NO durable state, NO external fill path.

## Tasks — write scopes are disjoint; no two lanes touch one file
| # | Scope | Owner | Acceptance |
|---|---|---|---|
| T1 | `apply/{types,exceptions,profile,ledger,risk,drafts}.py` + `tests/test_apply_core.py` | lane A | `pytest tests/test_apply_core.py -q` green; reserve is atomic + idempotent; profile 0600 round-trip |
| T2 | `apply/indeed_form.py` + `tests/test_indeed_form.py` | lane B | `pytest tests/test_indeed_form.py -q` green; portal detection, field fill, `FieldMissingError` on a missing required field |
| T3 | `response_monitor/{__init__,indeed,store}.py` + `tests/test_response_monitor.py` | lane C | `pytest tests/test_response_monitor.py -q` green; reads ledger, writes `data/responses/<app_id>.json` |
| T4 | `apply/driver.py` | lead | attaches to harness over CDP OR launches the repo's warmed profile; seeds cookies; raises on challenge |
| T5 | `apply/flow.py` | lead | ledger reserve → confirm → fill → submit → mark; budget enforcement; draft writes; resume |
| T6 | `cli.py` wiring: `apply` (`--dry-run/--confirm/--limit/--resume`), `check-responses` | lead | `python3 -m indeed_scraper apply --dry-run --limit 3` exits 0 |
| T7 | integration + verification SC1–SC8 | lead + worker-verify | all criteria PASS with artifacts |
| T8 | independent diff review | worker-review | unconditional approval |

## TODOs

Legend: `[x]` = implemented and independently verified with a captured artifact.
`[ ]` = outstanding. Every artifact path below is relative to
`.omo/start-work/evidence/`; every run has a matching `ledger.jsonl` entry.

### Wave 0 — state restoration (lead, done)
- [x] T0.1 Restore `.omo/boulder.json` and the evidence ledger lost to the chat disconnect
- [x] T0.2 Re-confirm the inherited baseline: 219 tests green, 98 master jobs, HEAD `b6140ab`

### Wave 1 — verification lanes (four independent workers, parallel, disjoint evidence dirs)
> T1–T6 are **implemented and committed** (through `b6140ab`), but the prior
> session's evidence ledger was destroyed by the chat disconnect. They stay
> `[ ]` until V5 independently re-confirms each acceptance claim in this
> session — an inherited done-claim is not a verified one.

- [ ] T1 `apply/{types,exceptions,profile,ledger,risk,drafts}.py` + `tests/test_apply_core.py` — atomic idempotent reserve; profile 0600 round-trip → `v1-offline/`
- [ ] T2 `apply/indeed_form.py` + `tests/test_indeed_form.py` — portal detection, field fill, `FieldMissingError` → `v1-offline/`
- [ ] T3 `response_monitor/{__init__,indeed,store}.py` + `tests/test_response_monitor.py` — reads ledger, writes `data/responses/<app_id>.json` → `v1-offline/`
- [ ] T4 `apply/driver.py` — attaches over CDP or launches the warmed profile; seeds cookies; raises on challenge → `v1-offline/`
- [ ] T5 `apply/flow.py` — reserve → confirm → fill → submit → mark; budget; drafts; resume → `v1-offline/`
- [ ] T6 `cli.py` wiring `apply` / `resume` / `check-responses` / `profile` → `v1-offline/`
- [ ] T7.1 V1 offline acceptance: SC1-offline, SC3, SC4, SC5, SC6, SC7 with artifacts → `v1-offline/`
- [ ] T7.2 V2 live browser dry-run against a real Indeed posting: SC1-live, SC2 (PNG + log + ledger + draft) → `v2-live/`
- [ ] T7.3 V3 adversarial QA: every applicable ultraqa class probed with a captured observable → `v3-adversarial/`
- [ ] T8 V4 independent diff review vs `72f4fd2` against HC-1..HC-8 and OQ1..OQ7 (SC8) → `v4-review/`

### Wave 2 — independent verification of every done-claim
- [ ] V5 `AdversarialVerify` of the T1–T6 acceptance claims and the V1–V4 lane claims; only `confirmed` unblocks → `v5-verify/`

### Wave 3 — defect repair (runs only if V4 or V5 confirms a defect)
- [ ] F1 Fix every confirmed defect; each fix re-verified independently → `f1-fixes/`

#### F1 wave restart (the owning session died; the lanes are re-dispatched)
The codex session that dispatched the F1 wave lost its transport and died
mid-flight. All three lanes were left red with **no production change**, and
nobody was retrying them. The five failing-first test files were RETAINED as
the red baseline rather than deleted, so the restart is verifiable against the
same contract. Measured red baseline: lane C **31 failed / 21 passed**,
lane A **16 failed**.

The shared contract `SubmitResult(clicked, confirmed, detail)` lives in
`indeed_scraper/apply/types.py` — a file in no lane's write scope — so lanes A
and B cannot disagree about it. `ApplyStatus` was widened to the statuses the
code actually writes.

- [x] F1-A `apply/{indeed_form,selectors,risk,drafts,worker}.py` → `tests/test_fix_lane_a_submit_truth.py` green (17 tests)
- [x] F1-B `apply/{flow,driver,ledger,tracker}.py` + `response_monitor/*` + `cookies.py` → new `tests/test_fix_lane_b_*.py` green
- [x] F1-C `cli.py` + `messages/*` + `apply/autonomy.py` + new `commands/` → the four `tests/test_fix_lane_c_*.py` green
- [ ] F1-D `scraper.py` + `organize/*` + new `scripts/capture_search_page.py` + new `tests/test_extraction_completeness.py` → the extraction drift gate green
  - **PARTIAL — the defect is still OPEN.** The live capture was BLOCKED: Indeed
    refused the saved session (auth wall / challenge), so there is no real DOM
    and a CSS-selector fix would be a guess. The lane correctly refused to
    write one. Delivered: the read-only capture tool, the per-field fill-rate
    summary in the `organize` output, and the drift gate itself.
  - The gate is marked `xfail(strict=True)`, NOT skipped: the suite stays a
    usable gate, the defect stays explicitly recorded, and the marker fails
    LOUDLY the moment the extractor is fixed (a strict xfail that unexpectedly
    passes is a suite error).
  - **Remediation:** re-authenticate the session, capture the live search page
    into `tests/fixtures/indeed_search_page.html`, fix `_EXTRACT_JS` against it,
    replace the reconstructed fixture, remove the xfail marker.
    Measured today: `snippet` empty in 98/98 records, `posted` empty in 40/98,
    and the exported master CSV has an empty `Job Description` column in 98/98
    rows.

**F1-D is not part of the original triage.** An independent measurement found
the extractor leaves `snippet` **empty in 98/98 master records (100%, every
run)** and `posted` empty in 40/98, with no completeness check anywhere in the
package and no test asserting the field at all — the whole suite is green
while the operator's exported CSV has an empty `Job Description` column in
98/98 rows. No lane's defect list covers it. Its scope is disjoint from A/B/C.

**Ledger status sets agreed across lanes** (A writes them, B enforces them):
`LIVE_STATUSES = {reserved, submitting, submitted, unconfirmed}`; the apply-path
skip set and the resume-path refusal set are aligned on
`{submitted, submitting, unconfirmed}`, so the resume path can no longer
re-submit a posting left in `submitting` (B1). A click with no confirmation
lands in `unconfirmed` — never retried automatically, surfaced to the operator,
because a duplicate application is worse than a missed one.

> Host note: the suite must be run as `PYTHONPATH=$PWD python3 -m pytest -q`.
> The `rtk` wrapper strips the CWD from `sys.path`, so a bare `pytest` fails
> with `ModuleNotFoundError`. That is a host artefact, not a project defect —
> do not "fix" it with a conftest.py or pyproject.toml.

### Final Verification Wave
- [x] F2.1 Full suite green. Two collection scopes, both verified:
  - repo-wide (`PYTHONPATH=$PWD python3 -m pytest -q`) → **440 collected, 439 passed, 1 xfailed, 0 failed** (409 from `tests/` + 31 from `api/tests/`; baseline was 219).
  - scraper only (`python3 -m pytest tests/ -q`) → **409 collected, 408 passed, 1 xfailed, 0 failed**.
  - api backend (`cd api && python3 -m pytest tests/ -q`) → **31 passed, 0 failed**.
  The 1 xfail is the deliberate F1-D open-defect marker. Proven self-contained: the suite was re-run green after deleting its generated `/tmp` fixture.
- [x] F2.2 `organize` still yields 98 master jobs → 5 runs, 98 unique, 7 duplicates, 26 new / 6 updated / 66 unchanged (identical to baseline). The new **Field Completeness** table shows `snippet 0% (0/98)`, so the open drift is visible in the operator's own output.
- [x] F2.3 `doctor` reports every check ok → python, playwright, chromium, saved session, state dir, indeed reachable (HTTP 200)
- [x] F2.4 Secrets: no profile/ledger/draft/response file is tracked or staged; every secret path is gitignored; the cookie files are now 0600 in a 0700 directory (they were 0644)
- [x] F2.5 No leftover QA assets: every spawned browser, sandbox and temp dir torn down; the suite's own fixtures are regenerated on demand
- [x] F2.6 Every final-verification checkbox is `[x]` and every ledger entry has an artifact. **F1-D remains deliberately open** - see its entry above; it is an operator-action blocker (a live capture needs a re-authenticated session), not an unfinished implementation.

## Success criteria
- **SC1 happy** `python3 -m indeed_scraper apply --dry-run --limit 3` → exit 0; ledger 3×`reserved`, 0×`submitted`; 3 `draft.json`.
- **SC2 real browser** live dry-run reaches a real Indeed posting signed-in; PNG + log.
- **SC3 idempotency** same fingerprint twice → 1 ledger line; 2nd run logs "already applied or reserved".
- **SC4 hard-refuse** missing required field → `FieldMissingError(question, job_url)`; nothing fabricated.
- **SC5 budget** `max_per_day=2` blocks the 3rd application.
- **SC6 regression** pytest green; `organize` still yields 98 master jobs; `doctor` all ok.
- **SC7 no secrets** `git check-ignore` confirms profile/ledger/drafts ignored; no data files staged.
- **SC8 reviewer** `worker-review` approves unconditionally.

## Data layout
`data/applications/ledger.jsonl` (0600) · `data/applications/drafts/<app_id>/draft.json` ·
`data/responses/<app_id>.json` · `~/.config/indeed_scraper/profile.json` (0600) — all gitignored.
`data/runs/` + `data/master/` stay tracked.

## Rollback
Any task failing its acceptance twice → revert its files, record in the notepad, escalate.

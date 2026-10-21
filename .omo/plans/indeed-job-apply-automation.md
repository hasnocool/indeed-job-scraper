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

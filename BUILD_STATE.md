---
schema_version: 1
scope: project:/home/hyperion/Forks/indeed-job-scraper
generated_at: 2026-10-21T23:49:22Z
generator: build-state-sync/1.0.0
content_sha256: 6af4a496115aad5b244db1ab23f7914f9089822ba147f413e622f902b7255d40
---
# Build State — project:/home/hyperion/Forks/indeed-job-scraper

## Identity
- Scope path: /home/hyperion/Forks/indeed-job-scraper
- Scope key: project:/home/hyperion/Forks/indeed-job-scraper
- Hostname: cachyos-x8664
- Generator: build-state-sync/1.0.0
- Generated at: 2026-10-21T23:49:22Z

## Repository
- Git toplevel: /home/hyperion/Forks/indeed-job-scraper
- Branch: main
- HEAD: b6140ab
- HEAD commit: Make a released reservation retryable and keep the tracker status out of the idempotency ledger | 2026-10-21 16:34:00 -0700
- Status: modified=1 added=0 deleted=0 untracked=1
- Last 5 commits:
  - b6140ab Make a released reservation retryable and keep the tracker status out of the idempotency ledger
  - 347b1ba Fix every finding from the two independent reviews
  - a725653 Close the offer-classifier hole so an offer can never be accepted unattended
  - bc39763 Validate the resume and add a profile command so a placeholder can never be applied
  - a944687 Added the Indeed application tracker sync
- Remotes:
  - origin https://github.com/hasnocool/indeed-job-scraper.git

## Stack
- .md: 3 files, ~493 LOC
- .py: 71 files, ~9864 LOC
- .sh: 1 files, ~4 LOC
- Manifests: requirements.txt

## Commands
No build command detected

## Structure
- .file_contents_output (dir, 1)
- .gitignore (file, 1)
- .graphflow (dir, 2)
- .omo (dir, 1)
- .opencode (dir, 1)
- .repo_summary (dir, 1)
- BUILD_STATE.md (file, 1)
- README.md (file, 1)
- data (dir, 7)
- graphflow-out (dir, 1)
- indeed_scraper (dir, 19)
- job_scraper_with_rate_limiting.py (file, 1)
- parse_json_file_to_csv.py (file, 1)
- remove_logs.sh (file, 1)
- requirements.txt (file, 1)
- scripts (dir, 5)
- tests (dir, 25)

## Tooling
- python3: Python 3.14.7
- node: v26.10.0
- npm: 11.19.1
- uv: uv 0.12.18 (x86_64-unknown-linux-gnu)
- cargo: cargo 1.98.1 (797e8a9bc 2026-08-05)
- rustc: rustc 1.98.1 (48a229cea 2026-09-01)
- docker: podman version 6.1.3
- make: GNU Make 4.4.1
- pytest: pytest 9.1.1
- ruff: ruff 0.16.10
- git: git version 2.56.0

## Work In Progress
- TODO.md open tasks: 0
- NOTES.md open tasks: 0
- PLAN.md open tasks: 0
- Uncommitted paths (max 20):
  - ata/master/jobs_master.json
  - BUILD_STATE.md
- Modified tracked files: 1

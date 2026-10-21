"""Which postings in the master list still offer an apply button? READ-ONLY."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from indeed_scraper.apply.driver import open_driver
from indeed_scraper.apply.selectors import APPLY_BUTTON_SELECTORS
from indeed_scraper.config import Config
from indeed_scraper.cookies import CookieStore


def main() -> int:
    config = Config.load(state_dir=Path(__file__).resolve().parents[1] / "data")
    store = CookieStore(config)
    session = store.current()
    master = json.loads((config.master_dir / "jobs_master.json").read_text(encoding="utf-8"))
    jobs = master["jobs"]
    with open_driver(config, session) as (context, _info):
        page = context.pages[0] if context.pages else context.new_page()
        live = []
        for job in jobs[:14]:
            try:
                page.goto(job["url"], wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2500)
                found = False
                for sel in APPLY_BUTTON_SELECTORS:
                    try:
                        loc = page.locator(sel).first
                        if loc.is_visible(timeout=700):
                            found = True
                            break
                    except Exception:  # noqa: BLE001, S112 - a probe may not match
                        continue
                loc_txt = job.get("location", "")[:26]
                print(f"{'LIVE ' if found else 'closed'} | {job.get('company','')[:20]:20} | {loc_txt:26} | {job['title'][:40]}", flush=True)
                if found:
                    live.append(job["jk"])
            except Exception as e:  # noqa: BLE001
                print("ERR   |", str(e)[:60], flush=True)
        print("\nLIVE jks:", live, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Why is the apply button not found? Dump the live job page. READ-ONLY."""

from __future__ import annotations

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
    jk = sys.argv[1] if len(sys.argv) > 1 else "d908957804ef576c"
    with open_driver(config, session) as (context, _info):
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(f"https://ca.indeed.com/viewjob?jk={jk}", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2000)
        print("after 2s:", flush=True)
        for sel in APPLY_BUTTON_SELECTORS:
            try:
                loc = page.locator(sel).first
                print(f"   {sel:45} count={page.locator(sel).count()} visible={loc.is_visible(timeout=800)}", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"   {sel:45} ERROR {str(e)[:60]}", flush=True)
        page.wait_for_timeout(6000)
        print("\nafter 8s:", flush=True)
        for sel in APPLY_BUTTON_SELECTORS:
            try:
                loc = page.locator(sel).first
                print(f"   {sel:45} count={page.locator(sel).count()} visible={loc.is_visible(timeout=800)}", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"   {sel:45} ERROR {str(e)[:60]}", flush=True)
        texts = page.evaluate(
            "() => Array.from(document.querySelectorAll('a,button'))"
            ".map(n => (n.innerText||'').trim()).filter(t => /apply/i.test(t)).slice(0,10)"
        )
        print("\nany element whose text mentions 'apply':", texts, flush=True)
        print("title:", page.title(), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

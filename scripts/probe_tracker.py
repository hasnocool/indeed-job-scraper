"""Map the application tracker's status control. READ-ONLY: nothing is selected."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from indeed_scraper.apply.driver import open_driver
from indeed_scraper.config import Config
from indeed_scraper.cookies import CookieStore

PROBE_JS = r"""() => {
  const rows = Array.from(document.querySelectorAll('[data-testid="jobStatusDateShort"]'));
  const buttons = Array.from(document.querySelectorAll('button'))
    .filter(b => /update status/i.test(b.innerText || ''));
  return {
    url: location.href,
    title: document.title,
    status_rows: rows.length,
    update_buttons: buttons.length,
    tabs: Array.from(document.querySelectorAll('[data-testid="SAVED"],[data-testid="APPLIED"],[data-testid="INTERVIEWS"],[data-testid="ARCHIVED"]'))
      .map(n => ({id: n.getAttribute('data-testid'), text: (n.innerText||'').trim().slice(0,40)})),
    first_rows: Array.from(document.querySelectorAll('[data-testid="jobStatusDateShort"]')).slice(0,4)
      .map(n => (n.innerText||'').trim().slice(0,60)),
    body_head: (document.body ? document.body.innerText : '').slice(0,700),
  };
}"""


def main() -> int:
    config = Config.load(state_dir=Path(__file__).resolve().parents[1] / "data")
    store = CookieStore(config)
    session = store.current()
    with open_driver(config, session) as (context, _info):
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://myjobs.indeed.com/applied", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(4000)
        info = page.evaluate(PROBE_JS)
        print(json.dumps(info, indent=2, ensure_ascii=False)[:2200], flush=True)
        # open the first "Update status" control and read its options (no selection)
        buttons = page.locator('button:has-text("Update status")')
        if buttons.count():
            buttons.first.click()
            page.wait_for_timeout(2000)
            menu = page.evaluate(
                """() => {
                  const items = Array.from(document.querySelectorAll('[role=option], [role=menuitem], li, button'))
                    .map(n => (n.innerText||'').trim())
                    .filter(t => t && t.length < 40);
                  return {items: items.slice(-25), testids: Array.from(new Set(Array.from(document.querySelectorAll('[data-testid]'))
                    .map(n => n.getAttribute('data-testid')))).filter(t => /status|menu|option|dropdown/i.test(t)).slice(0,15)};
                }"""
            )
            print("\nMENU:", json.dumps(menu, ensure_ascii=False)[:1500], flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

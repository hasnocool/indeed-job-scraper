"""Discover Indeed's candidate messaging surface with the real session.

Read-only: navigates candidate-facing URLs and reports what renders.
Never clicks a reply control, never sends anything.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from indeed_scraper.browser import active_page, open_context
from indeed_scraper.config import Config
from indeed_scraper.cookies import CookieStore

URLS = [
    "https://ca.indeed.com/messages",
    "https://ca.indeed.com/myjobs/messages",
    "https://ca.indeed.com/employermessages",
    "https://ca.indeed.com/sp/employer-messages",
    "https://ca.indeed.com/myjobs",
]

PROBE_JS = r"""() => {
  const out = {url: location.href, title: document.title, testids: [], links: [], text: ''};
  out.testids = Array.from(new Set(Array.from(document.querySelectorAll('[data-testid]'))
      .map(n => n.getAttribute('data-testid')))).slice(0, 40);
  out.links = Array.from(document.querySelectorAll('a[href]'))
      .map(a => ({href: a.getAttribute('href'), text: (a.innerText||'').trim().slice(0,40)}))
      .filter(l => /messag|chat|employer|recruit|notif|inbox/i.test(l.href + ' ' + l.text))
      .slice(0, 25);
  const body = document.body ? document.body.innerText : '';
  out.text = body.slice(0, 1200);
  out.textareas = Array.from(document.querySelectorAll('textarea'))
      .map(t => ({name: t.getAttribute('name'), id: t.id, ph: t.getAttribute('placeholder')})).slice(0, 8);
  out.inputs = Array.from(document.querySelectorAll('input'))
      .map(n => ({name: n.getAttribute('name'), type: n.getAttribute('type'), id: n.id})).slice(0, 12);
  out.buttons = Array.from(document.querySelectorAll('button'))
      .map(b => (b.innerText||b.getAttribute('aria-label')||'').trim().slice(0,30))
      .filter(Boolean).slice(0, 20);
  return out;
}"""


def main() -> int:
    config = Config.load(state_dir=Path(__file__).resolve().parents[1] / "data")
    store = CookieStore(config)
    session = store.current()
    if session is None or not session.is_signed_in():
        print("NO SESSION")
        return 1
    results = []
    with open_context(config, session=session, headless=False) as context:
        page = active_page(context)
        for url in URLS:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2500)
                info = page.evaluate(PROBE_JS)
                results.append(info)
                print("=" * 70, flush=True)
                print("URL:", url, flush=True)
                print("FINAL:", info["url"], flush=True)
                print("TITLE:", info["title"], flush=True)
                print("TEXT:", info["text"][:400].replace("\n", " | "), flush=True)
                print("TESTIDS:", info["testids"][:20], flush=True)
                print("MSG LINKS:", json.dumps(info["links"][:8], ensure_ascii=False), flush=True)
                print("TEXTAREAS:", info["textareas"], flush=True)
                print("BUTTONS:", info["buttons"][:10], flush=True)
            except Exception as error:  # noqa: BLE001
                print("=" * 70, flush=True)
                print("URL:", url, "ERROR:", str(error)[:200], flush=True)
    Path("/tmp/opencode/indeed_messages_probe.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\nsaved /tmp/opencode/indeed_messages_probe.json", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

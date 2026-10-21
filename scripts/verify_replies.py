"""Verify which conversations actually carry the operator's reply. READ-ONLY."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from indeed_scraper.apply.driver import open_driver
from indeed_scraper.config import Config
from indeed_scraper.cookies import CookieStore
from indeed_scraper.messages.inbox import (
    list_conversations,
    open_conversation,
    open_inbox,
)


def main() -> int:
    config = Config.load(state_dir=Path(__file__).resolve().parents[1] / "data")
    store = CookieStore(config)
    session = store.current()
    with open_driver(config, session) as (context, _info):
        page = context.pages[0] if context.pages else context.new_page()
        open_inbox(page)
        convs = list_conversations(page)
        print("conversations:", len(convs), flush=True)
        for conv in convs[:4]:
            open_inbox(page)
            rows = page.locator('[data-testid="indeed-messaging--ConversationList__item"]')
            rows.nth(conv.index).click()
            page.wait_for_timeout(3000)
            msgs = open_conversation(page, conv)
            print(f"\n--- {conv.company} ({conv.date})", flush=True)
            print("    url:", page.url.split("?")[0][-40:], flush=True)
            print("    messages:", len(msgs), flush=True)
            for m in msgs[-3:]:
                print(f"      [{m.sender or '?'}] {m.text[:90]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

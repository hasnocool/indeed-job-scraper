#!/usr/bin/env python3
"""Backwards-compatible entry point.

The original Selenium script could not run here: it hardcoded a missing Chrome
binary and needed a matching chromedriver. The scraper now drives a real
Chromium profile through Playwright, signs in interactively and reuses the
saved Indeed session cookies. Every argument is forwarded to the scrape
command, so this still works:  python job_scraper_with_rate_limiting.py -n 3
"""

from __future__ import annotations

import sys

from indeed_scraper.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["scrape", *sys.argv[1:]]))

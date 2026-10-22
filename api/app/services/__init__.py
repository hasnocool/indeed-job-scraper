"""Service layer: file reading, parsing and caching.

Each module here owns one kind of scraper state file and returns plain
Python data.  The routers in ``app/routers/`` do the HTTP shaping and nothing
else.
"""

from __future__ import annotations

__all__ = ["applications", "cache", "jobs", "messages", "runs", "session"]

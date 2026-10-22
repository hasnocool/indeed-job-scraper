"""HTTP routers.

Each router is a thin shell: it validates the query parameters, calls a
service and returns a response model.  No file is read here.
"""

from __future__ import annotations

__all__ = ["applications", "health", "jobs", "messages", "runs", "session"]

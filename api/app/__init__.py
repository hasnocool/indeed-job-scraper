"""Read-only FastAPI backend for the Indeed job scraper.

The package reads the scraper's state directory (``data/``) and never writes
to it.  See ``docs/api-contract.md`` for the frozen wire contract this
implements.

Importing this package puts the repository root on ``sys.path`` so the
scraper's own modules (``indeed_scraper``) can be reused instead of being
re-implemented here.  The repository root is the *parent* of the ``api/``
directory, which is where the ``indeed_scraper`` package lives.
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["REPO_ROOT", "__version__"]

__version__ = "0.1.0"

#: Repository root -- the parent of the ``api/`` directory that holds this
#: package.  Resolved from this file so it works no matter where the process
#: was started from.
REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

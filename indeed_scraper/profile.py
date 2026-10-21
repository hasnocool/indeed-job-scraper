"""Profile data for Indeed application forms.

Re-exported from :mod:`indeed_scraper.apply.profile`, which owns the schema,
the 0600 storage and the atomic write.
"""

from __future__ import annotations

from indeed_scraper.apply.profile import (
    PROFILE_PATH,
    Profile,
    apply_data,
    load_profile,
    save_profile,
)

__all__ = ["PROFILE_PATH", "Profile", "apply_data", "load_profile", "save_profile"]

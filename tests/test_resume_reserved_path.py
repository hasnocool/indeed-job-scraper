"""Regression test for the resume path's stale-reservation branch.

``resume_application`` releases a stale reservation before it checks the
live-status set, and that release calls ``_stale``. The helper lived in
``apply/flow.py`` and was NOT imported by ``apply/resume.py``, so the branch
raised ``NameError: name '_stale' is not defined`` - a crash in the middle of
the resume guard, on the one path that decides whether a posting may be
submitted again.

Nothing caught it: no test put a posting in the ``reserved`` state and drove
the resume path, and the 219-test suite was green throughout.

This test drives the real ``resume_application`` with a synthetic session, a
ledger holding a ``reserved`` posting, and a matching draft, and asserts that
the guard REFUSES the posting instead of raising.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rich.console import Console

from indeed_scraper.apply.flow import resume_application
from indeed_scraper.apply.ledger import ApplicationLedger
from indeed_scraper.apply.profile import Profile
from indeed_scraper.apply.workspace import drafts_dir, ledger_path
from indeed_scraper.config import Config
from indeed_scraper.cookies import Cookie, CookieStore

FINGERPRINT = "fp-resume-reserved"
APP_ID = "resumereserve"


def _state(tmp_path: Path) -> tuple[Config, CookieStore, Profile]:
    """A state dir with a synthetic session, a reserved posting and a draft."""
    config = Config.load(state_dir=tmp_path)
    config.ensure_dirs()
    store = CookieStore(config)
    # A synthetic session: is_signed_in() only looks for a SESS cookie.
    store.save(
        cookies=(Cookie(name="SESS", value="synthetic-not-a-credential", domain=".indeed.com"),),
        source="login",
    )

    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n" + b"0 " * 2048)
    profile = Profile(
        name="Test",
        email="test@example.com",
        phone="555-0100",
        resume_path=str(resume),
    )

    ledger = ApplicationLedger(ledger_path(config))
    ledger.reserve(
        FINGERPRINT,
        "jk1",
        "https://ca.indeed.com/viewjob?jk=jk1",
        company="Acme",
        title="Developer",
    )
    # "reserved" is what a run that was killed before the submit click leaves
    # behind. It is a LIVE status, so the posting must not be applied to again.
    assert ledger.status_of(FINGERPRINT) == "reserved"

    draft_dir = drafts_dir(config) / APP_ID
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / "draft.json").write_text(
        json.dumps(
            {
                "fingerprint": FINGERPRINT,
                "current_url": "https://ca.indeed.com/viewjob?jk=jk1",
                "jk": "jk1",
                "title": "Developer",
                "company": "Acme",
                "location": "Vancouver, BC",
            }
        ),
        encoding="utf-8",
    )
    return config, store, profile


def test_a_reserved_posting_is_refused_by_the_resume_path(tmp_path: Path) -> None:
    """The guard must refuse a reserved posting, not raise.

    The reservation is fresh, so it is not stale and must not be released -
    the posting is still live and a resume must not touch it.
    """
    config, store, profile = _state(tmp_path)

    with pytest.MonkeyPatch.context() as monkeypatch:
        # If the guard wrongly let the posting through, the next step would be
        # to open a browser. Fail loudly there instead of touching the site.
        def _no_browser(*args, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("the resume path opened a browser for a reserved posting")

        monkeypatch.setattr("indeed_scraper.apply.resume.open_driver", _no_browser)

        result = resume_application(
            config,
            store,
            Console(quiet=True),
            APP_ID,
            profile=profile,
            confirm=False,
        )

    assert result is None, "a reserved posting must not be resumed"
    # The reservation must still be live - it was not released.
    assert ApplicationLedger(ledger_path(config)).status_of(FINGERPRINT) == "reserved"

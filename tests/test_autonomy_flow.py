"""The autonomy policy must decide whether the operator is asked.

These tests cover the seam between the policy and the confirm gate: with the
policy at ``auto``/``full`` the operator is NOT prompted, and with ``manual``
they are. A regression in that wiring would mean either a bot asking
constantly or a bot submitting without ever asking.

The tests are hermetic: a fake page, a fake store, and a one-job master
dataset written into the temporary state directory. No browser, no network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from test_apply_confirm import _FakeConsole, _FakePage, _FakeStore, _profile

from indeed_scraper.apply.autonomy import AutonomyPolicy
from indeed_scraper.apply.ledger import ApplicationLedger

MASTER = {
    "meta": {"query": "(all jobs)", "locations": ["Ucluelet, BC"], "total_jobs": 1},
    "jobs": [
        {
            "jk": "jk1",
            "title": "Senior Data Engineer",
            "company": "Acme",
            "location": "Vancouver, BC",
            "url": "https://ca.indeed.com/viewjob?jk=jk1",
            "salary": "",
            "schedule": "",
            "posted": "",
            "snippet": "",
            "matches": ["Ucluelet, BC"],
        }
    ],
}


def _config(tmp_path: Path):
    from indeed_scraper.config import Config

    master = tmp_path / "master"
    master.mkdir(parents=True, exist_ok=True)
    (master / "jobs_master.json").write_text(json.dumps(MASTER), encoding="utf-8")
    return Config.load(state_dir=tmp_path)


def _profile_with_resume(tmp_path: Path):
    """A profile whose resume file actually exists (the flow refuses otherwise)."""
    resume = tmp_path / "resume.pdf"
    resume.write_bytes(b"%PDF-1.4\n" + b"0 " * 2048)
    return _profile(tmp_path)


def _page() -> Any:
    resume_selectors = {
        'input[name="applicant.name"]',
        'input[name="applicant.email"]',
        'input[name="applicant.phone"]',
        'input[type="file"]',
        'button:has-text("Apply now")',
        'button:has-text("Submit application")',
    }
    return _FakePage("https://ca.indeed.com/viewjob?jk=jk1", resume_selectors)


def test_the_flow_prompts_when_the_policy_is_manual(tmp_path: Path) -> None:
    """manual: the operator is asked before anything is submitted."""
    from indeed_scraper.apply.flow import apply_to_jobs

    console = _FakeConsole("yes")
    results = apply_to_jobs(
        _config(tmp_path),
        _FakeStore(),
        console,
        profile=_profile_with_resume(tmp_path),
        limit=1,
        confirm=True,
        policy=AutonomyPolicy(level="manual"),
        page=_page(),
    )
    assert console.prompts, "manual mode must ask the operator"
    assert results


def test_the_flow_does_not_prompt_when_the_policy_allows_it(tmp_path: Path) -> None:
    """auto/full PLUS the switch: the flow submits without a prompt.

    The level alone is only a permission. The unattended submit also needs
    the explicit ``unattended_submit`` switch, because a policy file that
    says ``"level": "full"`` must not by itself send a real application
    with no prompt.
    """
    from indeed_scraper.apply.flow import apply_to_jobs

    console = _FakeConsole("yes")
    results = apply_to_jobs(
        _config(tmp_path),
        _FakeStore(),
        console,
        profile=_profile_with_resume(tmp_path),
        limit=1,
        confirm=True,
        policy=AutonomyPolicy(
            level="auto",
            max_applications_per_day=5,
            min_delay_minutes=0,
            unattended_submit=True,
        ),
        page=_page(),
    )
    assert not console.prompts, "auto mode must not ask the operator"
    # The submission went out without a prompt. It is recorded as
    # "unconfirmed" because the fake page shows no confirmation signal, and
    # an unconfirmed submit is still an ATTEMPT - which is what the
    # idempotency guard cares about.
    assert any(result.status in {"submitted", "unconfirmed"} for result in results)


def test_the_flow_prompts_without_the_unattended_switch(tmp_path: Path) -> None:
    """The level alone is not enough: the operator is still asked."""
    from indeed_scraper.apply.flow import apply_to_jobs

    console = _FakeConsole("yes")
    apply_to_jobs(
        _config(tmp_path),
        _FakeStore(),
        console,
        profile=_profile_with_resume(tmp_path),
        limit=1,
        confirm=True,
        policy=AutonomyPolicy(level="auto", max_applications_per_day=5, min_delay_minutes=0),
        page=_page(),
    )
    assert console.prompts, "auto without the switch must still ask the operator"


def test_the_policy_supplies_the_risk_budget(tmp_path: Path) -> None:
    """The policy's numbers are the ones the flow enforces."""
    from indeed_scraper.apply.flow import apply_to_jobs

    console = _FakeConsole("yes")
    policy = AutonomyPolicy(
        level="auto",
        max_applications_per_day=1,
        min_delay_minutes=0,
        unattended_submit=True,
    )
    config = _config(tmp_path)
    apply_to_jobs(
        config,
        _FakeStore(),
        console,
        profile=_profile_with_resume(tmp_path),
        limit=5,
        confirm=True,
        policy=policy,
        page=_page(),
    )
    ledger = ApplicationLedger(config.state_dir / "applications" / "ledger.jsonl")
    # The cap stopped the run after the first application.
    assert ledger.submitted_today() == 1


def test_an_offer_reply_is_never_sent_unattended(tmp_path: Path) -> None:
    """A reply that accepts an offer stays a draft, whatever the level."""
    from indeed_scraper.messages.compose import build_reply
    from indeed_scraper.messages.inbox import Message

    profile = _profile(tmp_path)
    incoming = [
        Message(sender="Acme Recruiting", timestamp="now", text="We would like to offer you the role.")
    ]
    plan = build_reply(profile, incoming[0].text, "Acme")
    assert plan.kind == "offer"
    assert plan.requires_approval is True
    # No policy level may send it unattended unless the operator opts in.
    full = AutonomyPolicy(level="full", allow_binding_commitments=False)
    assert full.allows_reply is True
    assert full.allows_binding_commitment is False
    opted_in = AutonomyPolicy(level="full", allow_binding_commitments=True)
    assert opted_in.allows_binding_commitment is True

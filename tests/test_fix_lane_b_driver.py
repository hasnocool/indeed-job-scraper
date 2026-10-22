"""B2 - open_driver must not swallow the caller's own Playwright error.

``open_driver`` is a context manager that yields the browser to the apply
flow. The ``yield`` used to sit INSIDE the ``try:`` whose ``except Error:``
was meant to catch a failed CDP attach. Because ``contextlib`` implements
the with-body by calling ``gen.throw(exc)``, a ``playwright.sync_api.Error``
raised by the FLOW landed in that ``except``, and the generator was then
asked to yield a second time - which surfaces as:

    RuntimeError: generator didn't stop after throw()

The original error was destroyed, and the driver fell back to launching the
repository's SHARED ``data/chrome-profile`` browser as a side effect - an
HC-7 risk (the shared profile carries the cf_clearance cookie).
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest


class _FakeConfig:
    """The parts of Config that open_driver touches."""

    def __init__(self, profile_dir: Path) -> None:
        self.profile_dir = profile_dir


class _FakeSession:
    """A session with no cookies, so no cookie seeding happens."""

    cookies: tuple = ()

    def playwright_cookies(self) -> list[dict]:
        return []


def _install_fake_harness(monkeypatch: pytest.MonkeyPatch, *, boom: Exception | None) -> dict:
    """Replace the harness driver with one that records what happened."""
    from indeed_scraper.apply import driver as driver_module

    calls: dict[str, Any] = {"harness_used": False, "profile_used": False}

    @contextmanager
    def _fake_harness_driver(endpoint: str, session: Any):
        calls["harness_used"] = True
        if boom is not None:
            raise boom
        yield ("fake-context", "fake-info")

    @contextmanager
    def _fake_open_context(config: Any, session: Any = None, headless: bool = False):
        calls["profile_used"] = True
        yield "fake-profile-context"

    monkeypatch.setattr(driver_module, "_harness_driver", _fake_harness_driver)
    monkeypatch.setattr("indeed_scraper.browser.open_context", _fake_open_context)
    monkeypatch.setenv(driver_module.HARNESS_CDP_ENV, "http://127.0.0.1:9222")
    return calls


def test_a_playwright_error_from_the_flow_propagates_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flow's own Playwright error must reach the caller unchanged.

    This is the defect: the error was replaced by "RuntimeError: generator
    didn't stop after throw()", so the operator never learned what actually
    went wrong.
    """
    from playwright.sync_api import Error as PlaywrightError

    from indeed_scraper.apply.driver import open_driver

    _install_fake_harness(monkeypatch, boom=None)

    with pytest.raises(PlaywrightError) as error, open_driver(_FakeConfig(tmp_path), _FakeSession()) as (_ctx, _info):
        raise PlaywrightError("net::ERR_CONNECTION_RESET")

    assert "ERR_CONNECTION_RESET" in str(error.value), (
        "the original Playwright error must survive; "
        f"got {type(error.value).__name__}: {error.value}"
    )
    assert "generator didn't stop" not in str(error.value)


def test_a_playwright_error_from_the_flow_does_not_open_the_shared_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shared profile must NOT be launched as a side effect of an error.

    The shared profile carries the cf_clearance cookie; opening it because
    the flow crashed is exactly the HC-7 risk.
    """
    from playwright.sync_api import Error as PlaywrightError

    from indeed_scraper.apply.driver import open_driver

    calls = _install_fake_harness(monkeypatch, boom=None)

    with pytest.raises(PlaywrightError), open_driver(_FakeConfig(tmp_path), _FakeSession()) as (_ctx, _info):
        raise PlaywrightError("net::ERR_CONNECTION_RESET")

    assert calls["harness_used"] is True
    assert calls["profile_used"] is False, (
        "the shared data/chrome-profile browser was opened after the flow "
        "raised - the harness browser must not fall back to it"
    )


def test_a_failed_harness_attach_raises_a_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A CONFIGURED harness endpoint that cannot be reached must fail loudly.

    Silently falling back to the repository's shared profile would open a
    second, differently-fingerprinted browser against Indeed - which is what
    the profile driver is for, but it must be an explicit decision, never a
    side effect of a crash.
    """
    from playwright.sync_api import Error as PlaywrightError

    from indeed_scraper.apply.driver import open_driver
    from indeed_scraper.errors import IndeedScraperError

    _install_fake_harness(monkeypatch, boom=PlaywrightError("connect ECONNREFUSED"))

    with pytest.raises(IndeedScraperError) as error, open_driver(_FakeConfig(tmp_path), _FakeSession()):
        pass

    message = str(error.value)
    assert "9222" in message, "the error must name the endpoint that failed"
    assert "ECONNREFUSED" in message, "the error must keep the original cause"


def test_without_a_configured_endpoint_the_profile_driver_is_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no harness configured, the profile driver is the normal path."""
    from indeed_scraper.apply.driver import open_driver

    calls = _install_fake_harness(monkeypatch, boom=None)
    monkeypatch.delenv("INDEED_HARNESS_CDP", raising=False)

    with open_driver(_FakeConfig(tmp_path), _FakeSession()) as (_ctx, info):
        assert info.kind == "profile"

    assert calls["profile_used"] is True
    assert calls["harness_used"] is False

"""The submit click and the confirmation signal that proves it worked.

This module exists because the submit contract is a delicate thing: it is
the only irreversible action in the whole tool, and the old implementation
lied about it in two ways at once.

* It reported a success it never observed. The success keywords were
  checked, and then the code fell through to ``return True`` anyway, so a
  click that produced no confirmation at all was recorded as a submission.
  "submitted" is a TERMINAL ledger state, so that lie is permanent.
* It clicked the submit button TWICE. A real Indeed form matches both
  ``button:has-text("Submit application")`` and ``button:has-text("Submit")``
  - the same button. The post-click read raised (the click navigates and
  destroys the execution context), the exception was caught, and the loop
  moved on to the next selector and clicked the same button again. Two
  applications to one employer, from one run.

The contract implemented here:

* The submit control is located ONCE and clicked AT MOST ONCE. A failed
  post-click read is not a failed click: the click already happened.
* ``confirmed`` is True ONLY when a real success signal was observed - a
  success keyword in the title or the URL, or a confirmation phrase in the
  markup. There is no fall-through.
* A click without a confirmation is reported as ``clicked=True,
  confirmed=False``. The caller must treat that as an ATTEMPT that may
  have reached the employer, never as a success and never as a failure
  that makes the posting retryable.
"""

from __future__ import annotations

from typing import Any

from .types import SubmitResult

#: The submit controls, most specific first. Only the FIRST visible match
#: is ever clicked, so two selectors that match the same button can never
#: produce two clicks.
SUBMIT_SELECTORS: tuple[str, ...] = (
    'button:has-text("Submit application")',
    'button:has-text("Submit")',
    'input[type="submit"]',
    '[data-testid="submit-application"]',
)

#: Keywords that mark a real success signal in the page TITLE or URL. The
#: title of the post-submit page ("Application Submitted") and the
#: post-submit URL are the two signals Indeed itself produces.
TITLE_URL_KEYWORDS: tuple[str, ...] = (
    "success",
    "applied",
    "thank you",
    "submitted",
    "confirmation",
)

#: Phrases that mark a real confirmation in the page MARKUP. These are
#: deliberately PHRASES rather than single words: the body of an
#: unsubmitted form contains "Submit application" and "apply", so a loose
#: word match there would report a success for a form that was never sent.
BODY_KEYWORDS: tuple[str, ...] = (
    "application has been submitted",
    "application was submitted",
    "application submitted",
    "your application has been sent",
    "successfully submitted",
    "submission successful",
    "thank you for applying",
    "thank you for your application",
    "we have received your application",
    "application received",
    "application is complete",
    "your application is complete",
    "you have successfully applied",
)

#: How long to wait after the click before reading the confirmation, and
#: how many times to retry the read when the navigation has already
#: destroyed the execution context.
_SETTLE_MS = 500
_READ_ATTEMPTS = 2


def _settle(page: Any) -> None:
    """Wait a moment for the post-click navigation to settle.

    The wait is a COURTESY, not a requirement: a page double may not
    implement it, and a destroyed execution context cannot be waited on.
    Failing it must not turn a dispatched click into a missing click.
    """
    try:
        page.wait_for_timeout(_SETTLE_MS)
    except Exception:  # noqa: BLE001, S110 - the wait is optional
        pass


def _find_submit_control(page: Any) -> tuple[Any | None, str]:
    """The first visible submit control, and the selector that found it.

    The control is located BEFORE the click, so that a click which raises
    cannot send the loop off to the next selector and click the same
    button a second time.
    """
    for selector in SUBMIT_SELECTORS:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=2000):
                return locator, selector
        except Exception:  # noqa: BLE001, S112 - a non-matching selector is expected
            continue
    return None, ""


def _read_signals(page: Any) -> tuple[str, str, str]:
    """Read the URL, the title and the markup, each one independently.

    Each read is isolated: a page double without a ``content()`` method, or
    a navigation that destroyed the execution context, must not swallow the
    title or the URL, which are the signals most likely to be readable.
    """
    url = ""
    title = ""
    body = ""
    try:
        url = getattr(page, "url", "") or ""
    except Exception:  # noqa: BLE001 - a page double may not carry a URL
        url = ""
    try:
        title = page.title() or ""
    except Exception:  # noqa: BLE001 - the context may have been destroyed
        title = ""
    try:
        body = page.content() or ""
    except Exception:  # noqa: BLE001 - the context may have been destroyed
        body = ""
    return str(url), str(title), str(body)


def _has_confirmation(url: str, title: str, body: str) -> bool:
    """True when a REAL success signal is present in what was read."""
    haystack_url = url.lower()
    haystack_title = title.lower()
    if any(keyword in haystack_url or keyword in haystack_title for keyword in TITLE_URL_KEYWORDS):
        return True
    haystack_body = body.lower()
    return any(phrase in haystack_body for phrase in BODY_KEYWORDS)


def submit_application(page: Any) -> SubmitResult:
    """Click the submit control once, and report what was really observed.

    Returns:
        A :class:`~indeed_scraper.apply.types.SubmitResult` with:

        ``clicked``
            True when a click was DISPATCHED at the submit control. The
            click is dispatched at most once per call, and a click whose
            outcome could not be read is still reported as dispatched: a
            click that may have gone out must never be retried.
        ``confirmed``
            True only when a real success signal was observed afterwards -
            a success keyword in the title or the URL, or a confirmation
            phrase in the markup. There is no fall-through: a click with no
            signal is NOT a submission.
        ``detail``
            A short machine-readable reason, e.g. ``"no_submit_control"``,
            ``"no_confirmation"``, ``"post_click_read_failed"``,
            ``"click_raised"``.
    """
    locator, _selector = _find_submit_control(page)
    if locator is None:
        return SubmitResult(clicked=False, confirmed=False, detail="no_submit_control")

    try:
        locator.click()
    except Exception:  # noqa: BLE001 - the click may or may not have gone out
        # The click was dispatched but Playwright reported an error. It may
        # have reached the employer, so it is reported as an attempt and
        # never as a retryable failure.
        return SubmitResult(clicked=True, confirmed=False, detail="click_raised")

    _settle(page)

    url, title, body = _read_signals(page)
    if _has_confirmation(url, title, body):
        return SubmitResult(clicked=True, confirmed=True, detail="")

    # No signal. One bounded re-read: the click navigates, and the new
    # document may need a moment to carry the confirmation.
    for _attempt in range(_READ_ATTEMPTS - 1):
        _settle(page)
        url, title, body = _read_signals(page)
        if _has_confirmation(url, title, body):
            return SubmitResult(clicked=True, confirmed=True, detail="")

    # The reads failed entirely (the navigation destroyed the context) or
    # the page simply carries no confirmation. Either way the click
    # happened and no success was observed.
    detail = "no_confirmation" if (url or title or body) else "post_click_read_failed"
    return SubmitResult(clicked=True, confirmed=False, detail=detail)

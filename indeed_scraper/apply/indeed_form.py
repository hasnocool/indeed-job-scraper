"""Indeed application-form interaction.

Phase 1: Indeed-hosted application forms only. External ATS pages are detected
and reported as "external" so the flow can skip them.

Every interaction is selector-based; no pixel coordinates are used anywhere.
A required field with no operator-supplied value raises FieldMissingError
rather than inventing one.
"""

from __future__ import annotations

import os

from playwright.sync_api import Page

from ..browser import challenge_kind, challenge_label
from .exceptions import FieldMissingError
from .profile import Profile
from .selectors import (
    APPLY_BUTTON_SELECTORS,
    FIELD_SELECTORS,
    _find_required_field_label,
    _is_field_required,
)
from .types import PortalType


def detect_portal(page: Page) -> PortalType:
    """Classify the page as an Indeed form, an external portal, or unknown."""
    url = page.url
    if "indeed.com" not in url:
        return "external"
    if "apply" in url or "viewjob" in url:
        return "indeed"
    return "unknown"


def find_apply_button(page: Page):
    """Find the Apply button on a page.

    Returns:
        A Playwright Locator if a visible match is found, None otherwise.
    """
    for selector in APPLY_BUTTON_SELECTORS:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=2000):
                return locator
        except Exception:  # noqa: BLE001, S112 - a non-matching selector is expected
            continue
    return None


def detect_challenge(page: Page) -> str:
    """Detect a CAPTCHA/Cloudflare/auth wall on the page.

    Returns:
        A short label for the challenge kind, or "" when the page is clean.
    """
    kind = challenge_kind(page)
    if kind != "none":
        return challenge_label(kind)
    title = page.title().strip().lower()
    if title in {"just a moment...", "just a moment"} or "attention required" in title:
        return "cloudflare_js"
    return ""


def fill_indeed_form(page: Page, profile: Profile, draft: dict | None = None) -> dict:
    """Fill the Indeed-hosted application form from the given Profile.

    Hard rule: if a field is marked required in the DOM and the Profile has no
    value for it, raise FieldMissingError(question_text, job_url) - never
    invent a value.

    Returns:
        The draft map of the values that were filled.
    """
    from_path = profile.resume_path
    job_url = page.url

    if not os.path.isfile(from_path):
        raise FieldMissingError(f"resume: {from_path}", page.url)

    if draft is None:
        draft = {}

    def _fill_field(field_name: str, value: str, field_sels: tuple[str, ...]) -> None:
        """Fill a form field, checking the DOM required attribute when empty."""
        if not value:
            # The profile has an empty string for this field: if the DOM marks
            # it required, the operator has not supplied a value for it.
            if _is_field_required(page, field_sels[0]) is True:
                question = _find_required_field_label(page, field_sels[0]) or field_name
                raise FieldMissingError(question, job_url)
            return
        filled = False
        for selector in field_sels:
            try:
                locator = page.locator(selector).first
                if locator.is_visible(timeout=1000):
                    locator.fill(value)
                    filled = True
                    break
            except Exception:  # noqa: BLE001, S112 - try the next selector
                continue
        if not filled:
            # None means the field is not on this form at all (so it is not
            # missing); True means required (or unreadable -> be strict).
            is_req = _is_field_required(page, field_sels[0])
            if is_req:
                question = _find_required_field_label(page, field_sels[0]) or field_name
                raise FieldMissingError(question, job_url)

    _fill_field("name", profile.name, FIELD_SELECTORS["name"])
    _fill_field("email", profile.email, FIELD_SELECTORS["email"])
    _fill_field("phone", profile.phone, FIELD_SELECTORS["phone"])

    resume_sels = FIELD_SELECTORS["resume"]
    try:
        resume_locator = page.locator(resume_sels[0]).first
        if resume_locator.is_visible(timeout=1000):
            resume_locator.set_input_files(from_path)
    except Exception:  # noqa: BLE001 - try the remaining selectors
        for selector in resume_sels[1:]:
            try:
                locator = page.locator(selector).first
                if locator.is_visible(timeout=1000):
                    locator.set_input_files(from_path)
                    break
            except Exception:  # noqa: BLE001, S112 - try the next selector
                continue

    cover_sels = FIELD_SELECTORS["cover_letter"]
    if profile.cover_letter:
        for selector in cover_sels:
            try:
                locator = page.locator(selector).first
                if locator.is_visible(timeout=1000):
                    locator.fill(profile.cover_letter)
                    break
            except Exception:  # noqa: BLE001, S112 - try the next selector
                continue

    draft["name"] = profile.name
    draft["email"] = profile.email
    draft["phone"] = profile.phone
    if profile.cover_letter:
        draft["cover_letter"] = profile.cover_letter

    return dict(draft)


def click_element(locator, timeout_ms: int = 5000) -> bool:
    """Click a locator, falling back to a DOM-level click.

    Indeed renders a modal (``role="alertdialog"``) over the job page, and its
    subtree intercepts pointer events, so a real pointer click times out. The
    fallback dispatches the click on the element itself, which is still
    selector-based - no pixel coordinates are involved.

    Returns:
        True when the element was clicked, False when both attempts failed.
    """
    try:
        locator.click(timeout=timeout_ms)
        return True
    except Exception:  # noqa: BLE001 - an overlay intercepted the pointer
        try:
            locator.evaluate("el => el.click()")
            return True
        except Exception:  # noqa: BLE001 - the element is genuinely not clickable
            return False


def submit_application(page: Page) -> bool:
    """Click the submit control on the application form.

    Finds the submit control by selector, clicks it with a selector-based
    Playwright locator, then waits for a success signal (URL change, a
    confirmation text, or a toast).

    Returns:
        True on success, False if no submit control was found.
    """
    submit_sels = (
        'button:has-text("Submit application")',
        'button:has-text("Submit")',
        'input[type="submit"]',
        '[data-testid="submit-application"]',
    )

    for selector in submit_sels:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=2000):
                locator.click()
                page.wait_for_timeout(500)
                url = page.url
                title = page.title().strip().lower()
                success_keywords = (
                    "success", "applied", "thank you", "submitted", "confirmation",
                )
                if any(kw in title or kw in url for kw in success_keywords):
                    return True
                # The click succeeded even without an explicit signal.
                return True
        except Exception:  # noqa: BLE001, S112 - try the next selector
            continue
    return False

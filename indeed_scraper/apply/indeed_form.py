"""Indeed application-form interaction.

Phase 1: Indeed-hosted application forms only. External ATS pages are detected
and reported as "external" so the flow can skip them.

Every interaction is selector-based; no pixel coordinates are used anywhere.
A required field with no operator-supplied value raises FieldMissingError
rather than inventing one.

The draft this module returns is a RECEIPT, not a plan: it names only the
fields that actually reached the form. The old implementation named every
field it was ASKED to fill, so a form that carried none of them still
produced a draft that looked complete, and the operator had no way to tell
that nothing had been sent.

The submit click lives in :mod:`indeed_scraper.apply.submit` - it is the one
irreversible action in the tool and it has its own contract.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page

from ..browser import challenge_kind, challenge_label
from .exceptions import FieldMissingError, ProfileNotFoundError
from .profile import Profile, validate_resume
from .selectors import (
    APPLY_BUTTON_SELECTORS,
    FIELD_SELECTORS,
    _find_required_field_label,
    _is_field_required,
    find_fillable,
    has_applicant_input,
)
from .submit import submit_application
from .types import PortalType, SubmitResult

__all__ = [
    "APPLY_BUTTON_SELECTORS",
    "FIELD_SELECTORS",
    "SubmitResult",
    "click_element",
    "detect_challenge",
    "detect_portal",
    "fill_indeed_form",
    "find_apply_button",
    "submit_application",
]


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


def _label_for(page: Page, field_sels: tuple[str, ...], field_name: str) -> str:
    """The operator-facing name of a missing field.

    The label is looked up across the WHOLE selector group, not only the
    first selector: the first one often matches nothing on the real form,
    and a question built from a selector the operator cannot see is not a
    question they can answer.
    """
    try:
        label = _find_required_field_label(page, field_sels)
    except Exception:  # noqa: BLE001 - the label is a nicety, not a requirement
        label = None
    return (label or "").strip() or field_name


def fill_indeed_form(page: Page, profile: Profile) -> dict:
    """Fill the Indeed-hosted application form from the given Profile.

    Hard rule: if a field is marked required in the DOM and the Profile has no
    value for it, raise FieldMissingError(question_text, job_url) - never
    invent a value.

    A second hard rule: the returned draft is a RECEIPT. A field appears in
    it only when a locator for it was actually found AND filled. A form
    with no applicant inputs at all is not a successful fill, and raises
    FieldMissingError("no_fillable_fields", job_url) rather than returning
    an empty draft that reads like a quiet success.

    Returns:
        The draft map of the fields that were really filled.
    """
    from_path = profile.resume_path
    job_url = page.url

    # The resume is the one file that is UPLOADED to an employer, so this is
    # where it must be a real document: a placeholder would be sent to them.
    try:
        validate_resume(Path(from_path).expanduser())
    except ProfileNotFoundError as error:
        raise FieldMissingError(f"resume: {error}", page.url) from error

    filled: dict[str, object] = {}

    for field_name in ("name", "email", "phone"):
        field_sels = FIELD_SELECTORS[field_name]
        value = getattr(profile, field_name)
        if not value:
            # The profile has an empty string for this field: if the DOM
            # marks it required, the operator has not supplied a value.
            if _is_field_required(page, field_sels):
                raise FieldMissingError(_label_for(page, field_sels, field_name), job_url)
            continue
        locator, _selector = find_fillable(page, field_sels)
        if locator is None:
            # The field is not on this form at all (so it is not missing);
            # it IS on the form and marked required (so it is missing).
            if _is_field_required(page, field_sels):
                raise FieldMissingError(_label_for(page, field_sels, field_name), job_url)
            continue
        try:
            locator.fill(value)
        except Exception:  # noqa: BLE001, S112 - try the next selector
            continue
        filled[field_name] = value

    # The resume is recorded ONLY when a file input really took the file.
    # A form with no file input at all is recorded as "no_input", so the
    # operator can see that the resume never reached the employer instead
    # of reading a draft that says the resume was sent.
    resume_locator, _resume_selector = find_fillable(page, FIELD_SELECTORS["resume"])
    if resume_locator is not None:
        try:
            resume_locator.set_input_files(from_path)
        except Exception:  # noqa: BLE001 - the upload may have been refused
            resume_locator = None
    if resume_locator is not None:
        filled["resume"] = True
    else:
        filled["resume_status"] = "no_input"

    if profile.cover_letter:
        cover_locator, _cover_selector = find_fillable(page, FIELD_SELECTORS["cover_letter"])
        if cover_locator is not None:
            try:
                cover_locator.fill(profile.cover_letter)
            except Exception:  # noqa: BLE001 - the field refused the value
                cover_locator = None
            if cover_locator is not None:
                filled["cover_letter"] = profile.cover_letter

    if not has_applicant_input(page):
        # NOTHING reached the form AND there is nothing on the form to
        # reach. The live Indeed smartapply form had zero applicant inputs
        # at fill time, and the old code produced a draft claiming name,
        # email and phone. A form this tool cannot fill is a refusal, not a
        # quiet success.
        raise FieldMissingError("no_fillable_fields", job_url)

    return filled


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

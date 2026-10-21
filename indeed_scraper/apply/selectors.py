"""Selector tables and field inspection for Indeed application forms.

The selectors live here as data, so a portal change is a data edit rather
than a code change, and the interaction module stays readable.
"""

from __future__ import annotations

from playwright.sync_api import Page

APPLY_BUTTON_SELECTORS: tuple[str, ...] = (
    'button:has-text("Apply now")',
    'a:has-text("Apply now")',
    'button:has-text("Apply")',
    'a:has-text("Apply")',
    '[data-testid="apply-button"]',
    '.ia-IndeedApplyButton',
    '#indeedApplyButton',
)

FIELD_SELECTORS: dict[str, tuple[str, ...]] = {
    "name": (
        'input[name="applicant.name"]',
        'input[id="applicant-name"]',
        'input[name="name"]',
    ),
    "email": (
        'input[name="applicant.email"]',
        'input[id="applicant-email"]',
        'input[type="email"]',
    ),
    "phone": (
        'input[name="applicant.phone"]',
        'input[id="applicant-phone"]',
        'input[type="tel"]',
    ),
    "resume": (
        'input[type="file"][accept*="pdf"]',
        'input[type="file"][name*="resume"]',
        'input[type="file"]',
    ),
    "cover_letter": (
        'textarea[name="cover.letter"]',
        'textarea[id="cover-letter"]',
        'textarea[name="coverletter"]',
    ),
}


def _find_required_field_label(page: Page, field_sel: str) -> str | None:
    """Try to find the visible label text for a given input selector.

    Returns the label text if found, or None.
    """
    try:
        # Look for a preceding label or aria-describedby
        label = page.locator(f'label[for="{field_sel}"]').first
        if label.is_visible(timeout=1000):
            return label.text_content()
    except Exception:  # noqa: BLE001, S110 - the label is optional
        pass
    # Try to get aria-label from the input itself
    try:
        inp = page.locator(field_sel).first
        aria = inp.get_attribute("aria-label")
        if aria:
            return aria
    except Exception:  # noqa: BLE001, S110 - the label is optional
        pass
    return None


def _is_field_required(page: Page, field_sel: str) -> bool:
    """Check if a field has the HTML5 'required' attribute or aria-required='true'."""
    try:
        inp = page.locator(field_sel).first
        required = inp.get_attribute("required")
        aria_req = inp.get_attribute("aria-required")
        return bool(required or aria_req)
    except Exception:  # noqa: BLE001
        return False

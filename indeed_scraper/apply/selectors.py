"""Selector tables and field inspection for Indeed application forms.

The selectors live here as data, so a portal change is a data edit rather
than a code change, and the interaction module stays readable.

The inspection helpers are deliberately strict, and strict in ONE direction:
towards refusing the application rather than sending a broken one. A field
that cannot be inspected is treated as required, because a required field
left empty reaches the employer as a broken application.
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

#: The field groups that make a form an APPLICANT form. A form that carries
#: none of them is not a form this tool can fill, and pretending otherwise
#: produced a draft that claimed fields which had never reached the page.
#: The cover letter is deliberately NOT in this list: a form whose only
#: applicant box is a cover-letter textarea is still not fillable.
APPLICANT_INPUT_GROUPS: tuple[str, ...] = ("name", "email", "phone", "resume")


def has_applicant_input(page: Page) -> bool:
    """True when the page carries at least one FILLABLE applicant input.

    This is the question "is there anything here to fill?", asked by
    PRESENCE rather than by success. A form whose inputs are all empty
    because the operator has no value for them is still a form; a form with
    no applicant inputs at all is not, and the fill has to say so instead
    of returning an empty receipt that reads like a quiet success.
    """
    for group in APPLICANT_INPUT_GROUPS:
        locator, _selector = find_fillable(page, FIELD_SELECTORS[group])
        if locator is not None:
            return True
    return False



def _as_selectors(field_sels: str | tuple[str, ...]) -> tuple[str, ...]:
    """Accept either a single selector or a group of them."""
    if isinstance(field_sels, str):
        return (field_sels,)
    return tuple(field_sels)


def _is_fillable(locator) -> bool:
    """True when the locator points at an element the operator could type in.

    ``is_visible`` is the right question here: a hidden input is either a
    honeypot or a mirror of another field, and neither can be filled. It
    also never waits, so probing a form for the wrong selector shape does
    not stall the run.
    """
    try:
        return bool(locator.is_visible(timeout=1000))
    except Exception:  # noqa: BLE001 - an unreadable element is not fillable
        return False


def find_fillable(page: Page, field_sels: str | tuple[str, ...]):
    """The first FILLABLE locator of the group, or None.

    Returns the locator itself so the caller can fill it, and the selector
    that found it so the caller can look up the label.
    """
    for selector in _as_selectors(field_sels):
        try:
            locator = page.locator(selector).first
        except Exception:  # noqa: BLE001, S112 - a non-matching selector is expected
            continue
        if _is_fillable(locator):
            return locator, selector
    return None, ""


def has_fillable_input(page: Page, field_sels: str | tuple[str, ...]) -> bool:
    """True when at least one selector of the group matches a fillable input."""
    locator, _selector = find_fillable(page, field_sels)
    return locator is not None


def _find_required_field_label(page: Page, field_sels: str | tuple[str, ...]) -> str | None:
    """The visible label text for a field, so the operator knows what to fill.

    The label is looked up through the element's own ``id`` (``label[for=]``)
    and its ``aria-label``. The old lookup built ``label[for="input[name=...]"]``
    from the SELECTOR, which can never match a real form.
    """
    for selector in _as_selectors(field_sels):
        try:
            locator = page.locator(selector).first
        except Exception:  # noqa: BLE001, S112 - try the next selector
            continue
        if not _is_fillable(locator):
            continue
        try:
            aria = locator.get_attribute("aria-label")
            if aria and aria.strip():
                return aria.strip()
        except Exception:  # noqa: BLE001, S110 - the label is optional
            pass
        try:
            element_id = locator.get_attribute("id")
        except Exception:  # noqa: BLE001 - the label is optional
            element_id = None
        if element_id:
            try:
                label = page.locator(f'label[for="{element_id}"]').first
                if label.is_visible(timeout=1000):
                    text = label.text_content()
                    if text and text.strip():
                        return text.strip()
            except Exception:  # noqa: BLE001, S110 - the label is optional
                pass
    return None


def _is_field_required(page: Page, field_sels: str | tuple[str, ...]) -> bool:
    """True when the field is marked required in the DOM.

    The PRESENCE of the HTML5 ``required`` attribute is what matters, not its
    truthiness: a real browser reports a bare boolean attribute as the EMPTY
    STRING, so ``bool(required or aria_req)`` was False for every
    React-rendered ``required`` and the hard-refuse never fired.

    EVERY selector of the group is inspected. A form may carry the field
    under the second selector of the tuple, and checking only the first one
    missed it entirely.

    Fails CLOSED: when the attribute cannot be read, the field is treated as
    required, because a required field left empty reaches the employer as a
    broken application.
    """
    for selector in _as_selectors(field_sels):
        try:
            locator = page.locator(selector).first
            visible = locator.is_visible(timeout=1000)
        except Exception:  # noqa: BLE001 - the element cannot be inspected
            return True
        if not visible:
            continue
        try:
            required = locator.get_attribute("required")
        except Exception:  # noqa: BLE001 - the attribute cannot be read
            return True
        if required is not None:
            return True
        try:
            aria = locator.get_attribute("aria-required")
        except Exception:  # noqa: BLE001 - the attribute cannot be read
            return True
        if aria is not None and aria.strip().lower() == "true":
            return True
    return False

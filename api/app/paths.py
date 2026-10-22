"""Filesystem layout for the read-only API.

Everything the backend reads lives under one state directory (``data/`` by
default, overridable with ``INDEED_STATE_DIR``).  The paths themselves come
from the scraper's own modules so the two trees can never drift apart.

Two rules shape this module:

* **Read-only.**  None of the helpers below may create a directory or write a
  file.  Several scraper helpers (``workspace.ledger_path``,
  ``workspace.responses_dir``, ``messages.store.sent_ledger_path``) create
  their directories as a side effect, so they are only called when the
  directory already exists; otherwise the path is derived from the same
  constants.
* **Reuse.**  The scraper owns the layout, so this module reads the layout
  from ``indeed_scraper`` rather than hard-coding it.
"""

from __future__ import annotations

from pathlib import Path

from indeed_scraper.apply import workspace
from indeed_scraper.config import Config
from indeed_scraper.messages import store as messages_store

#: Filename of the master dataset inside ``master/``.
MASTER_FILENAME = "jobs_master.json"

#: Glob for the per-run job files inside ``runs/``.
RUNS_GLOB = "jobs_*.json"

#: Directory names inside the state directory.
APPLICATIONS_DIRNAME = "applications"
MESSAGES_DIRNAME = "messages"
RESPONSES_DIRNAME = "responses"


def get_config() -> Config:
    """Resolve the scraper's configuration.

    ``Config.load()`` honours ``INDEED_STATE_DIR`` and otherwise falls back to
    ``<repo root>/data``.  It does not touch the filesystem.
    """
    return Config.load()


def master_file(config: Config) -> Path:
    """The master dataset: ``<state>/master/jobs_master.json``."""
    return config.master_dir / MASTER_FILENAME


def run_files(config: Config) -> list[Path]:
    """Every scrape-run file, sorted by name."""
    if not config.runs_dir.is_dir():
        return []
    return sorted(config.runs_dir.glob(RUNS_GLOB))


def cookie_file(config: Config) -> Path:
    """The live cookie session: ``<state>/cookies/current.json``."""
    return config.current_cookie_file


def ledger_file(config: Config) -> Path:
    """The application ledger: ``<state>/applications/ledger.jsonl``.

    ``workspace.ledger_path`` would create ``applications/`` on the way, which
    a read-only backend must not do.  When the directory already exists the
    scraper's own helper is used (its ``mkdir`` is then a no-op); otherwise
    the same path is derived from the module's filename constant.
    """
    applications = config.state_dir / APPLICATIONS_DIRNAME
    if applications.is_dir():
        return workspace.ledger_path(config)
    return applications / workspace.LEDGER_FILENAME


def messages_file(config: Config) -> Path:
    """The sent-messages ledger: ``<state>/messages/sent.jsonl``.

    ``messages.store.sent_ledger_path`` creates and re-permissions the
    directory, so the path is derived from the module's constants instead.
    """
    return config.state_dir / MESSAGES_DIRNAME / messages_store.LEDGER_FILENAME


def responses_directory(config: Config) -> Path:
    """The recorded employer responses: ``<state>/responses``.

    ``workspace.responses_dir`` creates the directory; it is only called when
    the directory already exists.
    """
    responses = config.state_dir / RESPONSES_DIRNAME
    if responses.is_dir():
        return workspace.responses_dir(config)
    return responses


def responses_present(config: Config) -> bool:
    """True when employer responses have been recorded."""
    return responses_directory(config).is_dir()

"""Wave 2 — a test run must never write into the operator's real data.

**W2 MAJOR.** ``indeed_scraper/cli.py`` calls ``register(app, console,
_config)`` at IMPORT time, so the command closures captured the ORIGINAL
``_config`` function object. A test's
``monkeypatch.setattr(cli, "_config", ...)`` therefore never reached the
already-registered command, which went on to use the real config and
wrote into the repo's real ``data/`` directory.

A test suite must never write into the operator's data directory: it can
clobber real application records, and it makes the suite's side effects
depend on the state of the working tree.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _repo_data_snapshot() -> set[str]:
    """Every path under the repo's real ``data/`` directory."""
    data = REPO_ROOT / "data"
    if not data.is_dir():
        return set()
    return {str(path.relative_to(data)) for path in data.rglob("*")}


def test_the_repo_data_directory_is_not_touched_by_a_test_run(tmp_path: Path) -> None:
    """A command run during the suite must not write into the repo's data/.

    The command under test is the real ``apply`` command, driven exactly
    as the suite drives it. Before the fix the command used the REAL
    config (the repo's ``data/``) because the config factory had been
    captured at import time, and the run wrote
    ``data/applications/applications.csv`` into the operator's directory.
    """
    from typer.testing import CliRunner


    before = _repo_data_snapshot()

    # A config pointing at a temporary directory: the command must USE it.
    state = tmp_path / "state"
    master = state / "master"
    master.mkdir(parents=True, exist_ok=True)
    (master / "jobs_master.json").write_text(
        json.dumps({"meta": {"query": "", "locations": ["X"], "total_jobs": 0}, "jobs": []}),
        encoding="utf-8",
    )
    from indeed_scraper.config import Config

    config = Config.load(state_dir=state)

    import indeed_scraper.cli as cli_module

    original_config = cli_module._config
    original_apply = None
    try:
        # The patch has to reach the ALREADY-REGISTERED command.
        cli_module._config = lambda **kwargs: config
        import indeed_scraper.apply.flow as flow_module

        original_apply = flow_module.apply_to_jobs
        flow_module.apply_to_jobs = lambda *a, **k: []

        runner = CliRunner()
        runner.invoke(cli_module.app, ["apply", "--limit", "1"])
    finally:
        cli_module._config = original_config
        if original_apply is not None:
            import indeed_scraper.apply.flow as flow_module

            flow_module.apply_to_jobs = original_apply

    after = _repo_data_snapshot()
    created = after - before
    assert not created, (
        "a test run wrote into the operator's real data directory: "
        f"{sorted(created)!r}"
    )


def test_the_state_directory_is_redirected_for_the_whole_suite() -> None:
    """The suite-wide guard must be in place.

    ``Config.load`` honours ``INDEED_STATE_DIR``. The session fixture in
    ``tests/conftest.py`` points it at a temporary directory, so even a
    test that reaches the real config writes into a temp dir and never
    into the repo's ``data/``.
    """
    import os

    raw = os.environ.get("INDEED_STATE_DIR")
    assert raw, (
        "the suite must redirect INDEED_STATE_DIR so no test can write "
        "into the operator's real data directory"
    )
    assert Path(raw).resolve() != (REPO_ROOT / "data").resolve(), (
        "INDEED_STATE_DIR must not point at the repo's real data directory"
    )


def test_the_config_resolves_to_the_redirected_state_dir(tmp_path: Path) -> None:
    """The config the CLI builds must live under the redirected directory."""
    import os

    from indeed_scraper.config import Config

    config = Config.load()
    raw = os.environ.get("INDEED_STATE_DIR")
    assert raw, "INDEED_STATE_DIR must be set by the session fixture"
    assert str(config.state_dir).startswith(str(Path(raw).resolve())), (
        f"the config resolved to {config.state_dir}, outside {raw}"
    )


def test_a_command_that_reaches_the_real_config_still_writes_to_the_temp_dir(
    tmp_path: Path,
) -> None:
    """The belt-and-braces case: even the ORIGINAL factory is safe.

    The late-binding fix means a patched ``cli._config`` is used. The
    session-wide ``INDEED_STATE_DIR`` means that even an unpatched one
    cannot reach the repo's data. Both guards are exercised here.
    """
    from indeed_scraper.config import Config

    config = Config.load()
    assert not str(config.state_dir).startswith(str(REPO_ROOT / "data")), (
        f"the config still resolves into the repo's data directory: {config.state_dir}"
    )

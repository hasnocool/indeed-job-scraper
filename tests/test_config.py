"""Tests for Config state root and directory creation."""

from __future__ import annotations

from pathlib import Path

from indeed_scraper.config import Config


def test_config_default_state_root_is_data_dir(tmp_path: Path) -> None:
    """Default state root resolves to <repo>/data."""
    # Use a temp repo root
    config = Config.load(state_dir=tmp_path / "data")
    assert config.state_dir == (tmp_path / "data").resolve()
    # Ensure subdirs are accessible
    assert config.profile_dir == config.state_dir / "chrome-profile"
    assert config.cookies_dir == config.state_dir / "cookies"
    assert config.sessions_dir == config.state_dir / "cookies" / "sessions"
    assert config.runs_dir == config.state_dir / "runs"
    assert config.latest_dir == config.state_dir / "latest"
    assert config.master_dir == config.state_dir / "master"


def test_config_ensure_dirs_creates_all_dirs(tmp_path: Path) -> None:
    """ensure_dirs creates state_dir, profile_dir, cookies_dir, sessions_dir, runs_dir, latest_dir, master_dir."""
    config = Config.load(state_dir=tmp_path / "data")
    config.ensure_dirs()
    
    assert config.state_dir.exists()
    assert config.profile_dir.exists()
    assert config.cookies_dir.exists()
    assert config.sessions_dir.exists()
    assert config.runs_dir.exists()
    assert config.latest_dir.exists()
    assert config.master_dir.exists()


def test_config_env_override_works(tmp_path: Path) -> None:
    """INDEED_STATE_DIR env override works."""
    import os
    old = os.environ.get("INDEED_STATE_DIR")
    os.environ["INDEED_STATE_DIR"] = str(tmp_path / "custom_state")
    try:
        config = Config.load()
        assert config.state_dir == (tmp_path / "custom_state").resolve()
    finally:
        if old is not None:
            os.environ["INDEED_STATE_DIR"] = old
        else:
            os.environ.pop("INDEED_STATE_DIR", None)
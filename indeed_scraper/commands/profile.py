"""The ``profile`` commands: ``init``, ``show``, ``set-resume``.

The operator's profile holds the name, contact details, resume path and
screening answers that the composer answers a recruiter's questions from. It
is a private file (0600) because it holds personal data, and it is edited
through these commands rather than by hand so that the resume path is always
validated before it is saved.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

__all__ = ["register_profile_commands"]


def register_profile_commands(app: typer.Typer, console: Console) -> None:
    """Register the ``profile`` command group on the Typer app."""

    from ..apply.profile import (
        PROFILE_PATH,
        profile_template,
        save_profile,
        validate_resume,
    )

    profile_app = typer.Typer(help="Inspect and fix the operator profile.")
    app.add_typer(profile_app, name="profile")

    @profile_app.command("init")
    def profile_init(
        force: bool = typer.Option(False, "--force", help="Overwrite an existing profile.")
    ) -> None:
        """Write a profile template with the right permissions."""
        if PROFILE_PATH.exists() and not force:
            console.print(f"[yellow]{PROFILE_PATH} already exists - use --force to overwrite.[/yellow]")
            raise typer.Exit(code=1)
        path = save_profile(profile_template(), PROFILE_PATH)
        console.print(f"[green]wrote {path} (0600)[/green]")
        console.print(
            "[yellow]Next: put your resume PDF at the resume_path in that file, then run "
            "'profile set-resume <path>'.[/yellow]"
        )

    @profile_app.command("show")
    def profile_show() -> None:
        """Show the current profile and whether the resume is usable."""
        if not PROFILE_PATH.exists():
            console.print(f"[yellow]No profile at {PROFILE_PATH} - run 'profile init'.[/yellow]")
            raise typer.Exit(code=1)
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        table = Table(title=f"Profile {PROFILE_PATH}")
        table.add_column("Field")
        table.add_column("Value")
        for key, value in data.items():
            table.add_row(key, str(value)[:60])
        console.print(table)
        try:
            validate_resume(Path(str(data.get("resume_path", ""))).expanduser())
            console.print("[green]resume: ready[/green]")
        except Exception as error:  # noqa: BLE001 - reported to the operator, not raised
            console.print(f"[red]resume: {error}[/red]")

    @profile_app.command("set-resume")
    def profile_set_resume(
        resume: Path = typer.Argument(  # noqa: B008 - typer's required argument pattern
            ..., help="Path to your resume PDF."
        ),
    ) -> None:
        """Point the profile at your resume PDF (validated before it is saved)."""
        if not PROFILE_PATH.exists():
            console.print(f"[yellow]No profile at {PROFILE_PATH} - run 'profile init' first.[/yellow]")
            raise typer.Exit(code=1)
        try:
            validate_resume(resume.expanduser())
        except Exception as error:  # reported to the operator, not raised
            console.print(f"[red]{error}[/red]")
            raise typer.Exit(code=1) from error
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        data["resume_path"] = str(resume.expanduser())
        path = PROFILE_PATH
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        path.chmod(0o600)
        console.print(f"[green]resume_path set to {data['resume_path']}[/green]")

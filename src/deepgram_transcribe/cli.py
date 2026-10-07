"""Command line interface."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from . import __version__

app = typer.Typer(
    name="dgt",
    help="Transcribe recordings with Deepgram into Markdown + raw JSON.",
    no_args_is_help=True,
    add_completion=False,
)

COMMANDS = ("run", "render")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"deepgram-transcribe {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """Transcribe recordings with Deepgram into Markdown + raw JSON.

    `dgt FILES...` is a shortcut for `dgt run FILES...`.
    """


def _not_implemented(name: str) -> None:
    typer.echo(f"error: `{name}` is not implemented yet", err=True)
    raise typer.Exit(2)


@app.command()
def run(
    files: Annotated[list[str], typer.Argument(help="Files or globs to transcribe.")],
    config: Annotated[Path | None, typer.Option("--config", help="Config file override.")] = None,
    api_key: Annotated[
        str | None, typer.Option("--api-key", help="Deepgram API key (prefer the env var).")
    ] = None,
) -> None:
    """Transcribe recordings via Deepgram."""
    _not_implemented("run")


@app.command()
def render(
    json_files: Annotated[list[str], typer.Argument(help="Saved JSON files to re-render.")],
    config: Annotated[Path | None, typer.Option("--config", help="Config file override.")] = None,
) -> None:
    """Re-render Markdown from saved JSON, no API call."""
    _not_implemented("render")


def route_args(args: list[str]) -> list[str]:
    """Insert `run` for the bare `dgt FILES...` form."""
    if not args:
        return args
    if args[0] in COMMANDS or args[0] in ("--help", "-h", "--version"):
        return args
    return ["run", *args]


def main() -> None:
    app(args=route_args(sys.argv[1:]), prog_name="dgt")

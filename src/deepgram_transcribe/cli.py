"""Command line interface."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from . import __version__
from .client import DEFAULT_TIMEOUT
from .config import ConfigError, load_config, resolve_api_key
from .options import build_params, expand_inputs, parse_passthrough
from .renderer import resolve_date
from .runner import render_files, run_files

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


def _usage_error(msg: str) -> typer.Exit:
    typer.echo(f"error: {msg}", err=True)
    return typer.Exit(2)


def _noop(_msg: str) -> None:
    return None


@app.command()
def run(
    files: Annotated[list[str], typer.Argument(help="Files or globs to transcribe.")],
    config: Annotated[Path | None, typer.Option("--config", help="Config file override.")] = None,
    api_key: Annotated[
        str | None, typer.Option("--api-key", help="Deepgram API key (prefer the env var).")
    ] = None,
    output_dir: Annotated[
        Path | None, typer.Option("--output-dir", help="Where outputs go (created if missing).")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing outputs.")] = False,
    date: Annotated[
        str | None, typer.Option("--date", help="mtime | now | YYYY-MM-DD (default mtime).")
    ] = None,
    timeout: Annotated[
        float | None, typer.Option("--timeout", help="HTTP timeout in seconds (default 600).")
    ] = None,
    quiet: Annotated[bool, typer.Option("-q", "--quiet", help="Only errors.")] = False,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show details.")] = False,
    model: Annotated[str | None, typer.Option("--model")] = None,
    language: Annotated[str | None, typer.Option("--language")] = None,
    detect_language: Annotated[bool | None, typer.Option("--detect-language")] = None,
    diarize: Annotated[bool | None, typer.Option("--diarize/--no-diarize")] = None,
    smart_format: Annotated[bool | None, typer.Option("--smart-format/--no-smart-format")] = None,
    paragraphs: Annotated[bool | None, typer.Option("--paragraphs/--no-paragraphs")] = None,
    punctuate: Annotated[bool | None, typer.Option("--punctuate")] = None,
    utterances: Annotated[bool | None, typer.Option("--utterances")] = None,
    numerals: Annotated[bool | None, typer.Option("--numerals")] = None,
    filler_words: Annotated[bool | None, typer.Option("--filler-words")] = None,
    profanity_filter: Annotated[bool | None, typer.Option("--profanity-filter")] = None,
    keyterm: Annotated[
        list[str] | None, typer.Option("--keyterm", help="Key term (repeatable).")
    ] = None,
    redact: Annotated[
        list[str] | None, typer.Option("--redact", help="Redaction value (repeatable).")
    ] = None,
    summarize: Annotated[
        bool | None, typer.Option("--summarize", help="Sends summarize=v2 (English only).")
    ] = None,
    topics: Annotated[bool | None, typer.Option("--topics")] = None,
    intents: Annotated[bool | None, typer.Option("--intents")] = None,
    sentiment: Annotated[bool | None, typer.Option("--sentiment")] = None,
    detect_entities: Annotated[bool | None, typer.Option("--detect-entities")] = None,
    param: Annotated[
        list[str] | None,
        typer.Option("--param", help="Extra Deepgram query param KEY=VALUE (repeatable)."),
    ] = None,
) -> None:
    """Transcribe recordings via Deepgram."""
    try:
        cfg = load_config(config)
        key = resolve_api_key(api_key, cfg)
        passthrough = parse_passthrough(param or [])
        cli_opts = {
            "model": model,
            "language": language,
            "detect_language": detect_language,
            "diarize": diarize,
            "smart_format": smart_format,
            "paragraphs": paragraphs,
            "punctuate": punctuate,
            "utterances": utterances,
            "numerals": numerals,
            "filler_words": filler_words,
            "profanity_filter": profanity_filter,
            "keyterm": keyterm,
            "redact": redact,
            "summarize": summarize,
            "topics": topics,
            "intents": intents,
            "sentiment": sentiment,
            "detect_entities": detect_entities,
        }
        params, dropped = build_params(cli_opts, cfg.deepgram, passthrough)
        date_value = date or cfg.date or "mtime"
        if date_value != "mtime":
            resolve_date(date_value)  # validate early -> usage error
    except (ConfigError, ValueError) as exc:
        raise _usage_error(str(exc)) from exc
    http_timeout = timeout if timeout is not None else cfg.timeout or DEFAULT_TIMEOUT

    sources, unmatched = expand_inputs(files)
    if not sources:
        raise _usage_error("no input files matched: " + ", ".join(unmatched))
    for arg in unmatched:
        typer.echo(f"warning: no match for {arg!r}", err=True)
    if dropped:
        typer.echo(
            "warning: dropped English-only features (language must start with 'en' and "
            f"detect_language off): {', '.join(dropped)}",
            err=True,
        )

    out_dir = output_dir or (Path(cfg.output_dir).expanduser() if cfg.output_dir else None)
    result = run_files(
        sources,
        api_key=key,
        params=params,
        timeout=float(http_timeout),
        output_dir=out_dir,
        force=force,
        date=date_value,
        say=_noop if quiet else typer.echo,
        detail=typer.echo if verbose and not quiet else _noop,
        err=lambda m: typer.echo(m, err=True),
    )
    if not quiet:
        typer.echo(
            f"done: {len(result.transcribed)} transcribed, {len(result.skipped)} skipped, "
            f"{len(result.failed)} failed"
        )
    raise typer.Exit(result.exit_code)


@app.command()
def render(
    json_files: Annotated[
        list[str], typer.Argument(help="Saved JSON files or globs to re-render.")
    ],
    config: Annotated[Path | None, typer.Option("--config", help="Config file override.")] = None,
    output_dir: Annotated[
        Path | None, typer.Option("--output-dir", help="Where outputs go (created if missing).")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite existing outputs.")] = False,
    date: Annotated[
        str | None, typer.Option("--date", help="mtime | now | YYYY-MM-DD (default mtime).")
    ] = None,
    quiet: Annotated[bool, typer.Option("-q", "--quiet", help="Only errors.")] = False,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Show details.")] = False,
) -> None:
    """Re-render Markdown from saved JSON, no API call."""
    try:
        cfg = load_config(config)
        date_value = date or cfg.date or "mtime"
        if date_value != "mtime":
            resolve_date(date_value)  # validate early -> usage error
    except (ConfigError, ValueError) as exc:
        raise _usage_error(str(exc)) from exc

    sources, unmatched = expand_inputs(json_files)
    if not sources:
        raise _usage_error("no input files matched: " + ", ".join(unmatched))
    for arg in unmatched:
        typer.echo(f"warning: no match for {arg!r}", err=True)

    out_dir = output_dir or (Path(cfg.output_dir).expanduser() if cfg.output_dir else None)
    result = render_files(
        sources,
        output_dir=out_dir,
        force=force,
        date=date_value,
        say=_noop if quiet else typer.echo,
        detail=typer.echo if verbose and not quiet else _noop,
        err=lambda m: typer.echo(m, err=True),
    )
    if not quiet:
        typer.echo(
            f"done: {len(result.transcribed)} rendered, {len(result.skipped)} skipped, "
            f"{len(result.failed)} failed"
        )
    raise typer.Exit(result.exit_code)


def route_args(args: list[str]) -> list[str]:
    """Insert `run` for the bare `dgt FILES...` form."""
    if not args:
        return args
    if args[0] in COMMANDS or args[0] in ("--help", "-h", "--version"):
        return args
    return ["run", *args]


def main() -> None:
    app(args=route_args(sys.argv[1:]), prog_name="dgt")

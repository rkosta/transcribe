"""The `run` pipeline: inputs -> Deepgram -> <stem>.json + <stem>.md."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__, client
from .renderer import render_markdown, resolve_date

Transcribe = Callable[[str, Path, dict[str, Any], float], dict[str, Any]]


@dataclass
class RunResult:
    transcribed: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 1 if self.failed else 0


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat().replace("+00:00", "Z")


def output_paths(source: Path, output_dir: Path | None) -> tuple[Path, Path]:
    base = output_dir if output_dir is not None else source.parent
    return base / f"{source.stem}.json", base / f"{source.stem}.md"


def run_files(
    files: Sequence[Path],
    *,
    api_key: str,
    params: Mapping[str, Any],
    timeout: float,
    output_dir: Path | None,
    force: bool,
    date: str,
    say: Callable[[str], None] = lambda _m: None,
    detail: Callable[[str], None] = lambda _m: None,
    err: Callable[[str], None] = lambda _m: None,
    transcribe: Transcribe | None = None,
) -> RunResult:
    """Process each file; per-file failures are recorded and the run continues."""
    transcribe = transcribe or client.transcribe_file
    result = RunResult()
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
    total = len(files)
    for i, source in enumerate(files, 1):
        tag = f"[{i}/{total}] {source.name}"
        json_path, md_path = output_paths(source, output_dir)
        try:
            if not force and json_path.exists() and md_path.exists():
                say(f"{tag}: skipped (outputs exist; use --force)")
                result.skipped.append(source)
                continue
            say(f"{tag}: transcribing...")
            detail(f"  params: {dict(params)}")
            mtime = _iso(source.stat().st_mtime)
            response = transcribe(api_key, source, dict(params), timeout)
            doc = {
                "deepgram_transcribe": {
                    "version": __version__,
                    "created": _iso(datetime.now(UTC).timestamp()),
                    "source": {
                        "name": source.name,
                        "path": str(source.resolve()),
                        "mtime": mtime,
                    },
                    "options": dict(params),
                },
                "response": response,
            }
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(
                json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            md = render_markdown(doc, resolve_date(date, mtime=mtime), source.name)
            md_path.write_text(md, encoding="utf-8")
            say(f"{tag}: wrote {json_path.name}, {md_path.name}")
            detail(f"  -> {md_path}")
            result.transcribed.append(source)
        except Exception as exc:  # per-file: report and continue
            msg = str(exc) or type(exc).__name__
            err(f"error: {source}: {msg}")
            result.failed.append((source, msg))
    return result

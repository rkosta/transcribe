"""The `run` pipeline: inputs -> Deepgram -> <stem>.json + <stem>.md."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__, client
from .renderer import normalise, render_markdown, resolve_date

Transcribe = Callable[[str, Path, dict[str, Any], float], dict[str, Any]]


@dataclass
class RunResult:
    """Per-file outcome of ``run_files`` and ``render_files``."""

    transcribed: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        """1 if any file failed, else 0. Skipped files are not failures."""
        return 1 if self.failed else 0


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).isoformat().replace("+00:00", "Z")


def output_paths(source: Path, output_dir: Path | None) -> tuple[Path, Path]:
    """Return the ``(json, md)`` output paths: beside ``source`` unless ``output_dir`` is set."""
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
    """Transcribe each file and write ``<stem>.json`` and ``<stem>.md``.

    Args:
        files: Input files, processed in order.
        api_key: Deepgram API key.
        params: Deepgram query parameters; also saved in the JSON under ``options``.
        timeout: HTTP timeout in seconds.
        output_dir: Where outputs go; defaults to each source's directory.
        force: Overwrite existing outputs instead of skipping the file.
        date: ``--date`` value, resolved per file.
        say: Progress sink.
        detail: Verbose-only sink.
        err: Error sink.
        transcribe: Replacement for the Deepgram call, for tests.

    Returns:
        Per-file outcome. A failing file is recorded and the run continues; the caller
        should exit with ``RunResult.exit_code``.
    """
    transcribe = transcribe or client.transcribe_file
    result = RunResult()
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
    total = len(files)
    claimed: dict[Path, Path] = {}
    for i, source in enumerate(files, 1):
        tag = f"[{i}/{total}] {source.name}"
        json_path, md_path = output_paths(source, output_dir)
        try:
            # Same stem twice in one run would overwrite the first file's outputs.
            key = json_path.resolve()
            if key in claimed:
                raise RuntimeError(
                    f"output {json_path.name} collides with {claimed[key]} "
                    "(same stem in this run); use --output-dir or rename"
                )
            claimed[key] = source
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


def _check_wrapped(doc: dict[str, Any], name: str) -> None:
    """Reject wrong-typed wrapper fields with a clear message."""
    if "response" in doc and not isinstance(doc["response"], dict):
        raise RuntimeError(f"invalid response in {name}: expected an object")
    meta = doc.get("deepgram_transcribe")
    if meta is None:
        return
    bad = not isinstance(meta, dict)
    if not bad:
        for key in ("source", "options"):
            if meta.get(key) is not None and not isinstance(meta[key], dict):
                bad = True
        src = meta.get("source")
        if isinstance(src, dict):
            for key in ("name", "mtime"):
                if src.get(key) is not None and not isinstance(src[key], str):
                    bad = True
    if bad:
        raise RuntimeError(f"invalid deepgram_transcribe metadata in {name}")


def render_files(
    files: Sequence[Path],
    *,
    output_dir: Path | None,
    force: bool,
    date: str,
    say: Callable[[str], None] = lambda _m: None,
    detail: Callable[[str], None] = lambda _m: None,
    err: Callable[[str], None] = lambda _m: None,
) -> RunResult:
    """Re-render ``<stem>.md`` from saved JSON (wrapped or bare). No network, no API key.

    Arguments mirror ``run_files`` without the API options; ``files`` are the saved JSON files.

    Returns:
        Per-file outcome. Unreadable or non-Deepgram JSON is recorded as a failure and the
        run continues; exit with ``RunResult.exit_code``.
    """
    result = RunResult()
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
    total = len(files)
    claimed: dict[Path, Path] = {}
    for i, source in enumerate(files, 1):
        tag = f"[{i}/{total}] {source.name}"
        base = output_dir if output_dir is not None else source.parent
        md_path = base / f"{source.stem}.md"
        try:
            # Same stem twice in one run would overwrite the first file's outputs.
            key = md_path.resolve()
            if key in claimed:
                raise RuntimeError(
                    f"output {md_path.name} collides with {claimed[key]} "
                    "(same stem in this run); use --output-dir or rename"
                )
            claimed[key] = source
            if not force and md_path.exists():
                say(f"{tag}: skipped ({md_path.name} exists; use --force)")
                result.skipped.append(source)
                continue
            try:
                doc = json.loads(source.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise RuntimeError(f"cannot read JSON: {exc}") from exc
            if not isinstance(doc, dict):
                raise RuntimeError("not a Deepgram JSON object")
            _check_wrapped(doc, source.name)
            meta, response = normalise(doc, source.stem)
            if not isinstance(response.get("results"), dict):
                raise RuntimeError("no Deepgram response found (missing 'results')")
            mtime = (meta.get("source") or {}).get("mtime") or _iso(source.stat().st_mtime)
            md = render_markdown(doc, resolve_date(date, mtime=mtime), source.stem)
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(md, encoding="utf-8")
            say(f"{tag}: wrote {md_path.name}")
            detail(f"  -> {md_path}")
            result.transcribed.append(source)
        except Exception as exc:  # per-file: report and continue
            msg = str(exc) or type(exc).__name__
            err(f"error: {source}: {msg}")
            result.failed.append((source, msg))
    return result

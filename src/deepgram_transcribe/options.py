"""Option merging and input expansion for `run`. Pure apart from filesystem globbing."""

from __future__ import annotations

import glob
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "model": "nova-3",
    "language": "multi",
    "diarize": True,
    "smart_format": True,
    "paragraphs": True,
}
ENGLISH_ONLY = ("summarize", "topics", "intents", "sentiment")
_GLOB_CHARS = set("*?[")


def parse_passthrough(items: Sequence[str]) -> dict[str, list[str]]:
    """Parse ``KEY=VALUE`` items into ``{key: [values]}``; repeated keys accumulate.

    Raises:
        ValueError: If an item has no ``=`` or an empty key.
    """
    out: dict[str, list[str]] = {}
    for item in items:
        key, sep, value = item.partition("=")
        key = key.strip()
        if not sep or not key:
            raise ValueError(f"invalid --param {item!r}: expected KEY=VALUE")
        out.setdefault(key, []).append(value)
    return out


def _normalise(key: str, value: Any) -> Any:
    """Map a value to its wire form; None means "omit the parameter"."""
    if key == "summarize":
        if value is True:
            return "v2"
        if value is False:
            return None
    if isinstance(value, tuple):
        value = list(value)
    if isinstance(value, list) and not value:
        return None
    return value


def build_params(
    cli: Mapping[str, Any],
    config_deepgram: Mapping[str, Any],
    passthrough: Mapping[str, list[str]],
) -> tuple[dict[str, Any], list[str]]:
    """Merge options into Deepgram query parameters.

    Precedence, highest first: passthrough (``--param``), CLI flags, config ``[deepgram]``,
    ``DEFAULTS``.

    Args:
        cli: CLI flag values. None or an empty list/tuple means "not given".
        config_deepgram: The config file's ``[deepgram]`` table.
        passthrough: Parsed ``--param`` values; a single value is unwrapped from its list.

    Returns:
        ``(params, dropped)``: the parameters to send, and the English-only features
        removed because the language isn't English.
    """
    params: dict[str, Any] = dict(DEFAULTS)
    for source in (config_deepgram, cli):
        for key, value in source.items():
            if value is None or (isinstance(value, list | tuple) and not value):
                continue
            params[key] = value
    for key, values in passthrough.items():
        params[key] = values[0] if len(values) == 1 else list(values)

    params = {k: v for k in params if (v := _normalise(k, params[k])) is not None}

    # These features are English-only; drop them (and report) rather than fail the request.
    # detect_language may resolve to non-English, so it counts as non-English too.
    language = str(params.get("language", ""))
    english_ok = language.lower().startswith("en") and not _truthy(params.get("detect_language"))
    dropped: list[str] = []
    if not english_ok:
        for key in ENGLISH_ONLY:
            if params.get(key) not in (None, False):
                dropped.append(key)
            params.pop(key, None)
    return params, dropped


def _truthy(value: Any) -> bool:
    """Passthrough values are strings: "false"/"0"/"no"/"off" (any case) mean off."""
    if isinstance(value, list | tuple):
        value = value[-1] if value else None
    if isinstance(value, str):
        return value.strip().lower() not in ("", "false", "0", "no", "off")
    return bool(value)


def expand_inputs(args: Sequence[str]) -> tuple[list[Path], list[str]]:
    """Expand files and globs (``**`` supported) into existing files, deduped in order.

    Returns:
        ``(files, unmatched)``, where ``unmatched`` holds the args that matched nothing.
    """
    files: list[Path] = []
    seen: set[Path] = set()
    unmatched: list[str] = []

    def add(p: Path) -> None:
        key = p.resolve()
        if key not in seen:
            seen.add(key)
            files.append(p)

    for arg in args:
        path = Path(arg).expanduser()
        if path.is_file():
            add(path)
            continue
        hits: list[Path] = []
        if _GLOB_CHARS & set(arg):
            hits = [Path(h) for h in sorted(glob.glob(str(path), recursive=True))]
            hits = [h for h in hits if h.is_file()]
        if hits:
            for h in hits:
                add(h)
        else:
            unmatched.append(arg)
    return files, unmatched

"""Config file loading and API key resolution."""

from __future__ import annotations

import math
import os
import sys
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

KNOWN_KEYS = frozenset({"api_key", "output_dir", "date", "timeout", "deepgram"})
API_KEY_ENV = "DEEPGRAM_API_KEY"


class ConfigError(Exception):
    """Usage/config problem; the CLI maps this to exit code 2."""


@dataclass
class Config:
    """Settings read from the TOML config file; unset fields are None or empty."""

    api_key: str | None = None
    output_dir: str | None = None
    date: str | None = None
    timeout: float | None = None
    deepgram: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None


def validate_timeout(value: object, where: str) -> float:
    """Return ``value`` as a float, requiring a positive, finite number (bools rejected).

    Args:
        value: Raw value from the config file or CLI.
        where: Label used in the error message, e.g. ``--timeout``.

    Raises:
        ConfigError: If the value is not a positive finite number.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"{where} must be a number")
    if not math.isfinite(value) or value <= 0:
        raise ConfigError(f"{where} must be a positive number")
    return float(value)


def _warn_stderr(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)


def resolve_config_path(
    explicit: Path | str | None = None, env: Mapping[str, str] | None = None
) -> Path:
    """Return the config file path (it may not exist).

    Precedence: ``explicit`` (``--config``), then
    ``$XDG_CONFIG_HOME/deepgram-transcribe/config.toml``, then ``~/.config/...``.
    """
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ if env is None else env
    xdg = env.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "deepgram-transcribe" / "config.toml"


def load_config(
    explicit: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    warn: Callable[[str], None] = _warn_stderr,
) -> Config:
    """Load the config file.

    Args:
        explicit: Path from ``--config``. Must exist if given.
        env: Environment mapping; defaults to ``os.environ``.
        warn: Called once per unknown top-level key.

    Returns:
        The parsed config, or an empty one if the default file doesn't exist.

    Raises:
        ConfigError: On a missing explicit file, invalid TOML, or wrongly typed values.
    """
    path = resolve_config_path(explicit, env)
    if not path.is_file():
        if explicit:
            raise ConfigError(f"config file not found: {path}")
        return Config()
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid config file {path}: {exc}") from exc

    for key in sorted(set(data) - KNOWN_KEYS):
        warn(f"unknown config key {key!r} in {path}")

    deepgram = data.get("deepgram", {})
    if not isinstance(deepgram, dict):
        raise ConfigError(f"[deepgram] in {path} must be a table")
    timeout = data.get("timeout")
    if "timeout" in data:
        timeout = validate_timeout(timeout, f"timeout in {path}")
    for key in ("api_key", "output_dir", "date"):
        if key in data and not isinstance(data[key], str):
            raise ConfigError(f"{key} in {path} must be a string")
    return Config(
        api_key=data.get("api_key"),
        output_dir=data.get("output_dir"),
        date=data.get("date"),
        timeout=timeout,
        deepgram=dict(deepgram),
        path=path,
    )


def resolve_api_key(
    cli_key: str | None,
    config: Config,
    env: Mapping[str, str] | None = None,
) -> str:
    """Return the API key: ``--api-key`` > ``DEEPGRAM_API_KEY`` > config file, stripped.

    Blank values are skipped. Error messages never include the key.

    Raises:
        ConfigError: If no source provides a key.
    """
    env = os.environ if env is None else env
    for candidate in (cli_key, env.get(API_KEY_ENV), config.api_key):
        if candidate and candidate.strip():
            return candidate.strip()
    raise ConfigError(
        f"no Deepgram API key: pass --api-key, set {API_KEY_ENV}, or add api_key to the config file"
    )

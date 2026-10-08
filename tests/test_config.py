from pathlib import Path

import pytest

from deepgram_transcribe.config import (
    ConfigError,
    load_config,
    resolve_api_key,
    resolve_config_path,
)


def test_path_explicit_wins(tmp_path):
    p = tmp_path / "x.toml"
    assert resolve_config_path(p, {"XDG_CONFIG_HOME": str(tmp_path / "xdg")}) == p


def test_path_xdg(tmp_path):
    got = resolve_config_path(None, {"XDG_CONFIG_HOME": str(tmp_path)})
    assert got == tmp_path / "deepgram-transcribe" / "config.toml"


def test_path_home_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    got = resolve_config_path(None, {})
    assert got == Path(tmp_path) / ".config/deepgram-transcribe/config.toml"


def test_missing_default_file_ok(tmp_path):
    cfg = load_config(None, {"XDG_CONFIG_HOME": str(tmp_path)})
    assert cfg.api_key is None and cfg.deepgram == {}


def test_missing_explicit_file_errors(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.toml", {})


def test_load_values_and_unknown_keys(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text(
        'api_key = "k"\noutput_dir = "~/T"\ndate = "now"\ntimeout = 30\nbogus = 1\n'
        '[deepgram]\nmodel = "nova-3"\nkeyterm = ["a", "b"]\n'
    )
    warnings: list[str] = []
    cfg = load_config(f, {}, warn=warnings.append)
    assert (cfg.api_key, cfg.output_dir, cfg.date, cfg.timeout) == ("k", "~/T", "now", 30)
    assert cfg.deepgram == {"model": "nova-3", "keyterm": ["a", "b"]}
    assert len(warnings) == 1 and "bogus" in warnings[0]


def test_invalid_toml(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text("= nope")
    with pytest.raises(ConfigError):
        load_config(f, {})


def _cfg(tmp_path, key):
    f = tmp_path / "c.toml"
    f.write_text(f'api_key = "{key}"\n' if key else "")
    return load_config(f, {})


def test_api_key_precedence(tmp_path):
    cfg = _cfg(tmp_path, "from-config")
    env = {"DEEPGRAM_API_KEY": "from-env"}
    assert resolve_api_key("from-cli", cfg, env) == "from-cli"
    assert resolve_api_key(None, cfg, env) == "from-env"
    assert resolve_api_key(None, cfg, {}) == "from-config"


def test_api_key_env_default_uses_os_environ(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPGRAM_API_KEY", "env-key")
    assert resolve_api_key(None, _cfg(tmp_path, "cfg")) == "env-key"


def test_api_key_missing_message(tmp_path):
    with pytest.raises(ConfigError) as exc:
        resolve_api_key(None, _cfg(tmp_path, None), {})
    assert "DEEPGRAM_API_KEY" in str(exc.value)


def test_api_key_blank_is_ignored(tmp_path):
    assert resolve_api_key("  ", _cfg(tmp_path, "cfg"), {"DEEPGRAM_API_KEY": ""}) == "cfg"


def _write(tmp_path, text):
    f = tmp_path / "c.toml"
    f.write_text(text)
    return f


def test_deepgram_not_a_table(tmp_path):
    with pytest.raises(ConfigError, match="table"):
        load_config(_write(tmp_path, 'deepgram = "x"\n'), {})


@pytest.mark.parametrize("val", ['"fast"', "true", "0", "-5", "nan"])
def test_bad_timeout(tmp_path, val):
    with pytest.raises(ConfigError, match="timeout"):
        load_config(_write(tmp_path, f"timeout = {val}\n"), {})


@pytest.mark.parametrize("key", ["api_key", "output_dir", "date"])
def test_non_string_values(tmp_path, key):
    with pytest.raises(ConfigError, match=key):
        load_config(_write(tmp_path, f"{key} = 5\n"), {})


def test_no_warnings_for_known_keys(tmp_path):
    f = _write(
        tmp_path,
        'api_key = "k"\noutput_dir = "o"\ndate = "now"\ntimeout = 1.5\n[deepgram]\nmodel = "x"\n',
    )
    warnings: list[str] = []
    cfg = load_config(f, {}, warn=warnings.append)
    assert warnings == [] and cfg.timeout == 1.5

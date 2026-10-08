import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from deepgram_transcribe import client
from deepgram_transcribe.cli import app

FIXTURES = Path(__file__).parent / "fixtures"
KEY = "sk-test-secret-key-123"
runner = CliRunner()

DEFAULT_PARAMS = {
    "model": "nova-3",
    "language": "multi",
    "diarize": True,
    "smart_format": True,
    "paragraphs": True,
}


@pytest.fixture
def calls(monkeypatch, tmp_path):
    """Mock the Deepgram wrapper; isolate config and env."""
    recorded: list[dict] = []
    response = json.loads((FIXTURES / "diarized_paragraphs.json").read_text())
    response = response.get("response", response)

    def fake(api_key, path, params, timeout=600.0):
        recorded.append({"key": api_key, "path": path, "params": params, "timeout": timeout})
        return response

    monkeypatch.setattr(client, "transcribe_file", fake)
    monkeypatch.setenv("DEEPGRAM_API_KEY", KEY)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return recorded


@pytest.fixture
def audio(tmp_path):
    d = tmp_path / "in"
    d.mkdir()
    f = d / "meeting.m4a"
    f.write_bytes(b"fake audio")
    return f


def run(*args):
    return runner.invoke(app, ["run", *map(str, args)])


def test_defaults(calls, audio):
    res = run(audio)
    assert res.exit_code == 0, res.output
    assert calls[0]["params"] == DEFAULT_PARAMS
    assert calls[0]["timeout"] == 600
    assert calls[0]["key"] == KEY
    assert (audio.parent / "meeting.json").exists()
    assert (audio.parent / "meeting.md").exists()


def test_bare_form_runs(calls, audio):
    from deepgram_transcribe.cli import route_args

    res = runner.invoke(app, route_args([str(audio)]))
    assert res.exit_code == 0 and len(calls) == 1


def test_config_then_cli_override(calls, audio, tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text(
        'timeout = 42\n[deepgram]\nmodel = "nova-2"\nkeyterm = ["Reaktor", "Hermes"]\n'
        'language = "pt"\n'
    )
    assert run(audio, "--config", cfg).exit_code == 0
    assert calls[0]["params"] == {
        **DEFAULT_PARAMS,
        "model": "nova-2",
        "language": "pt",
        "keyterm": ["Reaktor", "Hermes"],
    }
    assert calls[0]["timeout"] == 42

    calls.clear()
    res = run(
        audio, "--config", cfg, "--model", "nova-3", "--no-diarize", "--timeout", "7", "--force"
    )
    assert res.exit_code == 0
    assert calls[0]["params"]["model"] == "nova-3"
    assert calls[0]["params"]["diarize"] is False
    assert calls[0]["timeout"] == 7


def test_keyterm_and_redact_repeat(calls, audio):
    run(audio, "--keyterm", "A", "--keyterm", "B", "--redact", "pci", "--redact", "ssn")
    p = calls[0]["params"]
    assert p["keyterm"] == ["A", "B"]
    assert p["redact"] == ["pci", "ssn"]


def test_typed_flags_map_one_to_one(calls, audio):
    run(
        audio,
        "--punctuate",
        "--utterances",
        "--numerals",
        "--filler-words",
        "--profanity-filter",
        "--detect-entities",
        "--language",
        "en",
        "--summarize",
        "--topics",
        "--intents",
        "--sentiment",
    )
    assert calls[0]["params"] == {
        **DEFAULT_PARAMS,
        "language": "en",
        "punctuate": True,
        "utterances": True,
        "numerals": True,
        "filler_words": True,
        "profanity_filter": True,
        "detect_entities": True,
        "summarize": "v2",
        "topics": True,
        "intents": True,
        "sentiment": True,
    }


def test_passthrough_wins_and_repeats(calls, audio):
    run(
        audio,
        "--model",
        "nova-2",
        "--param",
        "model=nova-3-medical",
        "--param",
        "tag=a",
        "--param",
        "tag=b",
        "--param",
        "search=x",
    )
    p = calls[0]["params"]
    assert p["model"] == "nova-3-medical"
    assert p["tag"] == ["a", "b"]
    assert p["search"] == "x"


def test_bad_param_is_usage_error(calls, audio):
    assert run(audio, "--param", "novalue").exit_code == 2
    assert calls == []


def test_english_only_drop_with_single_warning(calls, audio):
    res = run(audio, "--summarize", "--topics", "--intents", "--sentiment")
    assert res.exit_code == 0
    p = calls[0]["params"]
    assert not {"summarize", "topics", "intents", "sentiment"} & p.keys()
    warnings = [ln for ln in res.output.splitlines() if "dropped English-only" in ln]
    assert len(warnings) == 1
    for name in ("summarize", "topics", "intents", "sentiment"):
        assert name in warnings[0]


def test_english_only_dropped_when_detect_language(calls, audio):
    res = run(audio, "--language", "en-US", "--detect-language", "--topics")
    assert "topics" not in calls[0]["params"]
    assert "dropped English-only" in res.output
    assert calls[0]["params"]["detect_language"] is True


def test_english_kept_without_warning(calls, audio):
    res = run(audio, "--language", "en", "--summarize")
    assert calls[0]["params"]["summarize"] == "v2"
    assert "dropped" not in res.output


def test_param_detect_language_false_is_off(calls, audio):
    res = run(audio, "--language", "en", "--topics", "--param", "detect_language=FALSE")
    assert calls[0]["params"]["topics"] is True
    assert "dropped" not in res.output


def _two_dirs(tmp_path, names=("mon", "tue")):
    for n in names:
        (tmp_path / "d" / n).mkdir(parents=True)
        (tmp_path / "d" / n / "audio.m4a").write_bytes(n.encode())


@pytest.mark.parametrize("force", [False, True])
def test_stem_collision_output_dir_is_error(calls, tmp_path, force):
    _two_dirs(tmp_path)
    out = tmp_path / "out"
    args = [str(tmp_path / "d" / "**" / "audio.m4a"), "--output-dir", out]
    res = run(*args, *(["--force"] if force else []))
    assert res.exit_code == 1, res.output
    assert "collides with" in res.output and "skipped (outputs" not in res.output
    assert len(calls) == 1
    first = json.loads((out / "audio.json").read_text())
    assert first["deepgram_transcribe"]["source"]["path"] == calls[0]["path"].resolve().as_posix()


@pytest.mark.parametrize("force", [False, True])
def test_stem_collision_same_dir_different_ext(calls, tmp_path, force):
    d = tmp_path / "d"
    d.mkdir()
    (d / "talk.m4a").write_bytes(b"a")
    (d / "talk.mp4").write_bytes(b"b")
    res = run(d / "talk.*", *(["--force"] if force else []))
    assert res.exit_code == 1, res.output
    assert "collides with" in res.output and len(calls) == 1


def test_skip_then_force(calls, audio):
    assert run(audio).exit_code == 0
    res = run(audio)
    assert res.exit_code == 0 and "skipped" in res.output
    assert len(calls) == 1
    assert run(audio, "--force").exit_code == 0
    assert len(calls) == 2


def test_only_one_output_exists_is_not_skipped(calls, audio):
    (audio.parent / "meeting.json").write_text("{}")
    assert run(audio).exit_code == 0
    assert len(calls) == 1


def test_output_dir_created(calls, audio, tmp_path):
    out = tmp_path / "deep" / "out"
    assert run(audio, "--output-dir", out).exit_code == 0
    assert (out / "meeting.json").exists() and (out / "meeting.md").exists()
    assert not (audio.parent / "meeting.json").exists()


def test_glob_expansion_dedupe_and_recursion(calls, tmp_path):
    root = tmp_path / "g"
    (root / "sub").mkdir(parents=True)
    a, b, c = root / "a.mp3", root / "b.wav", root / "sub" / "c.mp3"
    for f in (a, b, c):
        f.write_bytes(b"x")
    res = run(root / "*.mp3", a, root / "**" / "*.mp3", b)
    assert res.exit_code == 0, res.output
    assert [c_["path"].name for c_ in calls] == ["a.mp3", "c.mp3", "b.wav"]


def test_no_match_exit_2(calls, tmp_path):
    res = run(tmp_path / "nothing*.mp3")
    assert res.exit_code == 2 and calls == []


def test_partial_unmatched_still_runs(calls, audio, tmp_path):
    res = run(audio, tmp_path / "missing.mp3")
    assert res.exit_code == 0 and len(calls) == 1


def test_per_file_failure_exit_1_and_continue(monkeypatch, calls, tmp_path):
    files = []
    for name in ("a.mp3", "b.mp3"):
        f = tmp_path / name
        f.write_bytes(b"x")
        files.append(f)
    ok = client.transcribe_file

    def flaky(api_key, path, params, timeout=600.0):
        if path.name == "a.mp3":
            raise client.TranscriptionError("HTTP 400: bad audio")
        return ok(api_key, path, params, timeout)

    monkeypatch.setattr(client, "transcribe_file", flaky)
    res = run(*files)
    assert res.exit_code == 1
    assert "a.mp3" in res.output and "bad audio" in res.output
    assert (tmp_path / "b.md").exists() and not (tmp_path / "a.json").exists()


def test_missing_key_exit_2(calls, audio, monkeypatch):
    monkeypatch.delenv("DEEPGRAM_API_KEY")
    res = run(audio)
    assert res.exit_code == 2 and "API key" in res.output and calls == []


def test_invalid_date_exit_2(calls, audio):
    assert run(audio, "--date", "yesterday").exit_code == 2


def test_date_option_in_markdown(calls, audio):
    run(audio, "--date", "2026-01-02")
    assert "date: 2026-01-02" in (audio.parent / "meeting.md").read_text()


def test_saved_json_wrapped_without_key(calls, audio):
    res = run(audio, "--api-key", KEY, "--keyterm", "X", "-v")
    assert res.exit_code == 0
    text = (audio.parent / "meeting.json").read_text()
    assert KEY not in text and KEY not in res.output
    doc = json.loads(text)
    meta = doc["deepgram_transcribe"]
    assert meta["source"]["name"] == "meeting.m4a"
    assert meta["options"]["keyterm"] == ["X"]
    assert "results" in doc["response"]


def test_quiet_suppresses_progress(calls, audio):
    res = run(audio, "-q")
    assert res.exit_code == 0 and res.output.strip() == ""


def test_progress_shown_by_default(calls, audio):
    assert "meeting.m4a" in run(audio).output


def test_wrapper_scrubs_key_from_errors(monkeypatch, audio):
    class Boom(Exception):
        status_code = 401
        body = f"bad key {KEY}"

    class FakeClient:
        def __init__(self, **_):
            raise Boom()

    import deepgram

    monkeypatch.setattr(deepgram, "DeepgramClient", FakeClient)
    with pytest.raises(client.TranscriptionError) as ei:
        client.transcribe_file(KEY, audio, {})
    assert KEY not in str(ei.value) and "401" in str(ei.value)


def test_wrapper_sends_params_to_sdk(monkeypatch, audio):
    seen = {}

    class Resp:
        def model_dump(self, **_):
            return {"metadata": {}, "results": {"channels": []}}

    class Media:
        def transcribe_file(self, *, request, request_options):
            seen["req"], seen["opts"] = request, request_options
            return Resp()

    class FakeClient:
        def __init__(self, **kw):
            seen["init"] = kw
            self.listen = type("L", (), {"v1": type("V", (), {"media": Media()})()})()

    import deepgram

    monkeypatch.setattr(deepgram, "DeepgramClient", FakeClient)
    out = client.transcribe_file(KEY, audio, {"keyterm": ["a", "b"]}, timeout=99)
    assert out["results"] == {"channels": []}
    assert seen["req"] == b"fake audio"
    assert seen["opts"]["additional_query_parameters"] == {"keyterm": ["a", "b"]}
    assert seen["opts"]["timeout"] == 99 and seen["init"]["timeout"] == 99


@pytest.mark.live
def test_live_smoke(tmp_path, monkeypatch):
    import math
    import os
    import struct
    import wave

    key = os.environ.get("DEEPGRAM_API_KEY")
    if not key:
        pytest.skip("DEEPGRAM_API_KEY not set")
    wav = tmp_path / "tone.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(
            b"".join(
                struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / 8000)))
                for i in range(8000)
            )
        )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    res = runner.invoke(app, ["run", str(wav)])
    assert res.exit_code == 0, res.output
    doc = json.loads((tmp_path / "tone.json").read_text())
    assert key not in json.dumps(doc)
    assert (tmp_path / "tone.md").read_text().startswith("---")
    assert "results" in doc["response"]


@pytest.mark.parametrize("bad", ["0", "-3", "abc"])
def test_bad_cli_timeout_exit_2(calls, audio, bad):
    res = run("--timeout", bad, audio)
    assert res.exit_code == 2 and not calls


def test_config_timeout_zero_is_error(calls, audio, tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text("timeout = 0\n")
    res = run("--config", cfg, audio)
    assert res.exit_code == 2 and not calls and "timeout" in res.output


def test_timeout_passed_through(calls, audio):
    assert run("--timeout", "42", audio).exit_code == 0
    assert calls[0]["timeout"] == 42.0


def test_output_dir_is_file(calls, audio, tmp_path):
    f = tmp_path / "afile"
    f.write_text("x")
    res = run("--output-dir", f, audio)
    assert res.exit_code == 2 and "not a directory" in res.output
    assert "Traceback" not in res.output and not calls


def test_output_dir_under_file(calls, audio, tmp_path):
    f = tmp_path / "afile"
    f.write_text("x")
    res = run("--output-dir", f / "sub", audio)
    assert res.exit_code == 2 and "cannot be created" in res.output
    assert "Traceback" not in res.output and not calls

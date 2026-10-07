import json
import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from deepgram_transcribe import client
from deepgram_transcribe.cli import app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


@pytest.fixture(autouse=True)
def no_key_no_network(monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    def boom(*a, **k):
        raise AssertionError("network call in render")

    monkeypatch.setattr(client, "transcribe_file", boom)


@pytest.fixture
def wrapped(tmp_path):
    d = tmp_path / "in"
    d.mkdir()
    p = d / "meeting.json"
    shutil.copy(FIXTURES / "wrapped.json", p)
    return p


@pytest.fixture
def bare(tmp_path):
    d = tmp_path / "in"
    d.mkdir(exist_ok=True)
    doc = json.loads((FIXTURES / "diarized_paragraphs.json").read_text())
    p = d / "standup.json"
    p.write_text(json.dumps(doc.get("response", doc)))
    os.utime(p, (1_700_000_000, 1_700_000_000))  # 2023-11-14
    return p


def render(*args):
    return runner.invoke(app, ["render", *map(str, args)])


def test_wrapped_next_to_json(wrapped):
    res = render(wrapped)
    assert res.exit_code == 0, res.output
    md = (wrapped.parent / "meeting.md").read_text()
    assert md.startswith("---")
    assert "date: 2026-10-05" in md  # mtime stored in the JSON


def test_bare_uses_stem_and_file_mtime(bare):
    res = render(bare)
    assert res.exit_code == 0, res.output
    md = (bare.parent / "standup.md").read_text()
    assert "source: standup" in md
    assert "date: 2023-11-14" in md


def test_skip_and_force(wrapped):
    assert render(wrapped).exit_code == 0
    md = wrapped.parent / "meeting.md"
    md.write_text("sentinel")
    res = render(wrapped)
    assert res.exit_code == 0 and "skipped" in res.output
    assert md.read_text() == "sentinel"
    assert render("--force", wrapped).exit_code == 0
    assert md.read_text().startswith("---")


def test_output_dir(wrapped, tmp_path):
    out = tmp_path / "out" / "nested"
    res = render("--output-dir", out, wrapped)
    assert res.exit_code == 0, res.output
    assert (out / "meeting.md").exists()
    assert not (wrapped.parent / "meeting.md").exists()


def test_glob(wrapped, bare):
    res = render(wrapped.parent / "*.json")
    assert res.exit_code == 0, res.output
    assert (wrapped.parent / "meeting.md").exists()
    assert (wrapped.parent / "standup.md").exists()


def test_date_variants(wrapped):
    md = wrapped.parent / "meeting.md"
    assert render("--date", "2020-01-02", wrapped).exit_code == 0
    assert "date: 2020-01-02" in md.read_text()
    assert render("--force", "--date", "now", wrapped).exit_code == 0
    assert "date: 2020-01-02" not in md.read_text()
    assert render("--force", "--date", "mtime", wrapped).exit_code == 0
    assert "date: 2026-10-05" in md.read_text()


def test_invalid_date_exit_2(wrapped):
    assert render("--date", "yesterday", wrapped).exit_code == 2


def test_invalid_json_continues(wrapped, tmp_path):
    bad = wrapped.parent / "a_bad.json"
    bad.write_text("{not json")
    notdg = wrapped.parent / "b_other.json"
    notdg.write_text('{"hello": 1}')
    res = render(bad, notdg, wrapped)
    assert res.exit_code == 1
    assert (wrapped.parent / "meeting.md").exists()
    assert not (wrapped.parent / "a_bad.md").exists()
    assert not (wrapped.parent / "b_other.md").exists()
    assert "a_bad.json" in res.output and "b_other.json" in res.output


def test_stem_collision_is_error(tmp_path, wrapped):
    other = tmp_path / "other"
    other.mkdir()
    shutil.copy(wrapped, other / "meeting.json")
    out = tmp_path / "out"
    res = render("--output-dir", out, wrapped, other / "meeting.json")
    assert res.exit_code == 1
    assert "collides" in res.output


def test_no_match_exit_2(tmp_path):
    assert render(tmp_path / "nope*.json").exit_code == 2


def test_bad_config_exit_2(wrapped, tmp_path):
    cfg = tmp_path / "bad.toml"
    cfg.write_text("this is = not [valid")
    assert render("--config", cfg, wrapped).exit_code == 2


def test_output_dir_is_file(wrapped, tmp_path):
    f = tmp_path / "afile"
    f.write_text("x")
    res = render("--output-dir", f, wrapped)
    assert res.exit_code == 2 and "not a directory" in res.output
    assert "Traceback" not in res.output


@pytest.mark.parametrize(
    "mutate, expect",
    [
        (lambda d: d.update(deepgram_transcribe="oops"), "invalid deepgram_transcribe metadata"),
        (lambda d: d["deepgram_transcribe"].update(source="oops"), "invalid deepgram_transcribe"),
        (lambda d: d["deepgram_transcribe"].update(options=[1]), "invalid deepgram_transcribe"),
        (lambda d: d.update(response="oops"), "invalid response"),
    ],
)
def test_malformed_wrapped_types(wrapped, tmp_path, mutate, expect):
    doc = json.loads(wrapped.read_text())
    mutate(doc)
    bad = wrapped.parent / "bad.json"
    bad.write_text(json.dumps(doc))
    good = wrapped.parent / "good.json"
    shutil.copy(FIXTURES / "wrapped.json", good)
    res = render(bad, good)
    assert res.exit_code == 1
    assert expect in res.output and "bad.json" in res.output
    assert "has no attribute" not in res.output
    assert (wrapped.parent / "good.md").exists()

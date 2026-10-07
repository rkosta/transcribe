import json
from datetime import datetime
from pathlib import Path

import pytest

from deepgram_transcribe.renderer import format_timestamp, render_markdown, resolve_date

FIX = Path(__file__).parent / "fixtures"
HEAD = '---\nsource: a.m4a\ndate: 2026-10-05\nduration: "00:01:15"\nmodel: nova-3\n'
DIARIZED_BODY = (
    "## Transcript\n\n"
    "**Speaker 0** [00:00:04]\nHello there.\n\nWelcome all.\n\n"
    "**Speaker 1** [00:00:31]\nThanks for having me.\n\n"
    "**Speaker 0** [00:00:40]\nSure.\n"
)


def load(name):
    return json.loads((FIX / f"{name}.json").read_text())


def render(name):
    return render_markdown(load(name), "2026-10-05", "a.m4a")


def test_diarized_paragraphs_merge_same_speaker():
    assert render("diarized_paragraphs") == HEAD + "speakers: 2\n---\n\n" + DIARIZED_BODY


def test_no_diarization():
    assert render("no_diarization") == (
        HEAD + "---\n\n## Transcript\n\n"
        "[00:00:04]\nHello there. Welcome all.\n\n"
        "[00:00:31]\nThanks for having me. Sure.\n"
    )


def test_words_only_groups_by_speaker():
    assert render("words_only") == (
        HEAD + "speakers: 2\n---\n\n## Transcript\n\n"
        "**Speaker 0** [00:00:04]\nHello there. Welcome all.\n\n"
        "**Speaker 1** [00:00:31]\nThanks for having me.\n\n"
        "**Speaker 0** [00:00:40]\nSure.\n"
    )


def test_summary_and_topics():
    assert render("summary_topics") == (
        HEAD + "speakers: 2\n---\n\n"
        "## Summary\n\nA short greeting between two speakers.\n\n"
        "## Topics\n\n- Greetings\n- Gratitude\n\n" + DIARIZED_BODY
    )


def test_detected_language():
    assert render("detected_language") == (
        HEAD + "language: pt\nspeakers: 2\n---\n\n" + DIARIZED_BODY
    )


def test_empty():
    assert render("empty") == (
        '---\nsource: a.m4a\ndate: 2026-10-05\nduration: "00:00:03"\nmodel: nova-3\n---\n\n'
        "## Transcript\n\n_No speech detected._\n"
    )


def test_wrapped_uses_embedded_source_and_quotes_yaml():
    out = render_markdown(load("wrapped"), "2026-10-05", "ignored.m4a")
    assert out.startswith(
        '---\nsource: "meeting: q3 \\"sync\\".m4a"\ndate: 2026-10-05\n'
        'duration: "00:01:15"\nmodel: nova-3\nlanguage: multi\nspeakers: 2\n---\n'
    )
    assert out.endswith(DIARIZED_BODY)


@pytest.mark.parametrize("name", sorted(p.stem for p in FIX.glob("*.json")))
def test_fixtures_match_sdk_schema(name):
    from deepgram.types.listen_v1response import ListenV1Response

    doc = load(name)
    ListenV1Response.model_validate(doc.get("response", doc))


@pytest.mark.parametrize(
    "value",
    ["new\nline", "cr\rlf", "tab\there", "bell\x07", "back\\slash", 'q"uote', "a: b"],
)
def test_yaml_source_roundtrip(value):
    import yaml

    out = render_markdown(load("empty"), "2026-10-05", value)
    front = out.split("---\n")[1]
    assert yaml.safe_load(front)["source"] == value


def test_bare_response_without_source_omits_source():
    out = render_markdown(load("empty"), "2026-10-05")
    assert "source:" not in out


def test_renderer_does_not_mutate_input():
    doc = load("summary_topics")
    before = json.dumps(doc)
    render_markdown(doc, "2026-10-05", "a.m4a")
    assert json.dumps(doc) == before


def test_format_timestamp():
    assert format_timestamp(0) == "00:00:00"
    assert format_timestamp(3661.9) == "01:01:01"
    assert format_timestamp(None) == "00:00:00"


def test_date_mtime():
    assert resolve_date("mtime", mtime="2026-10-05T09:30:00+00:00") == "2026-10-05"
    assert resolve_date("mtime", mtime="2026-10-05T23:30:00Z") == "2026-10-05"


def test_date_mtime_missing_or_bad():
    with pytest.raises(ValueError):
        resolve_date("mtime")
    with pytest.raises(ValueError):
        resolve_date("mtime", mtime="garbage")


def test_date_now():
    assert resolve_date("now", now=datetime(2026, 1, 2, 3, 4)) == "2026-01-02"
    assert len(resolve_date("now")) == 10


def test_date_explicit():
    assert resolve_date("2026-02-28") == "2026-02-28"


@pytest.mark.parametrize("bad", ["2026-02-30", "2026-1-1", "yesterday", "", "20261007"])
def test_date_invalid(bad):
    with pytest.raises(ValueError):
        resolve_date(bad)

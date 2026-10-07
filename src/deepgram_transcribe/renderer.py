"""Pure Markdown renderer for Deepgram transcripts. No I/O."""

from __future__ import annotations

import re
from datetime import date as _date
from datetime import datetime
from typing import Any

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PLAIN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_./+-]*")
_RESERVED = {"true", "false", "null", "yes", "no", "on", "off", "y", "n"}

Block = tuple[int | None, float, list[str]]


def resolve_date(value: str, mtime: str | None = None, now: datetime | None = None) -> str:
    """Resolve a ``--date`` value to ``YYYY-MM-DD``.

    ``mtime`` is the source mtime as an ISO-8601 string; ``now`` is injectable for tests.
    Raises ValueError for anything invalid.
    """
    if value == "mtime":
        if not mtime:
            raise ValueError("--date mtime: no source mtime available")
        try:
            return datetime.fromisoformat(mtime.replace("Z", "+00:00")).date().isoformat()
        except ValueError as exc:
            raise ValueError(f"invalid mtime value: {mtime!r}") from exc
    if value == "now":
        return (now or datetime.now()).date().isoformat()
    if _DATE_RE.match(value):
        try:
            return _date.fromisoformat(value).isoformat()
        except ValueError:
            pass
    raise ValueError(f"invalid --date {value!r}: use mtime, now or YYYY-MM-DD")


def format_timestamp(seconds: float | None) -> str:
    total = int(seconds or 0)
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def _yaml_str(value: str) -> str:
    """Quote a string for YAML unless it is a safe plain scalar."""
    if _PLAIN_RE.fullmatch(value) and value.lower() not in _RESERVED:
        return value
    escapes = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}
    out = []
    for ch in value:
        if ch in escapes:
            out.append(escapes[ch])
        elif ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F:
            out.append(f"\\x{ord(ch):02x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def normalise(doc: dict, source_name: str | None = None) -> tuple[dict, dict]:
    """Return ``(meta, response)`` from a wrapped doc or a bare Deepgram response."""
    if isinstance(doc.get("response"), dict):
        return doc.get("deepgram_transcribe") or {}, doc["response"]
    return ({"source": {"name": source_name}} if source_name else {}), doc


def _alternative(response: dict) -> tuple[dict, dict]:
    channels = (response.get("results") or {}).get("channels") or []
    channel = channels[0] if channels else {}
    alts = channel.get("alternatives") or []
    return channel, (alts[0] if alts else {})


def _model(meta: dict, response: dict) -> str | None:
    model = (meta.get("options") or {}).get("model")
    if model:
        return str(model)
    md = response.get("metadata") or {}
    models = md.get("models") or []
    if models:
        info = (md.get("model_info") or {}).get(models[0]) or {}
        return info.get("name") or str(models[0])
    return None


def _paragraph_blocks(paragraphs: list[dict]) -> list[Block]:
    blocks: list[Block] = []
    for p in paragraphs:
        sentences = p.get("sentences") or []
        text = " ".join(s.get("text", "").strip() for s in sentences).strip()
        if not text:
            continue
        spk = p.get("speaker")
        start = p.get("start", sentences[0].get("start", 0))
        if blocks and spk is not None and blocks[-1][0] == spk:
            blocks[-1][2].append(text)
        else:
            blocks.append((spk, start, [text]))
    return blocks


def _word_blocks(words: list[dict]) -> list[Block]:
    groups: list[tuple[int | None, float, list[str]]] = []
    for w in words:
        token = w.get("punctuated_word") or w.get("word") or ""
        spk = w.get("speaker")
        if not groups or groups[-1][0] != spk:
            groups.append((spk, w.get("start", 0), []))
        groups[-1][2].append(token)
    return [(s, t, [" ".join(tokens)]) for s, t, tokens in groups]


def _summary(response: dict) -> str | None:
    summary = (response.get("results") or {}).get("summary") or {}
    text = summary.get("short") or summary.get("result")
    return text.strip() if isinstance(text, str) and text.strip() not in ("", "success") else None


def _topics(response: dict) -> list[str]:
    segments = (((response.get("results") or {}).get("topics") or {}).get("results") or {}).get(
        "segments"
    ) or []
    seen: list[str] = []
    for seg in segments:
        for t in seg.get("topics") or []:
            name = t.get("topic")
            if name and name not in seen:
                seen.append(name)
    return seen


def render_markdown(doc: dict, date: str, source_name: str | None = None) -> str:
    """Render a wrapped JSON doc (or bare Deepgram response) as Markdown.

    ``date`` is the already-resolved frontmatter date (see ``resolve_date``).
    ``source_name`` is the fallback source name for bare responses.
    """
    meta, response = normalise(doc, source_name)
    channel, alt = _alternative(response)
    md = response.get("metadata") or {}
    options = meta.get("options") or {}
    words = alt.get("words") or []

    paragraphs = (alt.get("paragraphs") or {}).get("paragraphs")
    if paragraphs:
        blocks = _paragraph_blocks(paragraphs)
    elif words:
        blocks = _word_blocks(words)
    elif (alt.get("transcript") or "").strip():
        blocks = [(None, 0, [alt["transcript"].strip()])]
    else:
        blocks = []

    speakers = {b[0] for b in blocks if b[0] is not None}
    speakers |= {w["speaker"] for w in words if w.get("speaker") is not None}

    lines = ["---"]
    src = (meta.get("source") or {}).get("name")
    if src:
        lines.append(f"source: {_yaml_str(str(src))}")
    lines.append(f"date: {date}")
    if md.get("duration") is not None:
        lines.append(f'duration: "{format_timestamp(md["duration"])}"')
    model = _model(meta, response)
    if model:
        lines.append(f"model: {_yaml_str(model)}")
    language = channel.get("detected_language") or options.get("language")
    if language:
        lines.append(f"language: {_yaml_str(str(language))}")
    if speakers:
        lines.append(f"speakers: {len(speakers)}")
    lines += ["---", ""]

    summary = _summary(response)
    if summary:
        lines += ["## Summary", "", summary, ""]
    topics = _topics(response)
    if topics:
        lines += ["## Topics", "", *[f"- {t}" for t in topics], ""]

    lines += ["## Transcript", ""]
    if not blocks:
        lines.append("_No speech detected._")
    else:
        rendered = []
        for spk, start, paras in blocks:
            stamp = f"[{format_timestamp(start)}]"
            head = f"**Speaker {spk}** {stamp}" if spk is not None else stamp
            rendered.append(head + "\n" + "\n\n".join(paras))
        lines.append("\n\n".join(rendered))
    return "\n".join(lines) + "\n"


__all__: list[Any] = ["format_timestamp", "normalise", "render_markdown", "resolve_date"]

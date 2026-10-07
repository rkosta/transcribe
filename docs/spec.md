# deepgram-transcribe — spec

CLI that sends audio/video recordings to Deepgram's pre-recorded speech-to-text API and writes a Markdown transcript plus the raw JSON response.

## Names
- PyPI package: `deepgram-transcribe`
- Console scripts: `deepgram-transcribe` and `dgt` (same entry point)
- Import package: `deepgram_transcribe` (`src/` layout)
- License: MIT. Author: `Ricardo Costa`, **no email** anywhere in package metadata.

## Commands
```
dgt run    [OPTIONS] FILES_OR_GLOBS...   # transcribe via Deepgram
dgt render [OPTIONS] JSON_FILES...       # re-render Markdown from saved JSON, no API call
dgt        [OPTIONS] FILES_OR_GLOBS...   # shortcut for `run`
```
Globs are expanded by the tool too (quoted globs work, `**` supported). Duplicates removed; order preserved.

### Shared options (run + render)
| Option | Meaning |
|---|---|
| `--output-dir DIR` | Where outputs go. Default: next to the source file. Created if missing. |
| `--force` | Overwrite existing outputs. Without it, a file whose outputs already exist is skipped (reported). |
| `--date mtime\|now\|YYYY-MM-DD` | Value of frontmatter `date`. Default `mtime` (source file modification date; for `render`, the mtime stored in the JSON). Invalid value → usage error. |
| `--config PATH` | Config file override. |
| `-q/--quiet`, `-v/--verbose` | Output verbosity. |

### `run` options
API key precedence: `--api-key` > `DEEPGRAM_API_KEY` > `api_key` in config. Missing key → clear error, exit 2.

Typed flags (each maps 1:1 to the Deepgram query param of the same name):
- `--model` (default `nova-3`), `--language` (default `multi`), `--detect-language`
- `--diarize/--no-diarize` (default on), `--smart-format/--no-smart-format` (default on), `--paragraphs/--no-paragraphs` (default on), `--punctuate`, `--utterances`, `--numerals`, `--filler-words`, `--profanity-filter`
- `--keyterm TEXT` (repeatable), `--redact VALUE` (repeatable)
- `--summarize` (sends `summarize=v2`), `--topics`, `--intents`, `--sentiment`, `--detect-entities`
- `--param KEY=VALUE` (repeatable): any other Deepgram query param, passed unchanged. Repeating a key sends it multiple times. Passthrough wins over typed flags/config for the same key.

Option precedence per key: CLI flag > config `[deepgram]` > built-in default.

**English-only rule:** `summarize`, `topics`, `intents`, `sentiment` are only sent when the effective `language` starts with `en` and `detect_language` is off. Otherwise they are dropped from the request with one warning per run naming the dropped features. (Default `multi` therefore skips them — accepted.)

Input files: any type; no extension filtering. The file is sent as-is; Deepgram decides. Deepgram/network errors are reported per file and the run continues. Use a generous HTTP timeout (meetings can be hours long; default 600 s, configurable via `timeout` in config/`--timeout`).

Only channel 0 / alternative 0 is rendered (multichannel out of scope).

## Config file
Path: `--config` > `$XDG_CONFIG_HOME/deepgram-transcribe/config.toml` > `~/.config/deepgram-transcribe/config.toml` (same on macOS). Missing file is fine.
```toml
api_key = "..."          # optional
output_dir = "~/Transcripts"   # optional
date = "mtime"           # optional
timeout = 600            # optional

[deepgram]               # any Deepgram query params, used as defaults
model = "nova-3"
language = "multi"
keyterm = ["Reaktor", "Hermes"]
```
Unknown top-level keys → warning. Lists → repeated query params.

## Outputs
For source `meeting.m4a`: `meeting.json` and `meeting.md` in the output dir. Skip check: if **both** exist and no `--force` → skip. Write JSON first (it's what the API cost), then Markdown.

### JSON file
```json
{
  "deepgram_transcribe": {
    "version": "<tool version>",
    "created": "<ISO-8601 UTC>",
    "source": {"name": "meeting.m4a", "path": "<absolute path>", "mtime": "<ISO-8601>"},
    "options": { "...effective query params sent..." }
  },
  "response": { "...Deepgram response verbatim..." }
}
```
**Never store the API key.** `render` must accept this format; it should also accept a bare Deepgram response (then `source`/`options` come from the response metadata where possible, and the source name from the JSON file stem).

### Markdown
```markdown
---
source: meeting.m4a
date: 2026-10-07
duration: "00:47:12"
model: nova-3
language: multi            # detected language if available, else requested
speakers: 3                # omitted when not diarized
---

## Summary                 # only when a summary is in the response

<summary text>

## Topics                  # only when topics are in the response

- topic one
- topic two

## Transcript

**Speaker 0** [00:00:04]
Paragraph text…

**Speaker 1** [00:00:31]
…
```
Rules:
- Timestamps `HH:MM:SS`, from the start of the block.
- Blocks: use `paragraphs` when present; consecutive paragraphs by the same speaker merge under one heading (blank line between paragraphs). Without paragraphs, group consecutive `words` by speaker. Without diarization, no speaker labels, just timestamped paragraphs.
- Empty transcript → Markdown with frontmatter and `_No speech detected._`.
- Frontmatter values YAML-safe (quote strings that need it).
- Renderer is a pure function: `render_markdown(doc, date, source_name=None) -> str` in `renderer.py`; `doc` is wrapped JSON or a bare response (`source_name` is the fallback for bare ones). `date` is already resolved by `resolve_date(value, mtime=None, now=None)` (`mtime`/`now`/`YYYY-MM-DD`, else `ValueError`). No I/O.
- Speakers count = distinct speaker ids. Topics are de-duplicated, in order of first appearance.

## Exit codes
`0` all files transcribed/rendered or skipped · `1` at least one file failed · `2` usage/config error (bad flags, no API key, no inputs matched).

## Testing
- `uv run pytest` must make **no network calls**. Deepgram responses come from fixtures in `tests/fixtures/` (hand-built to match the documented response schema: with/without diarization, paragraphs, summary, topics, detected language, empty).
- Deepgram client is mocked in `run` tests; assert the exact query params sent (defaults, precedence, passthrough, English-only rule).
- One live smoke test marked `@pytest.mark.live`, skipped unless `DEEPGRAM_API_KEY` is set; excluded by default (`-m "not live"` in pytest config).
- `uv run ruff check` and `uv run ruff format --check` clean.

## Packaging / release
- `hatchling` + `hatch-vcs` (version from git tag `vX.Y.Z`), `requires-python = ">=3.11"` (uses `tomllib`).
- Deps: `deepgram-sdk` (pinned to current major), `typer`. Dev group: `pytest`, `ruff`.
- PyPI-ready README (install via `uvx deepgram-transcribe` / `uv tool install deepgram-transcribe`, usage, config, examples).
- CI + trusted-publishing release: see `docs/release.md`.

## Out of scope (for now)
Watch-folder mode, Hermes skill, web UI, SRT/VTT/plain text, speaker renaming, URL inputs, streaming/live audio, multichannel.

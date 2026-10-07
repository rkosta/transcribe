# deepgram-transcribe

Transcribe audio and video recordings (meetings, calls, interviews) with
[Deepgram](https://deepgram.com) and get a Markdown transcript plus the raw JSON response.

For `meeting.m4a` you get `meeting.json` (the full Deepgram response, never your API key) and
`meeting.md` (frontmatter, optional summary and topics, speaker-labelled timestamped transcript).

## Install

```
uvx deepgram-transcribe --help          # run without installing
uv tool install deepgram-transcribe     # installs the `dgt` command
```

Requires Python 3.11+. Both `dgt` and `deepgram-transcribe` are installed.

## API key

Get a key from the Deepgram console, then provide it in one of these ways (highest precedence first):

1. `--api-key` on the command line
2. the `DEEPGRAM_API_KEY` environment variable
3. `api_key` in the config file

```
export DEEPGRAM_API_KEY=your-key
```

## Usage

Transcribe recordings (globs are expanded by the tool; quote them so `**` works):

```
dgt run meeting.m4a
dgt run --output-dir ~/Transcripts "recordings/**/*.mp3"
dgt meeting.m4a                      # shortcut for `run`
dgt run --summarize --topics --language en call.wav
dgt run --keyterm Reaktor --param tier=enhanced meeting.m4a
```

Re-render Markdown from saved JSON, without calling the API:

```
dgt render meeting.json
dgt render --force --date 2026-10-07 *.json
```

Common options: `--output-dir DIR`, `--force` (overwrite; otherwise files with existing outputs are
skipped), `--date mtime|now|YYYY-MM-DD`, `--config PATH`, `-q/--quiet`, `-v/--verbose`.
Run `dgt run --help` for the full list of Deepgram flags (`--model`, `--language`, `--diarize`,
`--smart-format`, `--paragraphs`, `--keyterm`, `--redact`, `--param KEY=VALUE`, ...).

Exit codes: `0` success or skipped, `1` at least one file failed, `2` usage or config error.

## Config file

Location: `$XDG_CONFIG_HOME/deepgram-transcribe/config.toml`, falling back to
`~/.config/deepgram-transcribe/config.toml`. A missing file is fine.

```toml
api_key = "..."                # optional
output_dir = "~/Transcripts"   # optional
date = "mtime"                 # optional
timeout = 600                  # optional, seconds

[deepgram]                     # defaults for any Deepgram query param
model = "nova-3"
language = "multi"
keyterm = ["Reaktor", "Hermes"]
```

Precedence per option: CLI flag > config `[deepgram]` > built-in default.

## English-only features

`--summarize`, `--topics`, `--intents` and `--sentiment` only work for English. They are sent only
when the effective language starts with `en` and language detection is off. With the default
`language = "multi"` they are dropped with a warning, so pass `--language en` to use them.

## More

Full behaviour is described in the
[spec](https://github.com/rkosta/transcribe/blob/main/docs/spec.md). Licensed under MIT.

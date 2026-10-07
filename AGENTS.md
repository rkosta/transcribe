# AGENTS.md

`deepgram-transcribe` (`dgt`): Python CLI that sends recordings to Deepgram and writes Markdown + raw JSON transcripts. Published to PyPI.

- Spec (source of truth): `docs/spec.md`
- CI / release: `docs/release.md`

## Commands
```
uv sync
uv run pytest            # no network; live tests excluded
uv run pytest -m live    # needs DEEPGRAM_API_KEY, costs money — only when asked
uv run ruff check && uv run ruff format --check
uv run dgt --help
```

## Layout
`src/deepgram_transcribe/` (cli, config, deepgram client wrapper, renderer) · `tests/` with fixtures in `tests/fixtures/`.

## Rules
- Python ≥3.11, uv, `typer`, official `deepgram-sdk`. Don't add dependencies without a reason in the PR/card.
- Renderer stays pure (no I/O); all Deepgram calls go through one wrapper so tests can mock it.
- Never log, print, or persist the API key (including in saved JSON).
- No email address anywhere in package metadata; author is `Ricardo Costa`.
- Tests never hit the network unless marked `live`.
- Branch per card (`feat/...`); no pushes, merges or tags — Ricardo does those after review.
- Keep docs in sync: behaviour changes update `docs/spec.md` in the same change.

## Comments and docstrings
Enforced by ruff `D` rules (`convention = "google"`, off for `tests/`).
- Google-style docstrings on every module, public class and public function. No types in docstrings (type hints cover them). `Args`/`Returns`/`Raises` only when they say more than the name and signature.
- Private helpers (`_name`) get a one-line docstring when their purpose isn't obvious from the name.
- Inline `#` comments explain why, not what: Deepgram/SDK quirks, workarounds, edge cases. No line-by-line narration.
- Tests need no docstrings; the test name describes it. One-liner only for non-obvious tests.
- No TODO/FIXME comments. Unfinished work goes in the card handoff so it becomes a card.

# Release

## CI (`.github/workflows/ci.yml`)
On push and pull request: `uv sync`, `uv run ruff check`, `uv run ruff format --check`, `uv run pytest` (live tests excluded) on Python 3.11, 3.12, 3.13. Also `uv build` to make sure the package builds.

## Publish (`.github/workflows/release.yml`)
Trigger: push of a tag matching `v*`.
1. Checkout with `fetch-depth: 0` (hatch-vcs needs tags).
2. Run the same checks as CI.
3. `uv build` → `dist/`.
4. Publish with `pypa/gh-action-pypi-publish` using **trusted publishing**: job has `environment: pypi` and `permissions: id-token: write`. No API tokens stored anywhere.

## One-time setup (Ricardo, manual)
1. On PyPI → Account → Publishing → add a *pending* trusted publisher: project `deepgram-transcribe`, owner/repo = the GitHub repo, workflow `release.yml`, environment `pypi`.
2. On GitHub → repo Settings → Environments → create `pypi` (optionally require approval).

## Cutting a release
```
git tag vX.Y.Z
git push origin vX.Y.Z
```
Check the Actions run, then `uvx deepgram-transcribe --help` to verify.

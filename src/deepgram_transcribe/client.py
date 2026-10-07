"""The only module that talks to Deepgram. Mock `transcribe_file` in tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT = 600.0

Params = dict[str, Any]


class TranscriptionError(Exception):
    """A Deepgram/network failure for one file. Never contains the API key."""


def transcribe_file(
    api_key: str, path: Path, params: Params, timeout: float = DEFAULT_TIMEOUT
) -> dict[str, Any]:
    """Send one file to Deepgram's pre-recorded endpoint and return the response as a dict.

    ``params`` are sent verbatim as query parameters (bools as true/false, lists repeated).
    """
    from deepgram import DeepgramClient  # imported lazily: keeps `--help` fast

    try:
        audio = path.read_bytes()
        client = DeepgramClient(api_key=api_key, timeout=timeout)
        response = client.listen.v1.media.transcribe_file(
            request=audio,
            request_options={
                "timeout": timeout,
                "additional_query_parameters": params,
                "max_retries": 2,
            },
        )
        if not hasattr(response, "model_dump"):
            raise TranscriptionError("unexpected response from Deepgram")
        data = response.model_dump(mode="json", by_alias=True, exclude_none=True)
    except TranscriptionError:
        raise
    except Exception as exc:  # SDK/httpx/OS errors: report per file, never leak the key
        raise TranscriptionError(_describe(exc, api_key)) from exc
    if "results" not in data:
        raise TranscriptionError("Deepgram returned no transcription results")
    return data


def _describe(exc: Exception, api_key: str) -> str:
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    msg = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
    if status is not None:
        msg = f"HTTP {status}: {body}" if body else f"HTTP {status}"
    return msg.replace(api_key, "***") if api_key else msg

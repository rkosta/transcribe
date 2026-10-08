"""deepgram-transcribe: transcribe recordings with Deepgram."""

try:
    from ._version import __version__
except ImportError:  # running from an unbuilt checkout
    __version__ = "0.0.0"

__all__ = ["__version__"]

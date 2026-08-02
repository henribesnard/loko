"""LOKO — deterministic chatbot platform for customer service."""

try:
    from importlib.metadata import version as _v

    __version__ = _v("loko")
except Exception:
    __version__ = "1.3.4"

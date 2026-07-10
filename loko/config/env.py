"""N1 — Unified environment variable reader with RAGKIT_ backward compatibility.

All LOKO configuration reads should go through `get_env()`.
Legacy `RAGKIT_*` variables are still accepted with a deprecation warning.
Support will be removed in 0.5.0.
"""

from __future__ import annotations

import os
import warnings


def get_env(name: str, default: str | None = None) -> str | None:
    """Read LOKO_<name>, falling back to deprecated RAGKIT_<name>.

    Parameters
    ----------
    name : str
        The variable suffix (e.g. "MODE", "ENV", "CORS_ORIGINS").
    default : str | None
        Value returned when neither LOKO_ nor RAGKIT_ variant is set.

    Returns
    -------
    str | None
        The environment value, or *default*.
    """
    val = os.environ.get(f"LOKO_{name}")
    if val is not None:
        return val
    legacy = os.environ.get(f"RAGKIT_{name}")
    if legacy is not None:
        warnings.warn(
            f"RAGKIT_{name} is deprecated, use LOKO_{name}. "
            "Support will be removed in 0.5.0.",
            DeprecationWarning,
            stacklevel=2,
        )
        return legacy
    return default

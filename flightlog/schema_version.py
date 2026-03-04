"""Schema version constants and compatibility helpers."""

from __future__ import annotations

SCHEMA_VERSION = "1.0.0"
SUPPORTED_SCHEMA_VERSIONS = {SCHEMA_VERSION}

_CURRENT_MAJOR = int(SCHEMA_VERSION.split(".")[0])


def is_compatible(version: str) -> bool:
    """Return True if *version* is forward-compatible (same MAJOR, any MINOR/PATCH)."""
    try:
        parts = version.split(".")
        if len(parts) != 3:
            return False
        major = int(parts[0])
        return major == _CURRENT_MAJOR
    except (ValueError, AttributeError):
        return False


def is_same_major(version: str) -> bool:
    """Return True if *version* shares the current MAJOR version."""
    try:
        return int(version.split(".")[0]) == _CURRENT_MAJOR
    except (ValueError, AttributeError, IndexError):
        return False

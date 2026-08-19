"""Type-safe platform enums.

``PlatformType``/``ArchType`` are ``str``-based so legacy string comparisons
(``platform == "windows"``) remain valid while new code can use the enum members
type-safely. Business logic should prefer the enum members; raw platform strings
are deprecated.
"""

from __future__ import annotations

from enum import Enum


class PlatformType(str, Enum):
    """Canonical OS identifiers (single source of truth, no raw strings)."""

    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"


class ArchType(str, Enum):
    """Canonical CPU architecture identifiers."""

    X86_64 = "x86_64"
    ARM64 = "arm64"
    X86 = "x86"
    UNKNOWN = "unknown"


__all__ = ["PlatformType", "ArchType"]

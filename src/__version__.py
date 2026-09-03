"""Single source of truth for XenRay application versioning."""

from __future__ import annotations

import os

__version__ = os.getenv("APP_VERSION", "0.3.3")
APP_VERSION = __version__

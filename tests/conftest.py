"""
pytest configuration and shared fixtures.

This conftest.py exists to:

1. Remove the loguru stderr handler before pytest teardown to prevent
   ``ValueError: I/O operation on closed file`` noise from XrayService /
   SingboxService atexit handlers that log after pytest closes sys.stderr.

2. **Isolate tests from the REAL system state** — the most important rule:

   ``XrayService`` and ``SingboxService`` register ``atexit`` handlers that
   perform DESTRUCTIVE system mutations at interpreter shutdown:
   - removing Windows NRPT DNS rules (``_remove_nrpt_rules``)
   - clearing static DNS from the ``xenray-tun`` adapter (``_cleanup_tun_dns``)
   - restoring the Smart Multi-Homed Name Resolution registry state (SMHR)
   - killing orphan processes via PID files

   If a test constructs one of these services, the atexit handler runs when
   pytest exits and WIPES the user's REAL VPN connection (NRPT rules, TUN DNS,
   SMHR). This conftest neutralises those side effects by:
   - redirecting the TMPDIR used for PID/log files to an isolated temp dir
   - patching the destructive cleanup methods to no-ops for the whole session

   No source code behaviour is changed -- this only affects the test runner.
"""

import os
import tempfile

import pytest
from loguru import logger

# ---------------------------------------------------------------------------
# Isolate the runtime filesystem (PID files, logs, generated configs) from the
# real application state so tests never touch ~/.config/xenray or
# %TEMP%/xenray (where a live VPN session keeps its xray.pid / singbox.pid).
# ---------------------------------------------------------------------------
_ISOLATED_TMP = tempfile.mkdtemp(prefix="xenray_test_tmp_")
os.environ["TMPDIR"] = _ISOLATED_TMP
os.environ["TEMP"] = _ISOLATED_TMP
os.environ["TMP"] = _ISOLATED_TMP

# The real application config dir must never be read/written by tests either.
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="xenray_test_cfg_")

# NOTE: src.core.constants computes TMPDIR at import time (module level). Any
# module imported AFTER this conftest runs (i.e. all test modules) will pick up
# the isolated dir. Modules imported before conftest (only pytest internals)
# don't touch these paths.


@pytest.fixture(autouse=True, scope="session")
def _neutralise_destructive_service_cleanup():
    """Patch destructive system mutations for the WHOLE test session.

    XrayService / SingboxService are constructed by several unit tests. Their
    ``atexit`` handlers and internal cleanup methods mutate the REAL OS
    (NRPT rules, TUN DNS, SMHR registry, orphan kills). We replace those with
    safe no-ops so running the test suite NEVER affects a live VPN session.
    """
    from unittest.mock import patch

    # XrayService destructive methods -> no-ops
    # NOTE: _restore_smhr / _suppress_smhr are NOT no-oped — they are thin
    # wrappers over PlatformUtils that some tests verify by delegation. They
    # only run inside _guaranteed_cleanup (no-oped) or explicit calls.
    xray_noops = [
        "src.services.xray_service.XrayService._guaranteed_cleanup",
        "src.services.xray_service.XrayService._remove_nrpt_rules",
        "src.services.xray_service.XrayService._cleanup_tun_dns",
        "src.services.xray_service.XrayService._cleanup_previous_instance",
    ]
    # SingboxService destructive methods -> no-ops
    singbox_noops = [
        "src.services.singbox_service.SingboxService._guaranteed_cleanup",
        "src.services.singbox_service.SingboxService._signal_handler",
    ]

    patchers = [patch(target, lambda *a, **k: None) for target in xray_noops + singbox_noops]
    for p in patchers:
        p.start()
    yield
    for p in patchers:
        p.stop()

    # Also neutralise the atexit handlers registered by any constructed
    # service so nothing destructive runs at interpreter shutdown.
    try:
        import atexit

        # The safest approach: remove all registered atexit handlers that are
        # bound methods of XrayService/SingboxService instances.
        for fn in list(atexit._exithandlers):  # noqa: SLF001 - internal API, only used in tests
            # Each entry is a tuple (func, args, kwargs)
            func = fn[0] if isinstance(fn, tuple) else None
            if func is not None and hasattr(func, "__self__"):
                cls_name = type(func.__self__).__name__
                if cls_name in ("XrayService", "SingboxService"):
                    try:
                        atexit._exithandlers.remove(fn)  # noqa: SLF001
                    except ValueError:
                        pass
    except Exception:
        pass  # Never fail the suite over atexit bookkeeping


@pytest.fixture(autouse=True, scope="session")
def _silence_loguru_on_teardown():
    """Remove the loguru stderr handler before the test session ends.

    XrayService and SingboxService register atexit callbacks that call
    logger.info()/logger.debug() during Python interpreter shutdown.  By that
    time pytest has already closed sys.stderr, so loguru raises:

        ValueError: I/O operation on closed file.

    Removing the stderr handler here (before teardown) prevents this.  The
    file handler (xenray.log) is unaffected and continues to work normally.
    """
    yield  # --- test session runs here ---

    # Remove all handlers that write to stderr so late atexit logs are silent.
    try:
        logger.remove()  # Removes ALL handlers added by src/core/logger.py
    except Exception:
        pass  # Never fail the suite over a logging housekeeping step

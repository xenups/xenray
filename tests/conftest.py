"""
pytest configuration and shared fixtures.

This conftest.py exists primarily to:
1. Remove the loguru stderr handler before pytest teardown to prevent
   ``ValueError: I/O operation on closed file`` noise from XrayService /
   SingboxService atexit handlers that log after pytest closes sys.stderr.

No source code behaviour is changed -- this only affects the test runner.
"""

import pytest
from loguru import logger


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

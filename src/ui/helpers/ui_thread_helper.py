"""UI Thread Helper - Provides thread-safe UI updates for Flet applications."""

from typing import Callable

from loguru import logger


class UIThreadHelper:
    """Helper class for thread-safe UI updates in Flet."""

    def __init__(self, page):
        """
        Initialize UIThreadHelper.

        Args:
            page: Flet Page instance
        """
        self._page = page

    def call(self, fn: Callable, *args, update_page: bool = False, **kwargs):
        """
        Execute a UI update in a thread-safe manner.

        Args:
            fn: Function to execute on UI thread
            *args: Positional arguments for the function
            update_page: Whether to call page.update() after execution
            **kwargs: Keyword arguments for the function
        """
        if not self._page:
            return

        async def _coro():
            # Check if loop is still running
            try:
                loop = getattr(self._page, "loop", None)
                if loop and loop.is_closed():
                    fn_name = fn.__name__ if hasattr(fn, "__name__") else "lambda"
                    logger.debug(
                        f"[DEBUG] Skipping UI call ({fn_name}): Event loop is closed"
                    )
                    return
            except Exception:
                pass

            try:
                fn(*args, **kwargs)
                if update_page:
                    try:
                        self._page.update()
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(
                    f"[DEBUG] UI call error in {fn.__name__ if hasattr(fn, '__name__') else 'lambda'}: {e}"
                )

        try:
            self._page.run_task(_coro)
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                logger.debug(
                    "[DEBUG] RuntimeError caught in ui_call: Event loop is closed"
                )
            else:
                logger.warning(f"[DEBUG] RuntimeError in ui_call: {e}")

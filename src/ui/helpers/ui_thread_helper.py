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
            fn: Function to execute on UI thread (sync or async)
            *args: Positional arguments for the function
            update_page: Whether to call page.update() after execution
            **kwargs: Keyword arguments for the function
        """
        if not self._page:
            return

        import asyncio
        _is_coro = asyncio.iscoroutinefunction(fn)

        async def _coro():
            try:
                if _is_coro:
                    await fn(*args, **kwargs)
                else:
                    fn(*args, **kwargs)
                if update_page:
                    try:
                        self._page.update()
                    except Exception:
                        pass
            except Exception as e:
                fn_name = fn.__name__ if hasattr(fn, "__name__") else "lambda"
                logger.debug(f"[DEBUG] UI call error in {fn_name}: {e}")

        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                self._page.run_task(_coro)
        except RuntimeError as e:
            msg = str(e)
            if "Event loop is closed" in msg or "destroyed session" in msg:
                pass
            else:
                logger.warning(f"[DEBUG] RuntimeError in ui_call: {e}")

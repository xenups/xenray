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

        From a background thread the update is scheduled onto the Flet event loop
        via ``page.run_task`` (``loop.call_soon_threadsafe``). When the caller is
        ALREADY executing on the page's event loop, ``run_coroutine_threadsafe``
        is not allowed — the update runs inline instead, which is the correct
        thread for Flet control mutations (a dropped update here is what made the
        disconnecting red animation silently not appear).

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

        def _run_inline() -> None:
            """Run fn inline (caller is on the page event loop)."""
            try:
                if _is_coro:
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(fn(*args, **kwargs))
                    except RuntimeError:
                        pass
                else:
                    fn(*args, **kwargs)
                if update_page:
                    try:
                        self._page.update()
                    except Exception:
                        pass
            except Exception as e:
                fn_name = fn.__name__ if hasattr(fn, "__name__") else "lambda"
                logger.debug(f"[DEBUG] UI call error (inline) in {fn_name}: {e}")

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
                # We are already on the page's event loop (run_task cannot be
                # scheduled from the running loop) — execute inline instead of
                # silently dropping the UI update.
                _run_inline()

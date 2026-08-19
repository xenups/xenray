import asyncio
import inspect
from typing import Callable, Optional


def schedule_animation_task(page, coro_or_factory: Callable) -> Optional[asyncio.Task]:
    """Schedule an animation coroutine onto the Flet event loop safely without RuntimeError.

    - If already on the Flet event loop -> asyncio.create_task.
    - Any other thread / loop -> page.run_task (thread-safe).
    """
    if page is None:
        return None

    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    page_loop = getattr(getattr(getattr(page, "session", None), "connection", None), "loop", None)

    if inspect.iscoroutinefunction(coro_or_factory):
        coro_fn = coro_or_factory
    else:

        async def _wrapped():
            res = coro_or_factory()
            if inspect.isawaitable(res):
                await res

        coro_fn = _wrapped

    try:
        if running is not None and page_loop is not None and running is page_loop:
            return asyncio.create_task(coro_fn())
        return page.run_task(coro_fn)
    except (RuntimeError, TypeError, ValueError):
        return None

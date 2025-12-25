import inspect
from typing import Any

async def maybe_await(func, *args, **kwargs) -> Any:
    """Call func which may return awaitable or normal result."""
    result = func(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result

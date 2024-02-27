import asyncio
import datetime
from typing import Coroutine, Awaitable, Optional

TimerCallable = Coroutine


class AsyncScheduleAt:
    _callable: TimerCallable
    _loop: asyncio.AbstractEventLoop
    _async_task: asyncio.Task
    _after: datetime.timedelta

    def __init__(self, callable: TimerCallable, loop: asyncio.AbstractEventLoop = None):
        self._callable = callable

        if loop:
            self._loop = loop
        else:
            self._loop = asyncio.get_running_loop()

    def after_seconds(self, seconds: float) -> None:
        self._after = datetime.timedelta(seconds=seconds)

    async def _run_task(self) -> None:
        await asyncio.sleep(self._after.total_seconds())
        await self._callable

    def schedule(self) -> None:
        self._async_task = self._loop.create_task(self._run_task())

    def cancel(self) -> None:
        if not self._async_task.cancelling():
            self._async_task.cancel()

    def has_completed(self) -> bool:
        return self._async_task.done()

    def has_succeeded(self) -> bool:
        if self.has_completed():
            return not self._async_task.exception()
        else:
            return False

    def has_exception(self) -> bool:
        if self.has_completed():
            return bool(self._async_task.exception())
        else:
            return False

    def retrieve_exception(self) -> Optional[BaseException]:
        if self.has_completed():
            return self._async_task.exception()
        else:
            return None

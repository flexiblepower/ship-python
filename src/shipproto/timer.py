import asyncio
import datetime
import time
from asyncio import Task
from typing import Literal, Optional


class AsyncTimer:
    _async_task: Task
    _loop: asyncio.AbstractEventLoop
    _event: asyncio.Event
    _after: Optional[datetime.timedelta]
    _at: Optional[float]

    def __init__(self, loop: asyncio.AbstractEventLoop = None):
        self._async_task = None
        if loop:
            self._loop = loop
        else:
            self._loop = asyncio.get_running_loop()

        self._event = asyncio.Event()
        self._at = None

    async def _run_task(self) -> None:
        wait_for = self._after.total_seconds()

        if wait_for > 0:
            await asyncio.sleep(wait_for)

        self._event.set()

    def start(self, after: datetime.timedelta) -> None:
        if self.has_started():
            raise RuntimeError("Timer was already started!")

        self._after = after
        self._at = time.time() + after.total_seconds()
        self._async_task = self._loop.create_task(self._run_task())

    def cancel(self) -> None:
        if self._async_task and not self._async_task.cancelling():
            self._async_task.cancel()

    def has_started(self) -> bool:
        return self._at is not None

    async def has_completed(self) -> bool:
        is_set = self._event.is_set()

        if is_set:
            await self._async_task

        return is_set

    async def wait_until_completed(self) -> Literal[True]:
        await self._event.wait()
        await self._async_task
        return True

    def time_left(self) -> Optional[float]:
        time_left = None
        if self._at:
            now = time.time()
            time_left = self._at - now

        return time_left

    def postpone(self, duration: datetime.timedelta) -> "AsyncTimer":
        left = self.time_left()
        if left and left > 0:
            total_duration = datetime.timedelta(seconds=duration.total_seconds() + left)
            new_timer = AsyncTimer()
            new_timer.start(total_duration)
            self.cancel()
        else:
            raise RuntimeError("The timer was not yet active.")

        return new_timer

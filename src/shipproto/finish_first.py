import asyncio
from dataclasses import dataclass
from typing import Dict, Any, Coroutine


@dataclass
class FinishFirst:
    coroutines_by_name: Dict[str, Coroutine]
    loop: asyncio.AbstractEventLoop

    def __init__(
        self, coroutines_by_name: Dict[str, Coroutine], loop: asyncio.AbstractEventLoop = None
    ):
        self.coroutines_by_name = coroutines_by_name

        if loop is None:
            self.loop = asyncio.get_event_loop()
        else:
            self.loop = loop

    async def run(self) -> Dict[str, Any]:
        """Run the coroutines and return the results from the coroutines that finish first.

        Normally only a single coroutine will finish first, but in certain edge cases
        it may be possible that multiple coroutines finish at the same time.

        :return: The results associated to the name of the coroutine.
        """

        tasks_by_name = {
            name: self.loop.create_task(coro) for name, coro in self.coroutines_by_name.items()
        }

        done, pending = await asyncio.wait(
            tasks_by_name.values(), return_when=asyncio.FIRST_COMPLETED
        )

        result = {}
        for task_name, task in tasks_by_name.items():
            if task in done:
                result[task_name] = task.result()
            else:
                task.cancel()

        return result

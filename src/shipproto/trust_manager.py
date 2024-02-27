import asyncio
import logging
from asyncio import Future
from functools import partial
from typing import Dict, Literal, Callable, Coroutine, List, Set

TrustListener = Callable[[str, Coroutine[None, None, None]], Coroutine[bool, None, None]]

log = logging.getLogger("ship")


class TrustManager:
    trust_by_ski: Dict[str, asyncio.Event]
    trust_listener: TrustListener
    _trust_tasks: Dict[str, asyncio.Task]

    def __init__(self, trust_listener: TrustListener):
        self.trust_by_ski = {}
        self.trust_listener = trust_listener
        self._trust_tasks = {}

    def _trust_task_done(self, ski: str, future: Future):
        del self._trust_tasks[ski]
        log.debug("Trust has been processed for ski %s, decision: %s", ski, self.is_trusted(ski))

    def _get_trust_event(self, ski: str) -> asyncio.Event:
        trust_event = self.trust_by_ski.get(ski)

        if not trust_event:
            trust_event = asyncio.Event()
            self.trust_by_ski[ski] = trust_event

            if ski not in self._trust_tasks:
                log.debug("Requesting to trust %s", ski)
                trust_task = asyncio.create_task(self.trust_listener(ski, self.trust_remote(ski)))
                self._trust_tasks[ski] = trust_task
                trust_task.add_done_callback(partial(self._trust_task_done, ski))

        return trust_event

    async def trust_remote(self, ski: str) -> None:
        self._get_trust_event(ski).set()

    async def wait_to_trust(self, ski: str) -> Literal[True]:
        return await self._get_trust_event(ski).wait()

    def is_trusted(self, ski: str) -> bool:
        return self._get_trust_event(ski).is_set()

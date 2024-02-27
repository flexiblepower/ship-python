from typing import Protocol, Any, Union, Coroutine

from websockets.frames import CloseCode


class Websocket(Protocol):
    async def recv(self) -> Union[str, bytes]:
        ...

    async def send(self, message: Union[str, bytes]) -> None:
        ...

    async def close(code: int = CloseCode.NORMAL_CLOSURE, reason: str = "") -> None:
        ...

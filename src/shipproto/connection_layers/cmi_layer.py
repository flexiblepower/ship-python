"""Connection Mode Initialisation layer."""

import asyncio
import logging
from enum import IntEnum

from shipproto.connection_layers.abstract_layer import AbortConnectionException
from shipproto.finish_first import FinishFirst
from shipproto.websocket import Websocket

log = logging.getLogger("ship")


class CMIClientStates(IntEnum):
    CMI_INIT_START = 0
    CMI_STATE_CLIENT_SEND = 1
    CMI_STATE_CLIENT_WAIT = 2
    CMI_STATE_CLIENT_EVALUATE = 3


class CMIServerStates(IntEnum):
    CMI_STATE_SERVER_WAIT = 0
    CMI_STATE_SERVER_EVALUATE = 1


class AbstractCMILayer:
    CMI_TIMEOUT_SECONDS = 10

    websocket: Websocket

    def __init__(self, websocket: Websocket):
        self.websocket = websocket

    async def receive_cmi_message(self) -> bytes:
        msg = await self.websocket.recv()

        if isinstance(msg, str):
            msg = msg.encode()

        return msg

    async def send_cmi_message(self):
        await self.websocket.send(b"\x00\x00")

    @staticmethod
    def evaluate_cmi_message(cmi_msg: bytes) -> bool:
        if len(cmi_msg) >= 2 and cmi_msg[0:2] == b"\x00\x00":
            return True
        else:
            raise AbortConnectionException()


class CMILayerClient(AbstractCMILayer):
    current_state: CMIClientStates

    def __init__(self, websocket: Websocket):
        super().__init__(websocket)
        self.current_state = CMIClientStates.CMI_INIT_START

    async def run(self):
        await self.send_cmi_message()

        self.current_state = CMIClientStates.CMI_STATE_CLIENT_WAIT

        results = await FinishFirst(
            {
                "cmi_message": self.receive_cmi_message(),
                "cmi_timeout_timer": asyncio.sleep(self.CMI_TIMEOUT_SECONDS),
            }
        ).run()

        if "cmi_timeout_timer" in results:
            log.debug("CMI timeout timer triggered.")
            raise AbortConnectionException()
        elif "cmi_message" in results:
            self.current_state = CMIClientStates.CMI_STATE_CLIENT_EVALUATE
            cmi_msg: bytes = results["cmi_message"]
            self.evaluate_cmi_message(cmi_msg)
        else:
            log.error("This should not happen. %s", results)
            raise AbortConnectionException()


class CMILayerServer(AbstractCMILayer):
    current_state: CMIServerStates

    def __init__(self, websocket: Websocket):
        super().__init__(websocket)
        self.current_state = CMIServerStates.CMI_STATE_SERVER_WAIT

    async def run(self):
        results = await FinishFirst(
            {
                "cmi_message": self.receive_cmi_message(),
                "cmi_timeout_timer": asyncio.sleep(self.CMI_TIMEOUT_SECONDS),
            }
        ).run()

        if "cmi_timeout_timer" in results:
            log.debug("CMI timeout timer triggered.")
            raise AbortConnectionException()
        elif "cmi_message" in results:
            log.debug("Received CMI message.")
            self.current_state = CMIServerStates.CMI_STATE_SERVER_EVALUATE
            await self.send_cmi_message()
            cmi_msg: bytes = results["cmi_message"]
            self.evaluate_cmi_message(cmi_msg)
        else:
            log.error("This should not happen. %s", results)
            raise AbortConnectionException()

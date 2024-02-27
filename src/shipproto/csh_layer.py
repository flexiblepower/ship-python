"""Connection State "Hello" layer."""
import datetime
import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from enum import IntEnum, Enum
from typing import Dict, Any, Optional

from shipproto.abstract_layer import AbortConnectionException
from shipproto.finish_first import FinishFirst
from shipproto.timer import AsyncTimer
from shipproto.trust_manager import TrustManager
from shipproto.websocket import Websocket

log = logging.getLogger("ship")


class CSHStates(IntEnum):
    SME_HELLO_STATE_READY_INIT = 0
    SME_HELLO_STATE_READY_LISTEN = 1
    SME_HELLO_STATE_READY_TIMEOUT = 2
    SME_HELLO_STATE_PENDING_INIT = 3
    SME_HELLO_STATE_PENDING_LISTEN = 4
    SME_HELLO_STATE_PENDING_TIMEOUT = 5
    SME_HELLO_OK = 6

    def is_pending(self) -> bool:
        return self in [
            CSHStates.SME_HELLO_STATE_PENDING_TIMEOUT,
            CSHStates.SME_HELLO_STATE_PENDING_LISTEN,
            CSHStates.SME_HELLO_STATE_PENDING_INIT,
        ]

    def is_ready(self) -> bool:
        return self in [
            CSHStates.SME_HELLO_STATE_READY_TIMEOUT,
            CSHStates.SME_HELLO_STATE_READY_LISTEN,
            CSHStates.SME_HELLO_STATE_READY_INIT,
            CSHStates.SME_HELLO_OK,
        ]


class CSHPhases(Enum):
    PENDING = "pending"
    READY = "ready"
    ABORTED = "aborted"


@dataclass
class CSHMessage:
    phase: CSHPhases
    waiting: Optional[timedelta]
    prolongation_request: Optional[bool]

    def to_json(self) -> Dict[str, Any]:
        items = [{"phase": self.phase.value}]

        if self.waiting is not None:
            items.append({"waiting": round(self.waiting.total_seconds() * 1000)})

        if self.prolongation_request is not None:
            items.append({"prolongationRequest": self.prolongation_request})

        return {"connectionHello": items}

    @staticmethod
    def from_json(csh_json_msg: Dict[str, Any]) -> "CSHMessage":
        phase = None
        waiting = None
        prolongation_request = None

        try:
            for item in csh_json_msg["connectionHello"]:
                if len(item) != 1:
                    log.error(
                        "Each item in CSH message is expected to have a single key, "
                        "value pair. Found multiple keys %s in message %s",
                        list(item.keys()),
                        csh_json_msg,
                    )
                    raise AbortConnectionException

                item: Dict[str, Any]
                key = next(iter(item))
                value = item[key]
                if key == "phase":
                    phase = CSHPhases(value)
                elif key == "waiting":
                    waiting = datetime.timedelta(milliseconds=int(value))
                elif key == "prolongationRequest":
                    prolongation_request = value
                else:
                    log.error("Unexpected field %s in CSH message %s", key, csh_json_msg)
                    raise AbortConnectionException
        except (KeyError, ValueError, IndexError):
            log.error("Could not parse CSH message after parsing to JSON: %s", csh_json_msg)
            raise AbortConnectionException

        if phase is None:
            log.error("Missing required field phase in CSH message %s", csh_json_msg)
            raise AbortConnectionException

        return CSHMessage(phase, waiting, prolongation_request)


class CSHLayer:
    CSH_TIMEOUT_T_HELLO_INIT = timedelta(seconds=120)
    CSH_TIMEOUT_T_HELLO_INC = CSH_TIMEOUT_T_HELLO_INIT
    CSH_TIMEOUT_T_HELLO_PROLONG_THR_INC = timedelta(seconds=30)
    CSH_TIMEOUT_T_HELLO_PROLONG_WAITTING_GAP = timedelta(seconds=15)
    CSH_TIMEOUT_T_HELLO_PROLONG_MIN = timedelta(seconds=1)

    _websocket: Websocket
    _trust_manager: TrustManager
    _remote_ski: str
    _current_state: CSHStates

    _wait_for_ready_timer: AsyncTimer
    _send_prolongation_timer: AsyncTimer
    _prolongation_request_reply_timer: AsyncTimer

    _previously_received_message: Optional[CSHMessage]
    _other_side_is_ready: bool

    def __init__(self, websocket: Websocket, trust_manager: TrustManager, remote_ski: str):
        self._websocket = websocket
        self._trust_manager = trust_manager
        self._remote_ski = remote_ski

        if self._trust_manager.is_trusted(self._remote_ski):
            self._current_state = CSHStates.SME_HELLO_STATE_READY_INIT
        else:
            self._current_state = CSHStates.SME_HELLO_STATE_PENDING_INIT

        self._wait_for_ready_timer = AsyncTimer()
        self._send_prolongation_timer = AsyncTimer()
        self._prolongation_request_reply_timer = AsyncTimer()

        self._previously_received_message = None
        self._other_side_trusts_us = False

    async def receive_csh_message(self) -> CSHMessage:
        msg = await self._websocket.recv()

        if len(msg) == 0:
            log.error("Received an empty CSH message.")
            raise AbortConnectionException()

        msg_type = msg[0]

        if isinstance(msg_type, str):
            msg_type = msg_type.encode()

        if msg_type != 1 and msg_type != b"\x01":
            log.error("CSH message expected with message type 1, received %s", msg_type)
            raise AbortConnectionException()

        try:
            msg_value = json.loads(msg[1:])
        except json.JSONDecodeError:
            log.error("Could not parse CSH message value as json. Received %s", msg[1:])
            raise AbortConnectionException()

        message = CSHMessage.from_json(msg_value)
        log.debug("Received CSH message %s", message)
        return message

    async def send_csh_message(self, message: CSHMessage) -> None:
        log.debug("Sending CSH message %s", message)
        await self._websocket.send(b"\x01" + json.dumps(message.to_json()).encode())

    async def send_sme_hello_update_message(self) -> None:
        if self._current_state.is_ready():
            phase = CSHPhases.READY
        else:
            phase = CSHPhases.PENDING

        wait_for_ready_left = self._wait_for_ready_timer.time_left()
        waiting = None
        if not await self._wait_for_ready_timer.has_completed() and wait_for_ready_left is not None:
            waiting = datetime.timedelta(seconds=wait_for_ready_left)

        message = CSHMessage(phase=phase, waiting=waiting, prolongation_request=None)
        await self.send_csh_message(message)

    async def decide_incoming_prolongation_request(self, message: CSHMessage):
        # TODO Check if we will accept new prolongation request. Spec says we should accept at
        #  least twice.
        self._wait_for_ready_timer = self._wait_for_ready_timer.postpone(
            self.CSH_TIMEOUT_T_HELLO_INC
        )
        log.debug(
            "Granting prolongation request. Postponing wait_for_ready_timer by %s seconds. New "
            "duration is %s",
            self.CSH_TIMEOUT_T_HELLO_INC.total_seconds(),
            self._wait_for_ready_timer.time_left(),
        )

    async def decide_next_input(self) -> Optional[CSHMessage]:
        finishes = {
            "csh_message": self.receive_csh_message(),
            "wait_for_ready_timer": self._wait_for_ready_timer.wait_until_completed(),
            "send_prolongation_timer": self._send_prolongation_timer.wait_until_completed(),
            "prolongation_request_reply_timer": self._prolongation_request_reply_timer.wait_until_completed(),
        }
        if self._current_state.is_pending():
            finishes["receive_trust"] = self._trust_manager.wait_to_trust(self._remote_ski)

        result = await FinishFirst(finishes).run()

        message = None
        if "wait_for_ready_timer" in result:
            log.debug("Wait_for_ready_timer expired")
            if self._current_state.is_ready():
                self._current_state = CSHStates.SME_HELLO_STATE_READY_TIMEOUT
            elif self._current_state.is_pending():
                self._current_state = CSHStates.SME_HELLO_STATE_PENDING_TIMEOUT
        elif "send_prolongation_timer" in result or "prolongation_request_reply_timer" in result:
            log.debug("send_prolongation_timer or prolongation_request_reply_timer expired")
            if self._current_state.is_ready():
                raise RuntimeError("State should not be ready, something happened.")
            self._current_state = CSHStates.SME_HELLO_STATE_PENDING_TIMEOUT
        elif "receive_trust" in result:
            log.debug("Received trust for remote %s.", self._remote_ski)
            self._send_prolongation_timer.cancel()
            self._prolongation_request_reply_timer.cancel()
            if self._other_side_trusts_us:
                self._current_state = CSHStates.SME_HELLO_OK
            else:
                self._current_state = CSHStates.SME_HELLO_STATE_READY_LISTEN
            await self.send_sme_hello_update_message()

        if "csh_message" in result:
            message: CSHMessage = result["csh_message"]
            self._previously_received_message = message
            if message.phase == CSHPhases.READY:
                self._other_side_trusts_us = True

        return message

    async def run(self) -> None:
        abort = False

        previous_state = self._current_state
        while not abort and self._current_state != CSHStates.SME_HELLO_OK:
            log.debug("Current state: %s", CSHStates(self._current_state).name)

            state_at_start = self._current_state
            if self._current_state == CSHStates.SME_HELLO_STATE_READY_INIT:
                self._wait_for_ready_timer.start(self.CSH_TIMEOUT_T_HELLO_INIT)
                self._send_prolongation_timer.cancel()
                self._prolongation_request_reply_timer.cancel()
                await self.send_sme_hello_update_message()
                self._current_state = CSHStates.SME_HELLO_STATE_READY_LISTEN
            elif self._current_state == CSHStates.SME_HELLO_STATE_READY_LISTEN:
                message = await self.decide_next_input()

                if message:
                    if message.phase == CSHPhases.READY:
                        log.debug(
                            "Received READY from remote while local is ready. "
                            "Transition to HELLO_OK."
                        )
                        self._current_state = CSHStates.SME_HELLO_OK
                    elif message.phase == CSHPhases.PENDING:
                        log.debug("Received PENDING")
                        if message.prolongation_request:
                            await self.decide_incoming_prolongation_request(message)
                            await self.send_sme_hello_update_message()
                    elif message.phase == CSHPhases.ABORTED:
                        log.debug("Received ABORTED")
                        abort = True
            elif self._current_state == CSHStates.SME_HELLO_STATE_READY_TIMEOUT:
                abort = True
            elif self._current_state == CSHStates.SME_HELLO_STATE_PENDING_INIT:
                self._wait_for_ready_timer.start(self.CSH_TIMEOUT_T_HELLO_INIT)
                self._send_prolongation_timer.cancel()
                self._prolongation_request_reply_timer.cancel()
                await self.send_sme_hello_update_message()
                self._current_state = CSHStates.SME_HELLO_STATE_PENDING_LISTEN
            elif self._current_state == CSHStates.SME_HELLO_STATE_PENDING_LISTEN:
                message = await self.decide_next_input()

                if message:
                    log.debug("Received message while PENDING_LISTEN.")
                    if message.phase == CSHPhases.READY and message.waiting is None:
                        log.error("Missing waiting field in message. Aborting.")
                        abort = True
                    elif (message.phase == CSHPhases.READY and message.waiting) or (
                        message.phase == CSHPhases.PENDING
                        and message.waiting
                        and message.prolongation_request is None
                    ):
                        log.debug("Remote is READY and waiting. Prolongation request was accepted.")

                        self._prolongation_request_reply_timer.cancel()
                        self._prolongation_request_reply_timer = AsyncTimer()
                        if message.phase == CSHPhases.READY and message.waiting:
                            self._wait_for_ready_timer.cancel()

                        if message.waiting >= self.CSH_TIMEOUT_T_HELLO_PROLONG_THR_INC:
                            new_send_prolongation_request_timer_duration = (
                                message.waiting - self.CSH_TIMEOUT_T_HELLO_PROLONG_WAITTING_GAP
                            )
                            log.debug(
                                "Calculated send_prolongation_request_timer duration %s",
                                new_send_prolongation_request_timer_duration,
                            )
                            self._send_prolongation_timer.cancel()
                            if (
                                new_send_prolongation_request_timer_duration
                                >= self.CSH_TIMEOUT_T_HELLO_PROLONG_MIN
                            ):
                                log.debug("Starting send_prolongation_timer.")
                                self._send_prolongation_timer = AsyncTimer()
                                self._send_prolongation_timer.start(
                                    new_send_prolongation_request_timer_duration
                                )
                        else:
                            log.debug(
                                "Prolongation request timer was too little, cancelling "
                                "send_prolongation_timer."
                            )
                            self._send_prolongation_timer.cancel()
                    elif (
                        message.phase == CSHPhases.PENDING
                        and message.waiting is None
                        and message.prolongation_request
                    ):
                        log.debug("Remote is PENDING and requested prolongation.")
                        await self.decide_incoming_prolongation_request(message)
                        await self.send_sme_hello_update_message()
                    elif message.phase == CSHPhases.ABORTED:
                        log.debug("Remote wants to abort.")
                        abort = True
                    else:
                        log.debug("Unknown message pattern, abort.")
                        abort = True
            elif self._current_state == CSHStates.SME_HELLO_STATE_PENDING_TIMEOUT:
                if await self._wait_for_ready_timer.has_completed():
                    log.warning("Remote was not ready in time, abort.")
                    abort = True
                elif await self._send_prolongation_timer.has_completed():
                    log.debug("send_prolongation_timer has expired. Requesting prolongation.")
                    send_message = CSHMessage(
                        phase=CSHPhases.PENDING, prolongation_request=True, waiting=None
                    )
                    await self.send_csh_message(send_message)

                    if self._previously_received_message:
                        timer_duration = self._previously_received_message.waiting
                    else:
                        timer_duration = datetime.timedelta(
                            seconds=1.1 * self._wait_for_ready_timer.time_left()
                        )
                    self._prolongation_request_reply_timer.start(timer_duration)
                    self._send_prolongation_timer = AsyncTimer()
                    self._current_state = previous_state
                elif await self._prolongation_request_reply_timer.has_completed():
                    log.debug("request_prolongation_reply_timer has expired, abort")
                    abort = True
            else:
                raise RuntimeError("This should not happen, at least one pattern should fit.")

            previous_state = state_at_start

        self._wait_for_ready_timer.cancel()
        self._send_prolongation_timer.cancel()
        self._prolongation_request_reply_timer.cancel()

        if abort:
            log.debug("CSH requested abort")
            send_message = CSHMessage(
                phase=CSHPhases.ABORTED, prolongation_request=None, waiting=None
            )
            await self.send_csh_message(send_message)
            raise AbortConnectionException()
        else:
            log.debug("CSH was successful.")

"""Connection Mode Initialisation layer."""

import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from enum import IntEnum, Enum
from typing import Dict, Any, List, TypeVar, Generic, Optional

from shipproto.connection_layers.abstract_layer import AbortConnectionException
from shipproto.finish_first import FinishFirst
from shipproto.timer import AsyncTimer
from shipproto.websocket import Websocket

log = logging.getLogger("ship")


class CSHPClientStates(IntEnum):
    SME_PROT_H_STATE_CLIENT_INIT = 0
    SME_PROT_H_STATE_CLIENT_LISTEN_CHOICE = 1
    SME_PROT_H_STATE_TIMEOUT = 2
    SME_PROT_H_STATE_CLIENT_OK = 3


class CSHPServerStates(IntEnum):
    SME_PROT_H_STATE_SERVER_INIT = 0
    SME_PROT_H_STATE_SERVER_LISTEN_PROPOSAL = 1
    SME_PROT_H_STATE_SERVER_LISTEN_CONFIRM = 2
    SME_PROT_H_STATE_TIMEOUT = 3
    SME_PROT_H_STATE_SERVER_OK = 4


class CSHPProtocolHandshakeType(Enum):
    ANNOUNCE_MAX = "announceMax"
    SELECT = "SELECT"


class SHIPFormats(Enum):
    JSON_UTF8 = "JSON-UTF8"
    JSON_UTF16 = "JSON-UTF16"


M = TypeVar("M")


class CSHPMessage(Generic[M]):
    def to_json(self) -> Dict[str, Any]:
        ...

    @staticmethod
    def json_is(cshp_json_msg: Dict[str, Any]) -> bool:
        ...

    @staticmethod
    def from_json(cshp_json_msg: Dict[str, Any]) -> M:
        ...


@dataclass
class CSHPProtocolHandshakeMessage(CSHPMessage["CSHPProtocolHandshakeMessage"]):
    handshake_type: CSHPProtocolHandshakeType
    version_major: int
    version_minor: int
    formats: List[SHIPFormats]

    def to_json(self) -> Dict[str, Any]:
        return {
            "messageProtocolHandshake": [
                {"handshakeType": self.handshake_type.value},
                {"version": {"major": self.version_major, "minor": self.version_minor}},
                {"formats": [{"format": [format_.value for format_ in self.formats]}]},
            ]
        }

    @staticmethod
    def json_is(cshp_json_msg: Dict[str, Any]) -> bool:
        return "messageProtocolHandshake" in cshp_json_msg

    @staticmethod
    def from_json(cshp_json_msg: Dict[str, Any]) -> "CSHPMessage":
        handshake_type = None
        version_major = None
        version_minor = None
        formats = None

        try:
            for item in cshp_json_msg["messageProtocolHandshake"]:
                if len(item) != 1:
                    log.error(
                        "Each item in CSHP message is expected to have a single key, "
                        "value pair. Found multiple keys %s in message %s",
                        list(item.keys()),
                        cshp_json_msg,
                    )
                    raise AbortConnectionException

                item: Dict[str, Any]
                key = next(iter(item))
                value = item[key]
                if key == "handshakeType":
                    handshake_type = CSHPProtocolHandshakeType(value)
                elif key == "version":
                    version_major = value["major"]
                    version_minor = value["minor"]
                elif key == "formats":
                    formats = [SHIPFormats(format_) for format_ in value[0]["format"]]
                else:
                    log.error("Unexpected field %s in CSHP message %s", key, cshp_json_msg)
                    raise AbortConnectionException
        except (KeyError, ValueError, IndexError):
            log.error("Could not parse CSHP message after parsing to JSON: %s", cshp_json_msg)
            raise AbortConnectionException

        def confirm_value(field_value, field_name):
            if field_value is None:
                log.error(
                    f"Missing required field '{field_name}' in CSHP message %s", cshp_json_msg
                )
                raise AbortConnectionException

        confirm_value(handshake_type, "handshakeType")
        confirm_value(version_major, "version.major")
        confirm_value(version_minor, "version.minor")
        confirm_value(formats, "formats.format")

        return CSHPProtocolHandshakeMessage(handshake_type, version_major, version_minor, formats)


@dataclass
class CSHPProtocolHandshakeErrorMessage(CSHPMessage["CSHPProtocolHandshakeErrorMessage"]):
    error: int

    def to_json(self) -> Dict[str, Any]:
        return {"messageProtocolHandshakeError": [{"error": self.error}]}

    @staticmethod
    def json_is(cshp_json_msg: Dict[str, Any]) -> bool:
        return "messageProtocolHandshakeError" in cshp_json_msg

    @staticmethod
    def from_json(cshp_json_msg: Dict[str, Any]) -> "CSHPProtocolHandshakeErrorMessage":
        error = None

        try:
            for item in cshp_json_msg["messageProtocolHandshakeError"]:
                if len(item) != 1:
                    log.error(
                        "Each item in CSHP message is expected to have a single key, "
                        "value pair. Found multiple keys %s in message %s",
                        list(item.keys()),
                        cshp_json_msg,
                    )
                    raise AbortConnectionException

                item: Dict[str, Any]
                key = next(iter(item))
                value = item[key]
                if key == "error":
                    error = value
                else:
                    log.error("Unexpected field %s in CSHP message %s", key, cshp_json_msg)
                    raise AbortConnectionException
        except (KeyError, ValueError, IndexError):
            log.error("Could not parse CSHP message after parsing to JSON: %s", cshp_json_msg)
            raise AbortConnectionException

        def confirm_value(field_value, field_name):
            if field_value is None:
                log.error(
                    f"Missing required field '{field_value}' in CSHP message %s", cshp_json_msg
                )
                raise AbortConnectionException

        confirm_value(error, "error")

        return CSHPProtocolHandshakeErrorMessage(error)


class AbstractCSHPLayer:
    CSHP_TIMEOUT_WAIT = timedelta(seconds=10)

    _websocket: Websocket
    _remote_ski: str

    _wait_timer: AsyncTimer

    def __init__(self, websocket: Websocket, remote_ski: str):
        self._websocket = websocket
        self._remote_ski = remote_ski
        self._wait_timer = AsyncTimer()

    async def send_cshp_message(self, message: CSHPMessage) -> None:
        log.debug("Sending CSH message %s", message)
        await self._websocket.send(b"\x01" + json.dumps(message.to_json()).encode())

    async def receive_cshp_message(self) -> CSHPMessage:
        msg = await self._websocket.recv()

        if len(msg) == 0:
            log.error("Received an empty CSHP message.")
            raise AbortConnectionException()

        msg_type = msg[0]

        if isinstance(msg_type, str):
            msg_type = msg_type.encode()

        if msg_type != 1 and msg_type != b"\x01":
            log.error("CSHP message expected with message type 1, received %s", msg_type)
            raise AbortConnectionException()

        try:
            msg_value = json.loads(msg[1:])
        except json.JSONDecodeError:
            log.error("Could not parse CSHP message value as json. Received %s", msg[1:])
            raise AbortConnectionException()

        if CSHPProtocolHandshakeMessage.json_is(msg_value):
            message = CSHPProtocolHandshakeMessage.from_json(msg_value)
            log.debug("Received CSHP protocol handshake message %s", message)
        elif CSHPProtocolHandshakeErrorMessage.json_is(msg_value):
            message = CSHPProtocolHandshakeErrorMessage.from_json(msg_value)
            log.debug("Received CSHP protocol handshake error message %s", message)
        else:
            raise AbortConnectionException(f"Unknown message {msg_value}")

        return message


class CSHPClientLayer(AbstractCSHPLayer):
    _current_state: CSHPClientStates

    def __init__(self, websocket: Websocket, remote_ski: str):
        super().__init__(websocket, remote_ski)

        self._current_state = CSHPClientStates.SME_PROT_H_STATE_CLIENT_INIT

    async def decide_next_input(self) -> Optional[CSHPMessage]:
        finishes = {
            "cshp_message": self.receive_cshp_message(),
            "wait_timer": self._wait_timer.wait_until_completed(),
        }

        result = await FinishFirst(finishes).run()

        message = None
        if "cshp_message" in result:
            message = result["cshp_message"]

        if "wait_timer" in result:
            log.debug("Wait_timer expired")
            self._current_state = CSHPClientStates.SME_PROT_H_STATE_TIMEOUT

        return message

    async def run(self) -> (int, int):
        abort = False
        error_code = None

        log.debug("Starting CSHP as client.")
        while not abort and self._current_state != CSHPClientStates.SME_PROT_H_STATE_CLIENT_OK:
            log.debug("Current state: %s", CSHPClientStates(self._current_state).name)

            if self._current_state == CSHPClientStates.SME_PROT_H_STATE_CLIENT_INIT:
                await self.send_cshp_message(
                    CSHPProtocolHandshakeMessage(
                        CSHPProtocolHandshakeType.ANNOUNCE_MAX,
                        version_major=1,
                        version_minor=0,
                        formats=[SHIPFormats.JSON_UTF8],
                    )
                )
                self._wait_timer.start(self.CSHP_TIMEOUT_WAIT)
                self._current_state = CSHPClientStates.SME_PROT_H_STATE_CLIENT_LISTEN_CHOICE
            elif self._current_state == CSHPClientStates.SME_PROT_H_STATE_CLIENT_LISTEN_CHOICE:
                maybe_msg = await self.decide_next_input()

                if isinstance(maybe_msg, CSHPProtocolHandshakeMessage):
                    self._wait_timer.cancel()
                    self._wait_timer = AsyncTimer()

                    if not all(
                        [
                            maybe_msg.handshake_type == CSHPProtocolHandshakeType.SELECT,
                            maybe_msg.version_major == 1,
                            maybe_msg.version_minor == 0,
                            len(maybe_msg.formats) == 1,
                            maybe_msg.formats[0] == SHIPFormats.JSON_UTF8,
                        ]
                    ):
                        abort = True
                        error_code = 3
                    else:
                        await self.send_cshp_message(maybe_msg)
                        self._current_state = CSHPClientStates.SME_PROT_H_STATE_CLIENT_OK
                elif maybe_msg is not None:
                    abort = True
                    error_code = 2
            elif self._current_state == CSHPClientStates.SME_PROT_H_STATE_TIMEOUT:
                abort = True
                error_code = 1
            else:
                raise RuntimeError("This should not happen, at least one pattern should fit.")

        self._wait_timer.cancel()

        if abort:
            log.debug("CSHP requested abort")
            send_message = CSHPProtocolHandshakeErrorMessage(error=error_code)
            await self.send_cshp_message(send_message)
            raise AbortConnectionException()
        else:
            log.debug("CSHP was successful.")

        return 1, 0


class CSHPServerLayer(AbstractCSHPLayer):
    _current_state: CSHPServerStates

    def __init__(self, websocket: Websocket, remote_ski: str):
        super().__init__(websocket, remote_ski)

        self._current_state = CSHPServerStates.SME_PROT_H_STATE_SERVER_INIT

    async def decide_next_input(self) -> Optional[CSHPMessage]:
        finishes = {
            "cshp_message": self.receive_cshp_message(),
            "wait_timer": self._wait_timer.wait_until_completed(),
        }

        result = await FinishFirst(finishes).run()

        message = None
        if "cshp_message" in result:
            message = result["cshp_message"]

        if "wait_timer" in result:
            log.debug("Wait_timer expired")
            self._current_state = CSHPServerStates.SME_PROT_H_STATE_TIMEOUT

        return message

    async def run(self) -> (int, int):
        abort = False
        error_code = None

        proposed_handshake = None
        log.debug("Starting CSHP as server.")
        while not abort and self._current_state != CSHPServerStates.SME_PROT_H_STATE_SERVER_OK:
            log.debug("Current state: %s", CSHPClientStates(self._current_state).name)

            if self._current_state == CSHPServerStates.SME_PROT_H_STATE_SERVER_INIT:
                self._wait_timer.start(self.CSHP_TIMEOUT_WAIT)
                self._current_state = CSHPServerStates.SME_PROT_H_STATE_SERVER_LISTEN_PROPOSAL
            elif self._current_state == CSHPServerStates.SME_PROT_H_STATE_SERVER_LISTEN_PROPOSAL:
                maybe_msg = await self.decide_next_input()

                if isinstance(maybe_msg, CSHPProtocolHandshakeMessage):
                    self._wait_timer.cancel()
                    self._wait_timer = AsyncTimer()

                    if not all(
                        [
                            maybe_msg.handshake_type == CSHPProtocolHandshakeType.ANNOUNCE_MAX,
                            maybe_msg.version_major == 1,
                            maybe_msg.version_minor == 0,
                            SHIPFormats.JSON_UTF8 in maybe_msg.formats,
                        ]
                    ):
                        abort = True
                        error_code = 3
                    else:
                        proposed_handshake = CSHPProtocolHandshakeMessage(
                            CSHPProtocolHandshakeType.SELECT,
                            version_major=1,
                            version_minor=0,
                            formats=[SHIPFormats.JSON_UTF8],
                        )
                        await self.send_cshp_message(proposed_handshake)
                        self._wait_timer.start(self.CSHP_TIMEOUT_WAIT)
                        self._current_state = (
                            CSHPServerStates.SME_PROT_H_STATE_SERVER_LISTEN_CONFIRM
                        )
                elif maybe_msg is not None:
                    abort = True
                    error_code = 2
            elif self._current_state == CSHPServerStates.SME_PROT_H_STATE_SERVER_LISTEN_CONFIRM:
                maybe_msg = await self.decide_next_input()
                if isinstance(maybe_msg, CSHPProtocolHandshakeMessage):
                    self._wait_timer.cancel()
                    self._wait_timer = AsyncTimer()

                    if not maybe_msg == proposed_handshake:
                        abort = True
                        error_code = 3
                    else:
                        self._current_state = CSHPServerStates.SME_PROT_H_STATE_SERVER_OK
                elif maybe_msg is not None:
                    abort = True
                    error_code = 2
            elif self._current_state == CSHPServerStates.SME_PROT_H_STATE_TIMEOUT:
                abort = True
                error_code = 1
            else:
                raise RuntimeError("This should not happen, at least one pattern should fit.")

        self._wait_timer.cancel()

        if abort:
            log.debug("CSHP requested abort")
            send_message = CSHPProtocolHandshakeErrorMessage(error=error_code)
            await self.send_cshp_message(send_message)
            raise AbortConnectionException()
        else:
            log.debug("CSHP was successful.")

        return 1, 0

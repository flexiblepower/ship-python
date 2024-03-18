"""Connection Mode Initialisation layer."""

import json
import logging
from dataclasses import dataclass
from enum import Enum
import re
from typing import Dict, Any, TypeVar, Generic, Optional

from shipproto.connection_layers.abstract_layer import AbortConnectionException
from shipproto.websocket import Websocket

log = logging.getLogger("ship")


class PinState(Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    PIN_OK = "pinOk"
    NONE = "none"


class PinInputPermissionType(Enum):
    BUSY = "busy"
    OK = "ok"


M = TypeVar("M")


class PinMessage(Generic[M]):
    def to_json(self) -> Dict[str, Any]:
        ...

    @staticmethod
    def json_is(pin_json_msg: Dict[str, Any]) -> bool:
        ...

    @staticmethod
    def from_json(pin_json_msg: Dict[str, Any]) -> M:
        ...


@dataclass
class PinStateMessage(PinMessage["PinStateMessage"]):
    pin_state: PinState
    input_permission: Optional[PinInputPermissionType]

    def to_json(self) -> Dict[str, Any]:
        msg = {
            "connectionPinState": [
                {"pinState": self.pin_state.value},
            ]
        }

        if self.input_permission:
            msg["connectionPinState"].append({"inputPermission": self.input_permission.value})

        return msg

    @staticmethod
    def json_is(pin_json_msg: Dict[str, Any]) -> bool:
        return "connectionPinState" in pin_json_msg

    @staticmethod
    def from_json(pin_json_msg: Dict[str, Any]) -> "PinStateMessage":
        pin_state = None
        input_permission = None

        try:
            for item in pin_json_msg["connectionPinState"]:
                if len(item) != 1:
                    log.error(
                        "Each item in PIN message is expected to have a single key, "
                        "value pair. Found multiple keys %s in message %s",
                        list(item.keys()),
                        pin_json_msg,
                    )
                    raise AbortConnectionException

                item: Dict[str, Any]
                key = next(iter(item))
                value = item[key]
                if key == "pinState":
                    pin_state = PinState(value)
                elif key == "inputPermission":
                    input_permission = PinInputPermissionType(value)
                else:
                    log.error("Unexpected field %s in PIN message %s", key, pin_json_msg)
                    raise AbortConnectionException
        except (KeyError, ValueError, IndexError):
            log.error("Could not parse PIN message after parsing to JSON: %s", pin_json_msg)
            raise AbortConnectionException

        def confirm_value(field_value, field_name):
            if field_value is None:
                log.error(f"Missing required field '{field_name}' in PIN message %s", pin_json_msg)
                raise AbortConnectionException

        confirm_value(pin_state, "pinState")

        return PinStateMessage(pin_state, input_permission)


@dataclass
class PinInputMessage(PinMessage["PinInputMessage"]):
    PIN_REGEX = re.compile(r"[0-9a-fA-F]{8,16}")
    pin: str

    def __init__(self, pin):
        if PinInputMessage.PIN_REGEX.fullmatch(pin):
            self.pin = pin
        else:
            raise ValueError(
                f"PIN was unsupported. Should conform to {PinInputMessage.PIN_REGEX.pattern} but found {pin}."
            )

    def to_json(self) -> Dict[str, Any]:
        return {
            "connectionPinInput": [
                {"pin": self.pin},
            ]
        }

    @staticmethod
    def json_is(pin_json_msg: Dict[str, Any]) -> bool:
        return "connectionPinInput" in pin_json_msg

    @staticmethod
    def from_json(pin_json_msg: Dict[str, Any]) -> "PinInputMessage":
        pin = None

        try:
            for item in pin_json_msg["connectionPinInput"]:
                if len(item) != 1:
                    log.error(
                        "Each item in PIN message is expected to have a single key, "
                        "value pair. Found multiple keys %s in message %s",
                        list(item.keys()),
                        pin_json_msg,
                    )
                    raise AbortConnectionException

                item: Dict[str, Any]
                key = next(iter(item))
                value = item[key]
                if key == "pin":
                    pin = value
                else:
                    log.error("Unexpected field %s in PIN message %s", key, pin_json_msg)
                    raise AbortConnectionException
        except (KeyError, ValueError, IndexError):
            log.error("Could not parse PIN message after parsing to JSON: %s", pin_json_msg)
            raise AbortConnectionException

        def confirm_value(field_value, field_name):
            if field_value is None:
                log.error(f"Missing required field '{field_name}' in PIN message %s", pin_json_msg)
                raise AbortConnectionException

        confirm_value(pin, "pin")

        return PinInputMessage(pin)


@dataclass
class PinErrorMessage(PinMessage["PinErrorMessage"]):
    error: int

    def __init__(self, error):
        self.error = error

    def to_json(self) -> Dict[str, Any]:
        return {
            "connectionPinError": [
                {"error": self.error},
            ]
        }

    @staticmethod
    def json_is(pin_json_msg: Dict[str, Any]) -> bool:
        return "connectionPinError" in pin_json_msg

    @staticmethod
    def from_json(pin_json_msg: Dict[str, Any]) -> "PinErrorMessage":
        error = None

        try:
            for item in pin_json_msg["connectionPinError"]:
                if len(item) != 1:
                    log.error(
                        "Each item in PIN message is expected to have a single key, "
                        "value pair. Found multiple keys %s in message %s",
                        list(item.keys()),
                        pin_json_msg,
                    )
                    raise AbortConnectionException

                item: Dict[str, Any]
                key = next(iter(item))
                value = item[key]
                if key == "error":
                    error = value
                else:
                    log.error("Unexpected field %s in PIN message %s", key, pin_json_msg)
                    raise AbortConnectionException
        except (KeyError, ValueError, IndexError):
            log.error("Could not parse PIN message after parsing to JSON: %s", pin_json_msg)
            raise AbortConnectionException

        def confirm_value(field_value, field_name):
            if field_value is None:
                log.error(f"Missing required field '{field_name}' in PIN message %s", pin_json_msg)
                raise AbortConnectionException

        confirm_value(error, "error")

        return PinErrorMessage(error)


class PinLayer:
    _websocket: Websocket
    _remote_ski: str

    def __init__(self, websocket: Websocket, remote_ski: str):
        self._websocket = websocket
        self._remote_ski = remote_ski

    async def send_pin_message(self, message: PinMessage) -> None:
        log.debug("Sending PIN message %s", message)
        await self._websocket.send(b"\x01" + json.dumps(message.to_json()).encode())

    async def receive_pin_message(self) -> PinMessage:
        msg = await self._websocket.recv()

        if len(msg) == 0:
            log.error("Received an empty PIN message.")
            raise AbortConnectionException()

        msg_type = msg[0]

        if isinstance(msg_type, str):
            msg_type = msg_type.encode()

        if msg_type != 1 and msg_type != b"\x01":
            log.error("PIN message expected with message type 1, received %s", msg_type)
            raise AbortConnectionException()

        try:
            msg_value = json.loads(msg[1:])
        except json.JSONDecodeError:
            log.error("Could not parse PIN message value as json. Received %s", msg[1:])
            raise AbortConnectionException()

        if PinStateMessage.json_is(msg_value):
            message = PinStateMessage.from_json(msg_value)
            log.debug("Received PIN state message %s", message)
        elif PinInputMessage.json_is(msg_value):
            message = PinInputMessage.from_json(msg_value)
            log.debug("Received PIN input message %s", message)
        elif PinErrorMessage.json_is(msg_value):
            message = PinErrorMessage.from_json(msg_value)
            log.debug("Received PIN error message %s", message)
        else:
            raise AbortConnectionException(f"Unknown message {msg_value}")

        return message

    async def run(self) -> None:
        log.debug("Starting PIN")

        await self.send_pin_message(PinStateMessage(PinState.NONE, None))
        remote_init_msg = await self.receive_pin_message()

        if (
            isinstance(remote_init_msg, PinStateMessage)
            and remote_init_msg.pin_state != PinState.NONE
        ):
            raise AbortConnectionException(
                "Other side has PIN requirements and this library does not support that."
            )
        elif not isinstance(remote_init_msg, PinStateMessage):
            raise AbortConnectionException(f"Received unknown message {remote_init_msg}")

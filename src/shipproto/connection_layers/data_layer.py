import json
import logging
from dataclasses import dataclass
from typing import Union, Dict, List, Optional

from shipproto.connection_layers.abstract_layer import AbortConnectionException
from shipproto.websocket import Websocket

log = logging.getLogger("ship")

Data = Union[str, int, float, Dict, List]


@dataclass
class SHIPDataConnection:
    protocol_id: str
    _remote_ski: str
    _websocket: Websocket

    async def send_data(self, data: Data) -> None:
        data_msg = {
            "data": [
                {"header": [{"protocolId": self.protocol_id}]},
                {"payload": data},
            ]
        }

        await self._websocket.send(b"\x02" + json.dumps(data_msg).encode())

    async def recv_data(self) -> Data:
        data_msg_encoded = await self._websocket.recv()

        if len(data_msg_encoded) == 0:
            log.error("Received an empty Data message.")
            raise AbortConnectionException()

        msg_type = data_msg_encoded[0]

        if isinstance(msg_type, str):
            msg_type = msg_type.encode()

        if msg_type != 2 and msg_type != b"\x02":
            log.error("Data message expected with message type 2, received %s", msg_type)
            raise AbortConnectionException()

        try:
            msg_value = json.loads(data_msg_encoded[1:])
        except json.JSONDecodeError:
            log.error(
                "Could not parse CSHP message value as json. Received %s", data_msg_encoded[1:]
            )
            raise AbortConnectionException()
        else:
            return next(filter(lambda i: "payload" in i, msg_value["data"]))["payload"]

#!/usr/bin/env python

# https://www.electricmonk.nl/log/2018/06/02/ssl-tls-client-certificate-verification-with-python-v3-4-sslcontext/

import asyncio
import ssl
import sys
from typing import Coroutine

import websockets

import logging

from shipproto.connection_layers.abstract_layer import AbortConnectionException
from shipproto.connection_layers.cmi_layer import CMILayerClient
from shipproto.connection_layers.csh_layer import CSHLayer
from shipproto.connection_layers.cshp_layer import CSHPClientLayer
from shipproto.connection_layers.pin_layer import PinLayer
from shipproto.trust_manager import TrustManager

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    fmt="%(asctime)s [%(name)s][%(filename)s:%(lineno)d][%(levelname)s]: %(message)s"
)
handler.setFormatter(formatter)
root_logger.addHandler(handler)

log = logging.getLogger("ship")


async def main_tls():
    server_cert = "/home/fleursl/Downloads/test_client_cert_ship/certificate.pem"
    server_key = "/home/fleursl/Downloads/test_client_cert_ship/privatekey.pem"
    client_cert = server_cert
    client_key = server_key

    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=server_cert)
    ssl_context.load_cert_chain(certfile=client_cert, keyfile=client_key)

    async with websockets.connect(uri="wss://localhost:8765", ssl=ssl_context) as websocket:
        await websocket.send("Boink")
        print(websocket.transport.get_extra_info("peercert"))
        print(await websocket.recv())


async def decide_if_ski_is_trusted(ski: str, decide_to_trust: Coroutine[None, None, None]) -> None:
    sleep_seconds = 10
    log.debug("Deciding if to trust %s. Waiting %s sec to mimic user input", ski, sleep_seconds)
    await asyncio.sleep(sleep_seconds)
    log.debug("Decided to trust %s", ski)
    await decide_to_trust


async def main_sme():
    trust_manager = TrustManager(decide_if_ski_is_trusted)
    async with websockets.connect(uri="ws://localhost:8765/ship/") as websocket:
        try:
            log.info("Setting up SHIP connection.")
            log.debug("Starting CMI.")
            await CMILayerClient(websocket).run()
            log.debug("Finished CMI.")

            log.debug("Starting CSH.")
            await CSHLayer(websocket, trust_manager, "server").run()
            log.debug("Finished CSH.")

            log.debug("Starting CSHP.")
            (version_major, version_minor) = await CSHPClientLayer(websocket, "server").run()
            log.debug("Finished CSHP.")

            log.debug("Starting PIN.")
            await PinLayer(websocket, "server").run()
            log.debug("Finished PIN.")
        except AbortConnectionException:
            log.error("Closing connection due to SHIP connection issue.")
            await websocket.close()


asyncio.run(main_sme())

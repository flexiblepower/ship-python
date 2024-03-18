#!/usr/bin/env python

import asyncio
import binascii
import ssl
import sys
from typing import Coroutine

import cryptography.x509
from websockets.server import serve, WebSocketServerProtocol

import logging

from shipproto.connection_layers.abstract_layer import AbortConnectionException
from shipproto.connection_layers.cmi_layer import CMILayerServer
from shipproto.connection_layers.csh_layer import CSHLayer
from shipproto.connection_layers.cshp_layer import CSHPServerLayer
from shipproto.connection_layers.data_layer import SHIPDataConnection
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


async def echo(websocket: WebSocketServerProtocol, url_path: str):
    ssl_object: ssl.SSLSocket = websocket.transport.get_extra_info("ssl_object")
    peer_cert_der = ssl_object.getpeercert(binary_form=True)

    print("Received peer cert", type(peer_cert_der), peer_cert_der)
    peer_cert = cryptography.x509.load_der_x509_certificate(peer_cert_der)
    client_ski = cryptography.x509.SubjectKeyIdentifier.from_public_key(
        peer_cert.public_key()
    ).digest
    client_ski_hex = binascii.hexlify(client_ski, sep=":").decode()
    print("Client SKI:", client_ski_hex)

    async for message in websocket:
        await websocket.send(message)


async def main_tls():
    server_cert = "/home/fleursl/Downloads/test_client_cert_ship/certificate.pem"
    server_key = "/home/fleursl/Downloads/test_client_cert_ship/privatekey.pem"
    client_cert = server_cert
    client_key = server_key

    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.verify_mode = ssl.CERT_REQUIRED
    ssl_context.load_cert_chain(certfile=server_cert, keyfile=server_key)
    ssl_context.load_verify_locations(cafile=client_cert)

    async with serve(echo, "localhost", 8765, ssl=ssl_context):
        await asyncio.Future()  # run forever


async def decide_if_ski_is_trusted(ski: str, decide_to_trust: Coroutine[None, None, None]) -> None:
    sleep_seconds = 5
    log.debug("Deciding if to trust %s. Waiting %s sec to mimic user input", ski, sleep_seconds)
    await asyncio.sleep(sleep_seconds)
    log.debug("Decided to trust %s", ski)
    await decide_to_trust


async def ship_connection(websocket: WebSocketServerProtocol, url_path: str):
    trust_manager = TrustManager(decide_if_ski_is_trusted)
    try:
        if url_path != "/ship/":
            raise AbortConnectionException(f"url_path was {url_path} but should be /ship/")
        log.debug("Starting CMI.")
        await CMILayerServer(websocket).run()
        log.debug("Finished CMI.")

        log.debug("Starting CSH.")
        await CSHLayer(websocket, trust_manager, "client").run()
        log.debug("Finished CSH.")

        log.debug("Starting CSHP.")
        (version_major, version_minor) = await CSHPServerLayer(websocket, "client").run()
        log.debug("Finished CSHP.")

        log.debug("Starting PIN.")
        await PinLayer(websocket, "server").run()
        log.debug("Finished PIN.")

        conn = SHIPDataConnection("S2", "server", websocket)
        print(await conn.recv_data())
        await conn.send_data("This is a fake S2 message from the server")

    except AbortConnectionException:
        log.error("Closing connection due to SHIP connection issue.")
        await websocket.close()


async def main_sme():
    async with serve(ship_connection, "localhost", 8765):
        await asyncio.Future()  # run forever


asyncio.run(main_sme())

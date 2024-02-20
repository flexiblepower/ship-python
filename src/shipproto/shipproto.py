#!/usr/bin/env python

import asyncio
import binascii
import ssl
import sys

import cryptography.x509
from websockets.server import serve, WebSocketServerProtocol

import logging

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
root_logger.addHandler(handler)


async def echo(websocket: WebSocketServerProtocol, url_path: str):
    ssl_object: ssl.SSLSocket = websocket.transport.get_extra_info('ssl_object')
    peer_cert_der = ssl_object.getpeercert(binary_form=True)

    print('Received peer cert', type(peer_cert_der), peer_cert_der)
    peer_cert = cryptography.x509.load_der_x509_certificate(peer_cert_der)
    client_ski = cryptography.x509.SubjectKeyIdentifier.from_public_key(peer_cert.public_key()).digest
    client_ski_hex = binascii.hexlify(client_ski, sep=':').decode()
    print('Client SKI:', client_ski_hex)

    async for message in websocket:
        await websocket.send(message)


async def main():
    server_cert = '/home/fleursl/Downloads/test_client_cert_ship/certificate.pem'
    server_key = '/home/fleursl/Downloads/test_client_cert_ship/privatekey.pem'
    client_cert = server_cert
    client_key = server_key

    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.verify_mode = ssl.CERT_REQUIRED
    ssl_context.load_cert_chain(certfile=server_cert, keyfile=server_key)
    ssl_context.load_verify_locations(cafile=client_cert)

    async with serve(echo, "localhost", 8765, ssl=ssl_context):
        await asyncio.Future()  # run forever

asyncio.run(main())

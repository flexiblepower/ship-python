#!/usr/bin/env python

# https://www.electricmonk.nl/log/2018/06/02/ssl-tls-client-certificate-verification-with-python-v3-4-sslcontext/

import asyncio
import ssl
import sys

import websockets

import logging

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
root_logger.addHandler(handler)

async def main():
    server_cert = '/home/fleursl/Downloads/test_client_cert_ship/certificate.pem'
    server_key = '/home/fleursl/Downloads/test_client_cert_ship/privatekey.pem'
    client_cert = server_cert
    client_key = server_key

    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=server_cert)
    ssl_context.load_cert_chain(certfile=client_cert, keyfile=client_key)

    async with websockets.connect(uri='wss://localhost:8765', ssl=ssl_context) as websocket:
        await websocket.send('Boink')
        print(websocket.transport.get_extra_info('peercert'))
        print(await websocket.recv())

asyncio.run(main())

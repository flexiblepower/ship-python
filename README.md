# SHIP Python

The EEBus SHIP protocol in Python. To be used for S2 protocol instead of EEBus SPINE.

## Status
This project is currently in proof-of-concept phase. It should not be integrated in any other
software (yet).

This implementation lacks:
- mDNS support: We expect the client to know the ip and port of the server.
- 'reverse connection': SHIP protocol allows for the server and client to reverse roles. This functionality is not implemented.
- Other PIN states than NONE: If one of the nodes requires a PIN to be send, the library will close with the appropriate error message.
- Closing the SHIP connection properly in data layer.

What is implemented:
- Setting up a connection going through all phases.
    - Connection mode initialisation (CMI) layer
    - Connection state 'Hello' (CSH) layer with prolongation & approve/disapprove trust.
    - Connection state 'Protocol handshake' layer.
    - Connection state 'PIN verification' (only pinState == 'none')
    - Connection Data Exchange by passing and receiving data.

## Trying it out

Install the `requirements.txt`.

To start the server:
```bash
PYTHONPATH="src/" python3 -m shipproto.shipproto
```

To start the client:
```bash
PYTHONPATH="src/" python3 -m shipproto.example_client
```

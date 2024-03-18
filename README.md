# SHIP Python

The EEBus SHIP protocol in Python. To be used for S2 protocol instead of EEBus SPINE.

## Status
This project is currently in proof-of-concept phase. It should not be integrated in any other
software (yet).


## Trying it out

To start the server:
```bash
PYTHONPATH="src/" python3 -m shipproto.shipproto
```

To start the client:
```bash
PYTHONPATH="src/" python3 -m shipproto.example_client
```

#!/bin/bash

python3 -m venv ./.venv
if [[ "$OSTYPE" != "win32" && "$OSTYPE" != "msys" ]]; then
  echo "Activating .venv first."
  . .venv/bin/activate
fi
pip3 install pip-tools

#!/bin/bash

if [[ "$OSTYPE" != "win32" && "$OSTYPE" != "msys" ]]; then
  echo "Activating .venv first."
  . .venv/bin/activate
fi

rm -Rf src/omotes_sdk/internal/orchestrator_worker_events/messages/
mkdir -p src/omotes_sdk/internal/orchestrator_worker_events/messages/
protoc -I task_messages_protocol/ --python_out src/omotes_sdk/internal/orchestrator_worker_events/messages/ ./task_messages_protocol/task.proto
protoc -I task_messages_protocol/ --mypy_out src/omotes_sdk/internal/orchestrator_worker_events/messages/ ./task_messages_protocol/task.proto
touch src/omotes_sdk/internal/orchestrator_worker_events/messages/__init__.py

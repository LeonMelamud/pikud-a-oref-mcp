#!/bin/bash
cd "$(dirname "$0")/.."
export PYTHONPATH="$(pwd)"
exec python -m src.core.mcp_server
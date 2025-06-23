#!/bin/bash
cd "/Users/Leon.Melamud/Documents/Cline/MCP/poha-real-time-alert-system"
export PYTHONPATH="/Users/Leon.Melamud/Documents/Cline/MCP/poha-real-time-alert-system"
export WEBHOOK_URL="http://localhost:8000/api/webhook/alerts"
export API_KEY="poha-test-key-2024-secure"
exec ./venv/bin/python -m src.core.mcp_server
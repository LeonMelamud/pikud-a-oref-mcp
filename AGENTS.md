# AGENTS.md — Pikud HaOref MCP Alert System

## Project Overview

Real-time Israeli emergency alert system that polls the official Pikud HaOref API, persists alerts to SQLite, and distributes them via SSE streaming, REST API, MCP tools, and a VS Code extension.

## Architecture

```
Pikud HaOref API (oref.org.il)
        │
        ▼
  ┌─────────────┐
  │ Polling Svc  │  polls every 2s
  └─────┬───────┘
        │ asyncio.Queue + SQLite
        ▼
  ┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
  │  FastAPI App │────▶│  SSE Gateway │────▶│ VS Code Extension│
  │  (port 8000)│     │  (port 8002) │     └─────────────────┘
  └─────┬───────┘     └──────────────┘
        │
        ▼
  ┌─────────────┐
  │  MCP Server  │  (port 8001, fastmcp)
  │  + SQLite    │
  └─────────────┘
```

### Services

| Service | Port | Docker Container | Description |
|---|---|---|---|
| Alert Poller | 8000 | `poha-alert-poller` | Main API: polling, SSE streaming, REST endpoints, test alerts |
| MCP Tools | 8001 | `poha-mcp-tools` | MCP tools for LLM access (fastmcp, streamable-http transport) |
| SSE Relay | 8002 | `poha-sse-relay` | Relay for VS Code extension, subscribes to main app's SSE |

## File Structure

```
src/
  api/
    main.py          — FastAPI app, lifespan, REST + SSE endpoints
    sse_gateway.py   — Separate FastAPI app relaying alerts to VS Code
  core/
    alert_queue.py   — asyncio.Queue for in-process alert distribution
    mcp_server.py    — MCP server (fastmcp) with alert tools
    state.py         — AppState dataclass (last_alert_id)
  db/
    database.py      — SQLite persistence (aiosqlite)
  services/
    polling.py       — Polls oref.org.il every 2s, queues + persists alerts
    sse.py           — SSE event generator for FastAPI streaming
  utils/
    geolocation.py   — GeoIP reader for optional geo-blocking
    security.py      — API key auth, rate limiting, geo middleware
tests/               — pytest test suite
docker/              — Dockerfile, mcp.Dockerfile, docker-compose.yml
vscode-extension/    — VS Code extension (TypeScript, EventSource)
skills/              — OpenClaw skill definition
```

## How to Run

### Docker (Recommended)

> **Important**: The Pikud HaOref API (oref.org.il) **geo-blocks non-Israeli IPs**. You must run Docker on a machine with an Israeli IP address (local machine in Israel, or a GCP `me-west1` VM).

```bash
make deploy  # One-command: creates .env, builds, starts, health-checks all 3 services
make build   # Build containers
make up      # Start all 3 services
make down    # Stop
make logs    # View logs
make status  # Show container status
```

SQLite DB is shared between `alert-poller` and `mcp-tools` via the `poha-alert-data` named volume.
All services read config from `.env` (auto-created from `.env.example` by `make deploy`).

### Local Development (without Docker)

```bash
# Install dependencies
pip install -r requirements.txt

# Run the FastAPI app
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# Run the MCP server (separate terminal)
python -m src.core.mcp_server

# Run the SSE gateway (separate terminal)
uvicorn src.api.sse_gateway:app --host 0.0.0.0 --port 8002
```

### Test Alerts

```bash
make test-alert       # Hebrew missile alert (תל אביב, רמת גן)
make test-alert-en    # English earthquake alert (Jerusalem, Haifa)
make test-alert-drill # Drill alert (כל הארץ)

# Or directly:
curl -X POST http://localhost:8000/api/test/fake-alert \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${API_KEY:-dev-secret-key}" \
  -d '{"data": ["תל אביב"], "cat": "1", "language": "he"}'
```

### Connect — MCP Client (VS Code, Claude Desktop, etc.)

Add to your MCP config (e.g. VS Code `mcp.json` or `claude_desktop_config.json`):

```jsonc
{
  "servers": {
    "pikud-haoref": {
      "type": "http",
      "url": "http://localhost:8001/mcp"
    }
  }
}
```

This gives your LLM access to tools: `check_current_alerts`, `get_alert_history`, `get_connection_status`, `get_city_alerts`, `get_db_stats`.

### Connect — REST API

```bash
# Health check
curl http://localhost:8000/health

# SSE stream (real-time, requires API key)
curl -N -H "X-API-Key: dev-secret-key" http://localhost:8000/api/alerts-stream

# Swagger UI
open http://localhost:8000/docs
```

### Connect — VS Code Extension

In VS Code extension settings, set the server URL to:
- **SSE URL**: `http://localhost:8002/api/alerts-stream`
- **API URL**: `http://localhost:8000`

## How to Test

```bash
pytest -v
```

Tests use `src.`-prefixed imports. The `conftest.py` mocks the background poller and DB init to prevent side effects.

## Production Deployment (GCP me-west1)

The oref.org.il API geo-blocks non-Israeli IPs. For production, deploy all 3 services on a **GCP e2-micro VM in `me-west1` (Tel Aviv)** — this is free-tier eligible and provides an Israeli IP.

### Setup

```bash
# 1. Create free VM in Tel Aviv
gcloud compute instances create pikud-haoref \
  --zone=me-west1-a \
  --machine-type=e2-micro \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --tags=http-server

# 2. Allow ports 8000-8002
gcloud compute firewall-rules create allow-pikud-haoref \
  --allow=tcp:8000-8002 --target-tags=http-server

# 3. SSH and install Docker
gcloud compute ssh pikud-haoref --zone=me-west1-a
sudo apt update && sudo apt install -y docker.io docker-compose
sudo usermod -aG docker $USER && newgrp docker

# 4. Clone, configure, and deploy
git clone <repo-url> && cd pikud-a-oref-mcp
cp .env.example .env  # Edit API_KEY for production!
make deploy
```

### GCP Service URLs

Replace `<GCP_VM_IP>` with your VM's external IP:

| Service | URL | Health Check |
|---|---|---|
| Alert Poller (REST + SSE) | `http://<GCP_VM_IP>:8000` | `/health` |
| MCP Tools | `http://<GCP_VM_IP>:8001/mcp` | `/health` |
| SSE Relay (VS Code) | `http://<GCP_VM_IP>:8002/api/alerts-stream` | `/health` |

### Why GCP me-west1?

- **Free forever** (e2-micro is always-free tier)
- **Israeli IP** from Tel Aviv data center — oref.org.il won't block it
- **Low latency** to oref.org.il (same country)
- **Docker works out of the box** on Debian

## Conventions

- **Imports**: All internal imports use relative paths (`..core.state`, `..services.polling`)
- **Tests**: Import with `src.` prefix (`from src.services.polling import ...`)
- **Patches**: Use full dotted path (`src.services.polling.app_state`)
- **Config**: Environment variables for all secrets and deployment settings
- **DB**: SQLite via aiosqlite, stored at `DATABASE_PATH` (default: `data/alerts.db`)
- **Alert format**: `{"id", "cat", "type", "title", "cities", "instructions"}` (from polling), raw oref format in DB
- **MCP**: Uses `fastmcp` library with streamable-http transport
- **No rate limiting**: Disabled for emergency alert system (immediate access required)
- **Docker names**: Services are `alert-poller`, `mcp-tools`, `sse-relay`; containers prefixed with `poha-`
- **Default API key**: `dev-secret-key` (change in `.env` for production)

### VS Code Extension

- Located in `vscode-extension/`, version 1.1.0
- Connects to SSE Gateway on port 8002 (configurable in settings)
- Fetches alert history from REST API (`/api/alerts/history`) on startup
- Uses exponential backoff reconnection (2s → 60s cap) with heartbeat monitoring
- Build: `cd vscode-extension && npx @vscode/vsce package --allow-missing-repository`
- Install: `code --install-extension pikud-haoref-alerts-1.1.0.vsix --force`

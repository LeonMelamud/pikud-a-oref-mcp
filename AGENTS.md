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

### Local Development

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

### Docker

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

## How to Test

```bash
pytest -v
```

Tests use `src.`-prefixed imports. The `conftest.py` mocks the background poller and DB init to prevent side effects.

## How to Deploy (Railway)

1. Push to GitHub
2. Connect repo to Railway
3. Set environment variables: `API_KEY`, `DATABASE_PATH`, `PORT`
4. Railway uses `railway.toml` for build config and health checks
5. The `/health` endpoint returns `{"status": "ok"}`

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

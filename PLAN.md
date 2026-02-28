# Pub-Sub Architecture Implementation Plan

## Overview

Convert the current dual-polling system to a publish-subscribe architecture where:
- **FastAPI Middleware** = Single poller + Publisher (SSE webhook)
- **MCP Server** = Subscriber (SSE client) + Tool provider
- **AI Assistants** = Consumers (MCP tools)

## Current Architecture (Problem)

```
┌─────────────────┐    ┌─────────────────┐
│   Gov API       │    │   Gov API       │
│                 │    │                 │
└─────────┬───────┘    └─────────┬───────┘
          │ polls                │ polls
          │ every 2s             │ every 2s
          ▼                      ▼
┌─────────────────┐    ┌─────────────────┐
│ FastAPI Service │    │   MCP Server    │
│   (main.py)     │    │ (mcp_server.py) │
└─────────────────┘    └─────────────────┘
```

**Issues:**
- Duplicate API calls
- Independent polling cycles
- No shared state
- Inefficient resource usage

## Desired Architecture (Solution)

```
                    ┌─────────────────┐
                    │   Gov API       │
                    │ (oref.org.il)   │
                    └─────────┬───────┘
                              │ polls every 2s
                              ▼
                    ┌─────────────────┐
                    │ FastAPI Service │ ◄── Single Source of Truth
                    │   (Middleware)  │
                    │   - Polling     │
                    │   - SSE Webhook │
                    └─────────┬───────┘
                              │ SSE Stream
                              ▼
                    ┌─────────────────┐
                    │   MCP Server    │ ◄── Subscriber
                    │ (SSE Client)    │
                    │   - Tools       │
                    │   - Resources   │
                    └─────────────────┘
```

## Implementation Steps

### Step 1: Enhance FastAPI Middleware

**File:** `main.py`

**Current SSE endpoint:** `/api/alerts-stream`
**Add new endpoint:** `/api/webhook/alerts` (public SSE endpoint for services)

```python
@app.get("/api/webhook/alerts", summary="Public Alert Webhook")
async def alerts_webhook(request: Request):
    """
    Public SSE endpoint for services (no API key required)
    Used by MCP server and other internal services
    """
    return StreamingResponse(alert_event_generator(request), media_type="text/event-stream")
```

### Step 2: Convert MCP Server to SSE Client

**File:** `mcp_server.py`

**Changes needed:**

1. **Remove direct API polling**
2. **Add SSE client functionality**
3. **Subscribe to FastAPI webhook**
4. **Update tools to use subscribed data**

**New architecture:**

```python
import httpx
import asyncio
from typing import AsyncGenerator

class AlertSubscriber:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.recent_alerts = []
        self.is_connected = False
    
    async def subscribe(self):
        """Subscribe to SSE webhook and process events"""
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", self.webhook_url) as response:
                self.is_connected = True
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        alert_data = json.loads(line[6:])
                        await self.process_alert(alert_data)
    
    async def process_alert(self, alert_data):
        """Process incoming alert from SSE stream"""
        self.recent_alerts.insert(0, {
            **alert_data,
            "received_at": datetime.now().isoformat()
        })
        # Keep only recent alerts
        if len(self.recent_alerts) > 50:
            self.recent_alerts.pop()
        
        logger.warning(f"🚨 NEW ALERT RECEIVED: {alert_data.get('id', 'N/A')}")

# Global subscriber instance
alert_subscriber = AlertSubscriber("http://localhost:8000/api/webhook/alerts")

# Start subscription in background
asyncio.create_task(alert_subscriber.subscribe())
```

### Step 3: Update MCP Tools

**Modified tools use subscribed data instead of direct polling:**

```python
@mcp.tool()
async def check_current_alerts() -> str:
    """Check for current active emergency alerts"""
    if not alert_subscriber.is_connected:
        return "❌ Not connected to alert stream"
    
    if not alert_subscriber.recent_alerts:
        return "✅ No recent alerts received"
    
    latest_alert = alert_subscriber.recent_alerts[0]
    # Format and return latest alert
    return format_alert(latest_alert)

@mcp.tool()
async def get_alert_history(limit: int = 10, region: str = None) -> str:
    """Get alert history from subscribed stream"""
    alerts = alert_subscriber.recent_alerts[:limit]
    # Filter by region if specified
    if region:
        alerts = [a for a in alerts if region.lower() in str(a.get('data', [])).lower()]
    
    return format_alert_history(alerts)
```

### Step 4: Configuration Changes

**Environment Variables:**

```env
# .env file
API_KEY=poha-test-key-2024-secure
WEBHOOK_URL=http://localhost:8000/api/webhook/alerts  # MCP server connects here
GEOIP_DB_PATH=/path/to/GeoLite2-Country.mmdb
```

**MCP Configuration:**

```json
{
  "mcpServers": {
    "poha-alerts": {
      "command": "python",
      "args": ["mcp_server.py"],
      "cwd": "/Users/Leon.Melamud/Documents/Cline/MCP/poha-real-time-alert-system",
      "env": {
        "PYTHONPATH": "/Users/Leon.Melamud/Documents/Cline/MCP/poha-real-time-alert-system",
        "WEBHOOK_URL": "http://localhost:8000/api/webhook/alerts"
      }
    }
  }
}
```

### Step 5: Update Project Structure

**Modified Files:**
- `main.py` - Add public webhook endpoint
- `mcp_server.py` - Convert to SSE client
- `requirements.txt` - Add SSE client dependencies
- `README.md` - Update architecture documentation
- `diagram.py` - Update architecture diagram

**New Files:**
- `alert_subscriber.py` - SSE client functionality
- `webhook_client.py` - Generic webhook client utilities

### Step 6: Testing Procedures

**Test Sequence:**

1. **Start FastAPI Service:**
   ```bash
   uvicorn main:app --reload
   ```

2. **Test Webhook Endpoint:**
   ```bash
   curl http://localhost:8000/api/webhook/alerts
   # Should stream keep-alive messages
   ```

3. **Start MCP Server:**
   ```bash
   python mcp_server.py
   # Should connect to webhook and log connection
   ```

4. **Test MCP Tools:**
   - Use Cursor to call `check_current_alerts`
   - Verify data comes from subscription, not direct polling

5. **Test Event Flow:**
   - Simulate alert (or wait for real one)
   - Verify: Gov API → FastAPI → Webhook → MCP Server → Tools

## Benefits of New Architecture

### Performance
- ✅ **50% reduction** in API calls to government server
- ✅ **Real-time propagation** of alerts
- ✅ **Reduced latency** for MCP tools

### Scalability
- ✅ **Multiple subscribers** can connect to webhook
- ✅ **Horizontal scaling** of MCP servers
- ✅ **Centralized polling** with distributed consumption

### Reliability
- ✅ **Single point of failure** for polling (easier to monitor)
- ✅ **Automatic reconnection** for SSE clients
- ✅ **Event replay** capability

### Architecture
- ✅ **Clean separation** of concerns
- ✅ **Publisher-subscriber** pattern
- ✅ **Event-driven** architecture

## Rollback Plan

If issues occur:

1. **Keep original files** as `.backup` copies
2. **Switch MCP config** back to direct polling
3. **Disable webhook endpoint** in FastAPI
4. **Revert to dual-polling** architecture

## Success Metrics

- [ ] **Single API polling** source confirmed
- [ ] **MCP server connects** to SSE webhook
- [ ] **Real-time alert propagation** working
- [ ] **All MCP tools** return correct data
- [ ] **Performance improvement** measured
- [ ] **No data loss** during transition

## Timeline

- **Phase 1** (30 min): Add webhook endpoint to FastAPI
- **Phase 2** (45 min): Convert MCP server to SSE client
- **Phase 3** (15 min): Update configurations and test
- **Phase 4** (15 min): Update documentation and diagrams

**Total Estimated Time:** 1.5 hours

## Next Steps

1. **Implement webhook endpoint** in FastAPI service
2. **Create SSE client** functionality for MCP server
3. **Test event flow** end-to-end
4. **Update documentation** and architecture diagrams
5. **Deploy and monitor** the new architecture

---

**Note:** This plan creates a true pub-sub system where the MCP server becomes an event-driven subscriber rather than an active poller, improving efficiency and scalability.

---

## Phase 2: Deploy, Extend, Integrate (February 2026)

### Completed

- [x] **Pub-sub architecture** — MCP server subscribes to FastAPI SSE webhook
- [x] **SSE Gateway** — Separate gateway for VS Code extension relay
- [x] **VS Code extension** — Tree view, notifications, test alerts
- [x] **Docker 3-service setup** — app, mcp-server, sse-gateway
- [x] **SQLite persistence** — `src/db/database.py` with `aiosqlite`, auto-init on startup
- [x] **REST API endpoints** — `/health`, `/api/alerts/history`, `/api/alerts/city/{name}`, `/api/alerts/stats`
- [x] **Fix VS Code extension** — configurable `serverUrl`, exact `deleteAlert`, `clearAllAlerts`, settings change listener, proper `deactivate()`
- [x] **Fix test imports** — all tests use `src.`-prefixed imports and patch paths
- [x] **Railway deployment config** — `railway.toml`, hardened Dockerfiles, `.env.example`, dynamic `$PORT`
- [x] **OpenClaw MCP integration** — skill definition, config example, `get_city_alerts` + `get_db_stats` MCP tools
- [x] **AGENTS.md** — project overview, architecture, conventions

### Deferred

- [ ] Redis pub-sub migration (solves single-consumer queue but adds external dependency)
- [ ] GeoIP bundling (disabled for external deployment)
- [ ] Extension TypeScript unit tests
- [ ] Rate limiting re-enablement
- [ ] Multi-instance horizontal scaling (SQLite = single-writer)
- [ ] GitHub Actions CI pipeline
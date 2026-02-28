---
name: pikud-haoref
description: 'Israeli emergency alerts via Pikud HaOref. Use when asked about missile alerts, rocket alerts, emergency alerts in Israel, "are there alerts in [city]?", Pikud HaOref status, or real-time SSE alert streaming. Provides MCP tools, REST API, SSE pub-sub, and OpenClaw webhook integration.'
argument-hint: 'City name in Hebrew (e.g., אשקלון, תל אביב) or alert query'
---

# Pikud HaOref Alert System

Use when the user asks about **Israeli emergency alerts**, missile alerts, Pikud HaOref, or "are there alerts in [city]?".

## MCP Server

This skill relies on a Pikud HaOref MCP server running via Docker (requires an Israeli IP — oref.org.il geo-blocks non-Israeli IPs).

### Docker (Recommended)

```bash
make deploy   # Build + start all 3 services
```

### MCP Client Config

Add to your MCP client config (VS Code `mcp.json`, Claude Desktop, OpenClaw, etc.):

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

For production on GCP me-west1, replace `localhost` with your VM's external IP.

### Service URLs

| Service | Local | Production (GCP) |
|---|---|---|
| REST API + SSE | `http://localhost:8000` | `http://<GCP_VM_IP>:8000` |
| MCP Server | `http://localhost:8001/mcp` | `http://<GCP_VM_IP>:8001/mcp` |
| SSE Relay (VS Code ext) | `http://localhost:8002/api/alerts-stream` | `http://<GCP_VM_IP>:8002/api/alerts-stream` |

## Available MCP Tools

| Tool | Description |
|---|---|
| `check_current_alerts` | Check for active emergency alerts (from SSE stream) |
| `get_alert_history` | Get recent alert history with optional city/region filtering |
| `get_city_alerts` | Query SQLite database for alerts in a specific city |
| `get_db_stats` | Get alert database statistics |
| `get_connection_status` | Check SSE subscription status |

## Usage Patterns

**"Are there alerts in Tel Aviv?"**
→ Use `get_city_alerts(city="תל אביב - יפו")`

**"What's the latest alert?"**
→ Use `check_current_alerts()`

**"Show alert history for the last week"**
→ Use `get_alert_history(limit=50)`

**"How many alerts have there been?"**
→ Use `get_db_stats()`

## Real-Time SSE Streams (Pub-Sub)

Subscribe to real-time alerts via Server-Sent Events. Any SSE-compatible client can connect and receive alerts as they happen — no polling needed.

### SSE Relay (public, no auth)

Best for external clients, VS Code extensions, and browser apps:

```bash
curl -N http://localhost:8002/api/alerts-stream
```

Sends JSON alert objects on the `data:` field, with `keep-alive` heartbeats every 30s.

### Main API SSE (requires API key)

Two equivalent endpoints with API key auth (`X-API-Key` header):

```bash
# Client-facing stream
curl -N -H "X-API-Key: dev-secret-key" \
  http://localhost:8000/api/alerts-stream

# Internal webhook stream (same data, for service-to-service)
curl -N -H "X-API-Key: dev-secret-key" \
  http://localhost:8000/api/webhook/alerts
```

### SSE Event Format

```
data: {"id":"...", "type":"missiles", "cities":["תל אביב"], "instructions":"...", "received_at":"..."}

data: keep-alive
```

### Integration Examples

**Python (httpx):**
```python
import httpx

async with httpx.AsyncClient(timeout=None) as client:
    async with client.stream("GET", "http://localhost:8002/api/alerts-stream") as resp:
        async for line in resp.aiter_lines():
            if line.startswith("data: ") and "keep-alive" not in line:
                alert = json.loads(line[6:])
                print(f"🚨 {alert['type']}: {alert['cities']}")
```

**JavaScript (EventSource):**
```javascript
const es = new EventSource("http://localhost:8002/api/alerts-stream");
es.onmessage = (e) => {
  if (e.data !== "keep-alive") {
    const alert = JSON.parse(e.data);
    console.log("🚨", alert.type, alert.cities);
  }
};
```

### REST API (pull-based)

For one-off queries instead of streaming:

```bash
# Current active alerts
curl http://localhost:8000/api/alerts/current

# Alert history (last 50)
curl http://localhost:8000/api/alerts/history

# Alerts by city
curl http://localhost:8000/api/alerts/city/תל%20אביב

# Statistics
curl http://localhost:8000/api/alerts/stats
```

## OpenClaw Integration (SSE → WhatsApp)

OpenClaw can't subscribe to SSE directly, but it has **webhooks** (`POST /hooks/agent`).
Use the included [bridge script](./scripts/sse_to_openclaw.py) to listen to the SSE stream, filter by city, and trigger OpenClaw to send WhatsApp messages.

### Architecture

```
SSE Relay (Docker)  →  Bridge Script  →  OpenClaw /hooks/agent  →  WhatsApp
```

### 1. Enable OpenClaw Webhooks

Add `enabled` and `token` to the `hooks` section of `~/.openclaw/openclaw.json`.

> **Important:** The hooks `token` **must be different** from the `gateway.auth.token`.
> If they match, OpenClaw will refuse to start with:
> `hooks.token must not match gateway auth token. Set a distinct hooks.token for hook ingress.`

If you already have `hooks.internal`, merge — don't overwrite:

```json
{
  "hooks": {
    "enabled": true,
    "token": "<generate-a-unique-token>",
    "internal": {
      "enabled": true,
      "entries": { ... }
    }
  }
}
```

Generate a token: `openssl rand -hex 24`

Then restart: `openclaw gateway restart`

### 2. Run the Bridge Script

```bash
# Watch אשקלון, send WhatsApp alerts to your phone
OPENCLAW_HOOK_TOKEN=your-secret-token \
python ./scripts/sse_to_openclaw.py \
    --cities "אשקלון" \
    --to "+972545899945" \
    --channel whatsapp

# Watch multiple cities
python ./scripts/sse_to_openclaw.py \
    --cities "אשקלון,תל אביב,באר שבע" \
    --to "+972545899945"
```

### 3. Or Use Cron (polling, not real-time)

If you prefer polling over a persistent SSE connection, use an OpenClaw cron job with MCP tools:

```bash
openclaw cron add \
  --name "ashkelon-alerts" \
  --every "30s" \
  --tz "Asia/Jerusalem" \
  --agent main \
  --session isolated \
  --to "+972545899945" \
  --channel whatsapp \
  --message 'Use the pikud-haoref MCP tool check_current_alerts. If any alert includes אשקלון, send me a WhatsApp with the alert details. If no alerts for אשקלון, reply with NO_REPLY.'
```

### Environment Variables for Bridge

| Variable | Default | Description |
|---|---|---|
| `SSE_URL` | `http://localhost:8002/api/alerts-stream` | SSE stream |
| `OPENCLAW_HOOK_URL` | `http://127.0.0.1:18789/hooks/agent` | OpenClaw webhook |
| `OPENCLAW_HOOK_TOKEN` | (required) | Webhook auth token |
| `WATCH_CITIES` | `אשקלון` | Comma-separated Hebrew city names |
| `DELIVER_TO` | (last chat) | Phone number or group JID |
| `DELIVER_CHANNEL` | `whatsapp` | Delivery channel |

## Persistent Service (LaunchAgent)

For always-on monitoring, install as a macOS LaunchAgent:

```bash
# Create plist (edit cities/phone/token as needed)
cat > ~/Library/LaunchAgents/ai.openclaw.pikud-haoref-bridge.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>ai.openclaw.pikud-haoref-bridge</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/sse_to_openclaw.py</string>
        <string>--cities</string>
        <string>אשקלון</string>
        <string>--to</string>
        <string>+972XXXXXXXXX</string>
        <string>--channel</string>
        <string>whatsapp</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>OPENCLAW_HOOK_TOKEN</key>
        <string>your-hook-token</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/pikud-haoref-bridge.out.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/pikud-haoref-bridge.err.log</string>
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
EOF

# Start it
launchctl load ~/Library/LaunchAgents/ai.openclaw.pikud-haoref-bridge.plist

# Check status
launchctl list | grep pikud
tail -f /tmp/pikud-haoref-bridge.err.log
```

## Important Notes

- City names should be in **Hebrew** for best matching (e.g., "תל אביב", not "Tel Aviv")
- The bridge script requires Python 3 with `httpx` installed (`pip3 install httpx`)
- The script uses `from __future__ import annotations` for Python 3.9 compatibility (macOS default)
- The MCP server subscribes to the FastAPI middleware via SSE for real-time alerts
- Historical data is stored in a local SQLite database
- The system polls the official Pikud HaOref API (oref.org.il) every 2 seconds

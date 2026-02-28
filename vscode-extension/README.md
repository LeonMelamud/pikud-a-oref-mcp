# 🚨 Pikud Haoref Emergency Alerts - VS Code Extension

Real-time Israeli emergency alerts directly in VS Code via SSE (Server-Sent Events).

Connects to the local Docker-deployed alert system — works out of the box with zero configuration.

## Features

- 📡 **Real-time SSE Connection** to Pikud HaOref alert stream (Docker)
- 🚨 **Live Alert Display** in VS Code Explorer sidebar
- 🔔 **Desktop Notifications** for new emergency alerts
- 🧪 **Test Alert Creation** directly from VS Code
- ⚙️ **Configurable Settings** for API endpoint and authentication
- 📊 **Connection Status** monitoring

## Quick Install

```bash
cd vscode-extension && npm install && npm run compile
npx @vscode/vsce package --allow-missing-repository
code --install-extension pikud-haoref-alerts-1.2.0.vsix --force
```

That's it — the extension connects to the production servers by default.

## Default Settings

| Setting | Default |
|---|---|
| **SSE URL** | `http://localhost:8002/api/alerts-stream` |
| **Server URL** | `http://localhost:8000` |
| **Notifications** | Enabled |

To override, go to VS Code Settings → search "Pikud Haoref".

## Live Services

| Service | URL |
|---|---|
| Alert API + SSE | `http://localhost:8000` |
| MCP Server | `http://localhost:8001/mcp` |
| SSE Relay | `http://localhost:8002` |

## Usage

### Starting Alert Monitoring
1. Open Command Palette (`Cmd+Shift+P`)
2. Type "Pikud Haoref: Start Alert Monitoring"
3. Extension will automatically connect to your SSE stream

### Viewing Alerts
- Check the **🚨 Emergency Alerts** panel in the Explorer sidebar
- Real-time alerts will appear as they're received
- Click on alerts to expand details

### Sending Test Alerts
1. Command Palette → "Pikud Haoref: Send Test Alert"
2. Or use the Makefile: `make test-alert`

## Commands

- `pikudHaoref.startAlerts` - Start monitoring alerts
- `pikudHaoref.stopAlerts` - Stop monitoring alerts  
- `pikudHaoref.testAlert` - Send a test alert

## Extension Structure

```
vscode-extension/
├── package.json          # Extension manifest
├── src/extension.ts      # Main extension code with SSE logic
├── tsconfig.json        # TypeScript configuration
├── .vscode/
│   ├── launch.json      # Debug configuration
│   └── tasks.json       # Build tasks
└── README.md           # This file
```

## How SSE Connection Works

The extension uses the Node.js `eventsource` library to:

1. **Connect** to the SSE Relay (`http://localhost:8002/api/alerts-stream`)
2. **Listen** for real-time alert events (no auth required for SSE relay)
3. **Parse** incoming JSON alert data
4. **Display** alerts in VS Code sidebar tree view
5. **Notify** user via desktop notifications
6. **Auto-reconnect** with exponential backoff (2s → 60s cap)

## Development

### Watch Mode
```bash
npm run watch  # Auto-compile on file changes
```

### Debugging
- Set breakpoints in `src/extension.ts`
- Press `F5` to start debugging session
- Check VS Code Developer Console for logs

### Testing SSE Connection
```bash
# Test your SSE endpoint directly
curl -N -H "X-API-Key: poha-test-key-2024-secure" \\
  http://localhost:8000/api/alerts-stream

# Send test alert
make test-alert
```

## Publishing

To package for distribution:

```bash
npm install -g vsce
vsce package
```

This creates a `.vsix` file you can install manually or publish to the marketplace.

## Architecture

```
Pikud HaOref API (oref.org.il)
        │
        ▼ polls every 2s
   Alert Poller (Docker)
        │
        ▼ SSE
   SSE Relay (Docker)
        │
        ▼ EventSource
   VS Code Extension
        │
        ▼
   Tree View + Desktop Notifications
```

## MCP Integration

Add to your VS Code `mcp.json` for LLM access to alert tools:

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

This gives your AI assistant tools: `check_current_alerts`, `get_alert_history`, `get_connection_status`, `get_alerts_by_city`, `get_alert_stats`.
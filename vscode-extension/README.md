# 🚨 Pikud Haoref Emergency Alerts - VS Code Extension

Real-time Israeli emergency alerts directly in VS Code via SSE (Server-Sent Events).

## Features

- 📡 **Real-time SSE Connection** to your Pikud Haoref alert stream
- 🚨 **Live Alert Display** in VS Code Explorer sidebar
- 🔔 **Visual Notifications** for new emergency alerts
- 🧪 **Test Alert Creation** directly from VS Code
- ⚙️ **Configurable Settings** for API endpoint and authentication
- 📊 **Connection Status** monitoring

## Installation & Setup

### 1. Install Dependencies
```bash
cd vscode-extension
npm install
```

### 2. Compile TypeScript
```bash
npm run compile
```

### 3. Test the Extension
- Press `F5` in VS Code to open Extension Development Host
- Or use `Ctrl+Shift+P` → "Developer: Reload Window"

### 4. Configure Settings
Go to VS Code Settings and search for "Pikud Haoref":

- **API URL**: `http://localhost:8000/api/alerts-stream`
- **API Key**: `poha-test-key-2024-secure`
- **Enable Notifications**: `true`

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

1. **Connect** to `http://localhost:8000/api/alerts-stream`
2. **Authenticate** using `X-API-Key` header
3. **Listen** for real-time alert events
4. **Parse** incoming JSON alert data
5. **Display** alerts in VS Code UI
6. **Notify** user of new emergencies

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
VS Code Extension ← SSE ← FastAPI ← Pikud Haoref API
     ↓
  Tree View + Notifications
```

The extension bridges real-time SSE streams with VS Code's extension API, providing emergency alerts directly in your development environment.
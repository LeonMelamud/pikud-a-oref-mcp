# Pikud Haoref Real-Time Alert System

![System Architecture](poha_sse_architecture.png)

A comprehensive middleware service and MCP server for accessing Israeli emergency alerts from the official Pikud Haoref (Israeli Home Front Command) API.

## Overview

This project provides **two ways** to access Israeli emergency alert data using a **publish-subscribe architecture**:

1. **FastAPI Middleware Service** - Single source polling with real-time SSE streaming
2. **MCP Server** - Event-driven subscriber for AI assistants (built with FastMCP)

The **FastAPI service** polls the official Pikud Haoref API at `https://www.oref.org.il/WarningMessages/alert/alerts.json` and publishes alerts via Server-Sent Events. The **MCP server** subscribes to this stream, creating an efficient pub-sub system that eliminates duplicate API calls while providing real-time access to emergency alerts including rocket alerts, aerial intrusions, earthquakes, and other emergencies.

## Features

### FastAPI Service Features
- **Single-source polling** of emergency alerts (eliminates duplicate API calls)
- **Real-time SSE streaming** via public webhook endpoint
- **API key authentication** for client endpoints and **geo-restriction** to Israel
- **Rate limiting** (5 requests per minute per IP)
- **Docker support** for easy deployment
- **Comprehensive testing** suite

### MCP Server Features
- **Event-driven SSE client** - Subscribes to FastAPI webhook for real-time alerts
- **3 Tools** for AI assistants:
  - `check_current_alerts` - Check for active alerts from subscribed stream
  - `get_alert_history` - Get recent alerts with filtering (limit: 1-50, region filter, **intelligent city matching**)
  - `get_connection_status` - Check SSE subscription connection status
- **2 Resources**:
  - `poha://alerts/recent` - JSON data of recent alerts
  - `poha://alerts/current-status` - System status information
- **Smart City Filtering**:
  - **Exact substring matching** - Find alerts by city name (e.g., "תל אביב" matches all Tel Aviv areas)
  - **Fuzzy matching** - Intelligent matching with threshold 60 for partial/similar names
  - **Multi-city support** - Search multiple cities simultaneously
  - **Hebrew city names** - Optimized for Hebrew location names from the API
- **Built with FastMCP** following proven patterns
- **Automatic reconnection** and error handling for SSE connections

## Quick Start

### Option 1: FastAPI Service (Requires API Key)

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Configure environment** (create `.env` file):
```env
API_KEY=your-secure-api-key-here  # Required for FastAPI SSE endpoints
GEOIP_DB_PATH=/path/to/GeoLite2-Country.mmdb  # Optional for geo-restriction
```

3. **Run the service:**
```bash
# Development
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

# Production with Docker
docker build -t poha-alert-system .
docker run -d -p 8000:8000 -e API_KEY=your-key --name poha-container poha-alert-system
```

4. **Connect to the stream:**
```bash
curl -H "X-API-Key: your-key" http://localhost:8000/api/alerts-stream
```

### Option 2: MCP Server (No API Key Required)

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Configure your MCP client** (Claude Desktop, etc.):

For **Claude Desktop**, add to `~/Library/Application Support/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "poha-alerts": {
      "type": "http",
      "url": "http://127.0.0.1:8001/mcp"
    }
  }
}
```

**Cursor IDE**, add to `.cursor/mcp.json` in your project:
```json
{
  "mcpServers": {
    "poha-alerts": {
      "type": "http", 
      "url": "http://127.0.0.1:8001/mcp"
    }
  }
}
```

3. **Start the services:**
```bash
# Start all services (FastAPI + MCP server)
make up

# Or start individually
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000  # FastAPI
python -m src.core.mcp_server  # MCP Server
```

4. **Start using** - The server will be available as "Pikud Haoref Alert System" in your MCP client via HTTP transport.

## API Endpoints (FastAPI Service)

### `GET /`
Basic status endpoint.

### `GET /api/alerts-stream`
**Headers:** `X-API-Key: your-key`

Server-Sent Events stream for real-time alerts (authenticated endpoint). Returns:
- `event: new_alert` - When a new alert is detected
- `: keep-alive` - Periodic keep-alive messages

### `GET /api/webhook/alerts`
**Headers:** `X-API-Key: your-key`

Internal SSE webhook endpoint for services like the MCP server. Streams the same alert data as the client endpoint and requires the same API key authentication for security. Designed for server-to-server communication.

Example response for both endpoints:
```
event: new_alert
data: {"id": "12345", "data": ["Tel Aviv", "Ramat Gan"], "cat": "1", "title": "Rocket Alert", "desc": "Immediate shelter required"}

: keep-alive
```

## MCP Tools Usage

### Check Current Alerts
```
Use the check_current_alerts tool to see if there are any active emergency alerts from the subscribed SSE stream.
```

### Get Alert History
```
Use get_alert_history with limit=5 to get the 5 most recent alerts from the API.
Use get_alert_history with region="Tel Aviv" to get alerts for a specific region.
Use get_alert_history with cities=["תל אביב"] to get alerts for Tel Aviv (all areas).
Use get_alert_history with cities=["תל אביב", "חיפה"] to get alerts for multiple cities.
Use get_alert_history with cities=["תל אביב מרכז"] for specific areas with fuzzy matching.
```

**City Filtering Examples:**
- `cities=["תל אביב"]` - Finds all Tel Aviv areas (דרום העיר ויפו, מזרח, מרכז העיר, עבר הירקון)
- `cities=["חיפה"]` - Finds all Haifa-related alerts
- `cities=["תל אביב", "חיפה", "ירושלים"]` - Multiple cities simultaneously
- `cities=["תל אביב מרכז"]` - Fuzzy matches to "תל אביב - מרכז העיר"
- `cities=["all"]` - No city filtering (shows all alerts)

### Check Connection Status
```
Use get_connection_status to verify the SSE subscription connection and see system health.
```

## Architecture

The system uses a **publish-subscribe architecture** with the following components:

1. **Pikud Haoref API** - External data source (government emergency alerts)
2. **FastAPI Middleware** - Single source polling + SSE publisher (polls every 2 seconds)
3. **MCP Server** - SSE subscriber + tool provider for AI assistants
4. **Client Applications** - Web frontends, mobile apps, AI assistants, or other services

```
Pikud Haoref API ←→ [Single Poller] ←→ FastAPI Middleware ←→ [SSE Stream] ←→ MCP Server → AI Assistants
                                              ↓
                                          [SSE Stream] ←→ Web Clients
```

**Key Benefits:**
- ✅ **50% reduction** in API calls (single polling source)
- ✅ **Real-time propagation** of alerts via SSE
- ✅ **Event-driven architecture** for better scalability
- ✅ **Automatic reconnection** for robust SSE connections

**Visual Diagram:** Run `python diagram.py` to generate `poha_sse_architecture.png` showing the complete system architecture.

## Security Features

### API Key Authentication (Required for All Endpoints)
**Important:** API key authentication is **required for both SSE endpoints** for security.

- **Both SSE endpoints** require API key authentication via `X-API-Key` header
- **MCP server** connects with authentication to the internal webhook endpoint
- **Same API key** used for both client and internal service authentication

### Geo-Restriction (Optional)
Configure `GEOIP_DB_PATH` to restrict access to Israeli IP addresses only:
1. Sign up at [MaxMind](https://www.maxmind.com/en/geolite2/signup)
2. Download `GeoLite2-Country.mmdb`
3. Set `GEOIP_DB_PATH` in your `.env` file

### Rate Limiting
- **Limit:** 5 requests per minute per IP address
- **Response:** HTTP 429 when exceeded

## Development

### Project Structure
```
├── main.py              # FastAPI application entry point
├── mcp_server.py        # MCP server implementation
├── polling.py           # Core API polling logic
├── sse.py              # Server-Sent Events implementation
├── security.py         # Authentication and geo-restriction
├── alert_queue.py      # Alert queue management
├── state.py            # Application state management
├── geolocation.py      # Geo-IP functionality
├── conftest.py         # Test configuration
├── pytest.ini         # Test settings
├── tests/              # Comprehensive test suite
├── diagram.py          # Architecture diagram generator
├── mcp.json           # MCP server configuration
├── Dockerfile         # Docker configuration
├── .gitignore         # Git ignore rules
└── requirements.txt   # Python dependencies
```

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_api.py -v

# Run with coverage
pytest --cov=. tests/
```

### Dependencies
- **Core:** `fastapi`, `uvicorn`, `httpx`, `python-dotenv`
- **Security:** `geoip2`, `slowapi`
- **MCP:** `fastmcp`, `fuzzywuzzy`, `python-Levenshtein`
- **Testing:** `pytest`, `pytest-asyncio`, `respx`

## Docker Deployment

### Build Image
```bash
docker build -t poha-alert-system .
```

### Run Container
```bash
# Basic run
docker run -d -p 8000:8000 -e API_KEY=your-key poha-alert-system

# With environment file
docker run -d -p 8000:8000 --env-file .env poha-alert-system

# With geo-restriction
docker run -d -p 8000:8000 --env-file .env -v /path/to/GeoLite2-Country.mmdb:/app/geo.mmdb poha-alert-system
```

## Data Source

- **API:** `https://www.oref.org.il/WarningMessages/alert/alerts.json`
- **Provider:** Israeli Government (Pikud Haoref - Home Front Command)
- **Coverage:** All emergency alerts in Israel
- **Update Frequency:** Every 2 seconds
- **Data Types:** Rocket alerts, aerial intrusions, earthquakes, emergency announcements

## Use Cases

- **Emergency Response Teams** - Real-time alert monitoring
- **News Organizations** - Breaking news automation
- **Israeli Residents** - Personal safety notifications
- **Researchers** - Emergency pattern analysis
- **AI Assistants** - Contextual emergency information
- **Mobile Apps** - Push notification services
- **Smart Home Systems** - Automated responses to alerts

## Configuration Examples

### FastAPI Service `.env` File
```env
# Required for FastAPI SSE endpoints
API_KEY=poha-test-key-2024-secure

# Optional - Enable geo-restriction
GEOIP_DB_PATH=/path/to/GeoLite2-Country.mmdb
```

### MCP Configuration for Various Clients

**Claude Desktop:**
```json
{
  "mcpServers": {
    "poha-alerts": {
      "command": "python",
      "args": ["-m", "src.core.mcp_server"],
      "cwd": "/path/to/poha-real-time-alert-system",
      "env": {
        "WEBHOOK_URL": "http://localhost:8000/api/webhook/alerts",
        "API_KEY": "poha-test-key-2024-secure"
      }
    }
  }
}
```

**Generic MCP Client:**
```json
{
  "mcpServers": {
    "poha-alerts": {
      "command": "python",
      "args": ["-m", "src.core.mcp_server"],
      "cwd": "/path/to/poha-real-time-alert-system",
      "env": {
        "PYTHONPATH": "/path/to/poha-real-time-alert-system",
        "WEBHOOK_URL": "http://localhost:8000/api/webhook/alerts",
        "API_KEY": "poha-test-key-2024-secure"
      }
    }
  }
}
```

## Troubleshooting

### Common Issues

1. **"API key is missing"** - Ensure `X-API-Key` header is set for both client and webhook endpoints
2. **MCP connection fails** - Check:
   - Python path in MCP config (use full venv path if needed: `/path/to/venv/bin/python`)
   - API_KEY environment variable is set correctly
   - FastAPI service is running on localhost:8000
   - Restart your MCP client (Cursor, Claude Desktop, etc.)
   - Alternative: Use the provided `start_mcp.sh` script as the command
3. **Connection timeouts** - Check your internet connection and firewall settings
4. **Geo-restriction errors** - Verify `GeoLite2-Country.mmdb` path and file permissions
5. **SSE authentication fails** - Verify API key matches between FastAPI service and MCP config
6. **City filtering not working** - 
   - Use Hebrew city names (e.g., "תל אביב" not "Tel Aviv")
   - Check exact city names in alert history first: `cities=["all"]`
   - Try broader names for fuzzy matching: "תל אביב" instead of "תל אביב - מרכז העיר"
7. **ModuleNotFoundError: No module named 'fuzzywuzzy'** - 
   - Rebuild Docker containers: `docker-compose build --no-cache`
   - Install dependencies: `pip install fuzzywuzzy python-Levenshtein`

### Logs
Both services provide detailed logging. Check logs for:
- API polling status
- SSE client connections and authentication
- MCP server webhook connection status
- Error messages
- Security events

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

This project accesses public emergency alert data from the Israeli government. The service is designed for legitimate emergency preparedness and news reporting purposes.

## Disclaimer

This service provides access to official Israeli emergency alert data but is not affiliated with or endorsed by the Israeli government or Pikud Haoref. Always follow official emergency procedures and consult official sources for critical safety information.
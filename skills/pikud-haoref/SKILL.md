# Pikud HaOref Alert System — OpenClaw Skill

Use when the user asks about **Israeli emergency alerts**, missile alerts, Pikud HaOref, or "are there alerts in [city]?".

## MCP Server

This skill relies on a Pikud HaOref MCP server. Configure it in `openclaw.json`:

```json
{
  "mcpServers": {
    "pikud-haoref": {
      "url": "http://127.0.0.1:8001/mcp"
    }
  }
}
```

For Railway deployment, use the public URL instead:
```json
{
  "mcpServers": {
    "pikud-haoref": {
      "url": "https://<your-railway-domain>/mcp"
    }
  }
}
```

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

## Important Notes

- City names should be in **Hebrew** for best matching (e.g., "תל אביב", not "Tel Aviv")
- The MCP server subscribes to the FastAPI middleware via SSE for real-time alerts
- Historical data is stored in a local SQLite database
- The system polls the official Pikud HaOref API (oref.org.il) every 2 seconds

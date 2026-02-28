#!/usr/bin/env python3
"""
MCP Server for Pikud Haoref (Israeli Emergency Alert System)

This MCP server provides tools and resources for accessing Israeli emergency alerts
by subscribing to the FastAPI webhook service via Server-Sent Events (SSE).
"""
import asyncio
import json
import logging
import sys
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastmcp import FastMCP
import httpx
from fuzzywuzzy import fuzz, process

# Import our existing polling functionality for reference
from ..services.polling import POHA_API_URL, REQUEST_HEADERS
from ..db.database import init_db, get_alerts_by_city as db_get_alerts_by_city, get_recent_alerts, get_alert_stats

# Define the history URL here as it's no longer in polling.py
POHA_HISTORY_API_URL = "https://www.oref.org.il/WarningMessages/alert/History/AlertsHistory.json"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Log startup information
logger.info("=== Pikud Haoref Alert MCP Server Starting ===")
logger.info(f"Python version: {sys.version}")
logger.info(f"Working directory: {os.getcwd()}")
logger.info(f"API Endpoint: {POHA_API_URL}")

# Store the last received alert in memory for the resource
last_alert: Optional[Dict[str, Any]] = None

# Global in-memory cache for alert history
cached_all_alerts: Optional[List[Dict[str, Any]]] = None
last_fetch_time: Optional[datetime] = None
CACHE_DURATION = timedelta(hours=1) # Cache for 1 hour

# SSE Client Configuration
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://localhost:8000/api/webhook/alerts")
API_KEY = os.getenv("API_KEY", "dev-secret-key")

class AlertSubscriber:
    """SSE client for subscribing to alerts from the FastAPI webhook"""
    
    def __init__(self, webhook_url: str, api_key: str):
        self.webhook_url = webhook_url
        self.api_key = api_key
        self.is_connected = False
        self.subscription_task = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        
    async def subscribe(self):
        """Subscribe to SSE webhook and process events"""
        while self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                logger.info(f"🔗 Connecting to SSE webhook: {self.webhook_url}")
                headers = {"X-API-Key": self.api_key}
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream("GET", self.webhook_url, headers=headers) as response:
                        if response.status_code == 200:
                            self.is_connected = True
                            self.reconnect_attempts = 0
                            logger.info("✅ Successfully connected to SSE webhook")
                            
                            async for line in response.aiter_lines():
                                if line.startswith("data: "):
                                    try:
                                        event_data = line[6:]  # Remove "data: " prefix
                                        
                                        # Handle keep-alive messages
                                        if event_data.strip() == "keep-alive":
                                            continue
                                            
                                        # Try to parse as JSON
                                        alert_data = json.loads(event_data)
                                        await self.process_alert(alert_data)
                                        
                                    except json.JSONDecodeError:
                                        # Non-JSON data (like keep-alive), skip
                                        continue
                                    except Exception as e:
                                        logger.error(f"Error processing SSE event: {e}")
                        else:
                            logger.error(f"SSE connection failed with status {response.status_code}")
                            self.is_connected = False
                            break
                            
            except Exception as e:
                self.is_connected = False
                self.reconnect_attempts += 1
                logger.error(f"SSE connection error (attempt {self.reconnect_attempts}): {e}")
                if self.reconnect_attempts < self.max_reconnect_attempts:
                    await asyncio.sleep(5)  # Wait 5 seconds before reconnecting
                else:
                    logger.error("Max reconnection attempts reached. SSE client disabled.")
                    break
    
    async def process_alert(self, alert_data: Dict[str, Any]):
        """Process incoming alert from SSE stream"""
        global last_alert
        if not alert_data or not isinstance(alert_data, dict):
            return
            
        # Add received timestamp and store as the last alert
        last_alert = {
            **alert_data,
            "received_at": datetime.now().isoformat()
        }
        
        logger.warning(f"🚨 NEW ALERT RECEIVED via SSE: {last_alert.get('id')}")
        
        
    def start_subscription(self):
        """Start the SSE subscription in the background"""
        if self.subscription_task is None or self.subscription_task.done():
            self.subscription_task = asyncio.create_task(self.subscribe())
            logger.info("🚀 Started SSE subscription task")

# Global subscriber instance
alert_subscriber = AlertSubscriber(WEBHOOK_URL, API_KEY)


# Initialize MCP server
mcp = FastMCP(
    name="Pikud Haoref Alert System",
    instructions="""
    A comprehensive Model Context Protocol (MCP) server for accessing Israeli emergency alerts
    via real-time subscription to the FastAPI middleware service.
    
    This server provides:
    - Real-time checking of current active emergency alerts in Israel
    - Alert history retrieval with optional region filtering
    - Live subscription to emergency alert streams via Server-Sent Events (SSE)
    - Comprehensive alert information including areas, categories, and descriptions
    
    Architecture: This server subscribes to a FastAPI middleware service that polls the official
    Pikud Haoref API, providing efficient real-time alert distribution via SSE webhooks.
    
    Data source: Official Pikud Haoref API (oref.org.il) via FastAPI middleware
    Coverage: All emergency alerts in Israel including rocket alerts, aerial intrusions, earthquakes, etc.
    
    Available tools:
    - check_current_alerts: Check for current active emergency alerts (from subscribed stream)
    - get_alert_history: Get recent alert history with optional filtering by region
    - get_connection_status: Check SSE subscription connection status
    
    Perfect for: Emergency response teams, news organizations, residents of Israel, 
    researchers studying emergency patterns, and anyone needing real-time Israeli alert data.
    """
)

@mcp.tool()
async def check_current_alerts() -> str:
    """Check for current active emergency alerts from subscribed stream"""
    logger.info("🔍 Checking for current active alerts from SSE stream")
    
    # Start subscription if not already running
    alert_subscriber.start_subscription()
    await asyncio.sleep(1) # Give it a moment to connect
    
    # Check connection status FIRST
    if not alert_subscriber.is_connected:
        return "❌ Cannot check for alerts: Not connected to the SSE alert stream."
    
    if not last_alert:
        return "✅ No alerts have been received via the SSE stream yet."
    
    alert_text = f"🚨 **LAST RECEIVED ALERT** (via SSE subscription)\n\n"
    alert_text += f"**Alert ID:** {last_alert.get('id', 'N/A')}\n"
    alert_text += f"**Areas:** {', '.join(last_alert.get('cities', []))}\n"
    alert_text += f"**Category:** {last_alert.get('type', 'N/A')}\n"
    alert_text += f"**Instructions:** {last_alert.get('instructions', 'N/A')}\n"
    alert_text += f"**Received:** {last_alert.get('received_at', 'N/A')}\n"
    
    return alert_text

@mcp.tool()
async def get_alert_history(limit: int = 10, region: Optional[str] = None, cities: Optional[List[str]] = None) -> str:
    """
    Get recent alert history by fetching directly from the Pikud Haoref API.
    
    Args:
        limit: Maximum number of alerts to return (1-50, default: 10)
        region: Filter alerts by region/area name (optional)
        cities: Optional list of city names to filter alerts by. **IMPORTANT: Please provide city names in Hebrew** (e.g., "תל אביב"). If "all" is provided, no city filtering will occur.
    """
    logger.info(f"📋 Getting alert history directly from API (limit: {limit}, region: {region}, cities: {cities})")
    
    global cached_all_alerts, last_fetch_time

    try:
        # Check cache first
        if cached_all_alerts and last_fetch_time and (datetime.now() - last_fetch_time) < CACHE_DURATION:
            logger.info("📊 Using cached alert history.")
            all_alerts = cached_all_alerts
        else:
            logger.info("🔗 Cache expired or not present. Fetching alert history from API.")
            logger.info(f"🔗 Making request to: {POHA_HISTORY_API_URL}")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(POHA_HISTORY_API_URL, headers=REQUEST_HEADERS)
                
                # Log response details for debugging
                logger.info(f"📊 Response status: {response.status_code}")
                logger.info(f"📊 Response headers: {dict(response.headers)}")
                logger.info(f"📊 Response encoding: {response.encoding}")
                
                response.raise_for_status()
                
                # The API returns a stream of JSON objects, not a valid array.
                # We need to manually construct a valid JSON array string.
                raw_text = await response.aread()
                logger.info(f"📊 Raw response size: {len(raw_text)} bytes")
                logger.info(f"📊 Raw response content type: {response.headers.get('content-type', 'unknown')}")
                
                decoded_text = raw_text.decode('utf-8-sig')
                logger.info(f"📊 Decoded text size: {len(decoded_text)} characters")
                logger.info(f"📊 Raw response preview (first 500 chars): {decoded_text[:500]}")
                
                json_text = decoded_text.strip()
                logger.info(f"📊 Stripped text size: {len(json_text)} characters")

                if not json_text:
                    all_alerts = []
                else:
                    try:
                        logger.info(f"📊 Attempting to parse JSON directly...")
                        # Try parsing as-is first (API might return valid JSON array)
                        all_alerts = json.loads(json_text)
                        logger.info(f"✅ Successfully parsed JSON directly - found {len(all_alerts)} alerts")
                        logger.info(f"📊 Sample alert structure: {all_alerts[0] if all_alerts else 'No alerts'}")
                    except json.JSONDecodeError as e:
                        logger.info(f"📊 Direct parsing failed, trying transformation...")
                        logger.info(f"📊 Processing JSON text transformation...")
                        # Fallback: Wrap the text in brackets to form a valid JSON array string
                        # and replace the object separators.
                        json_array_string = f"[{json_text.replace('}{', '},{')}]"
                        logger.info(f"📊 Transformed JSON array size: {len(json_array_string)} characters")
                        logger.info(f"📊 Transformed JSON preview (first 500 chars): {json_array_string[:500]}")
                        
                        try:
                            logger.info(f"📊 Attempting to parse transformed JSON...")
                            all_alerts = json.loads(json_array_string)
                            logger.info(f"✅ Successfully parsed transformed JSON - found {len(all_alerts)} alerts")
                            logger.debug(f"📊 All alerts (transformed) type: {type(all_alerts)}, first 3 items: {all_alerts[:3] if isinstance(all_alerts, list) else all_alerts}")
                            logger.info(f"📊 Sample alert structure: {all_alerts[0] if all_alerts else 'No alerts'}")
                        except json.JSONDecodeError as e2:
                            logger.error(f"❌ Failed to parse alert history JSON: {e2}")
                            logger.error(f"❌ JSON error position: {e2.pos if hasattr(e2, 'pos') else 'unknown'}")
                            logger.error(f"❌ Problematic JSON string: {json_array_string[:500]}") # Log first 500 chars
                            logger.error(f"❌ Original text had brackets? Start: '{json_text[:50]}' End: '{json_text[-50:]}'")
                            return "❌ Error: Could not parse the alert history data from the API."
            
            cached_all_alerts = all_alerts
            last_fetch_time = datetime.now()

        if not all_alerts:
            return "No historical alerts found from the API."

        # If cities are specified and limit is default, set limit to max to show all filtered alerts
        if cities and limit == 10:
            logger.info("📊 Cities filter provided, setting limit to max (50) to show all relevant alerts.")
            limit = 50 # Set to max allowed by the API to retrieve all filtered results

        # Validate limit
        limit = max(1, min(50, limit))
        
        final_filtered_alerts = all_alerts
        
        if region:
            valid_alerts_by_region = []
            for alert in all_alerts:
                if isinstance(alert, dict):
                    if region.lower() in str(alert.get('data', '')).lower():
                        valid_alerts_by_region.append(alert)
            final_filtered_alerts = valid_alerts_by_region

        # --- First Pass: Exact City Matching ---
        exact_match_found = False
        if cities and not ("all" in [c.lower() for c in cities]):
            logger.info(f"📊 Applying exact city filter for cities: {cities}")
            exact_city_filtered_alerts = []
            for alert in final_filtered_alerts:
                if isinstance(alert, dict):
                    alert_data_str = str(alert.get('data', '')).lower()
                    if isinstance(alert.get('data'), list):
                        # For list of cities, check if any exact city matches
                        if any(c.lower() in [city.lower() for city in cities] for c in alert.get('data')):
                            exact_city_filtered_alerts.append(alert)
                    elif isinstance(alert.get('data'), str):
                        # For single city string, check if any city is contained in the alert data
                        if any(city.lower() in alert_data_str for city in cities):
                            exact_city_filtered_alerts.append(alert)
            final_filtered_alerts = exact_city_filtered_alerts
            if final_filtered_alerts: # If exact matches found, set flag
                exact_match_found = True
        
        # --- Second Pass: Fuzzy City Matching (if no exact matches and cities were provided) ---
        if cities and not exact_match_found and not ("all" in [c.lower() for c in cities]):
            logger.info(f"📊 No exact matches found. Trying fuzzy city filter for cities: {cities}")
            fuzzy_city_filtered_alerts = []
            FUZZY_THRESHOLD = 60 # Lowered for better matching
            matched_cities = set()  # Track which cities we actually matched

            for alert in all_alerts: # Re-filter from all_alerts to ensure fuzzy doesn't miss anything due to prior exact filtering
                if isinstance(alert, dict):
                    alert_data_str = str(alert.get('data', ''))
                    
                    # Check fuzzy match for each requested city against alert data
                    is_fuzzy_match = False
                    for city_name in cities:
                        fuzzy_score = fuzz.partial_ratio(city_name.lower(), alert_data_str.lower())
                        if fuzzy_score >= FUZZY_THRESHOLD:
                            is_fuzzy_match = True
                            matched_cities.add(city_name)
                            logger.debug(f"📊 Fuzzy match: '{city_name}' -> '{alert_data_str}' (score: {fuzzy_score})")
                            break
                    
                    if is_fuzzy_match:
                        fuzzy_city_filtered_alerts.append(alert)
            
            final_filtered_alerts = fuzzy_city_filtered_alerts
            logger.info(f"📊 Fuzzy matching found {len(fuzzy_city_filtered_alerts)} alerts for cities: {list(matched_cities)}")
            
            if region:
                # Reapply region filter after fuzzy match if region was specified
                region_re_filtered_alerts = []
                for alert in final_filtered_alerts:
                    if isinstance(alert, dict):
                        if region.lower() in str(alert.get('data', '')).lower():
                            region_re_filtered_alerts.append(alert)
                final_filtered_alerts = region_re_filtered_alerts
        else:
            matched_cities = set()  # Initialize for non-fuzzy cases
            
        limited_alerts = final_filtered_alerts[:limit]
        
        if not limited_alerts:
            filter_text = f" matching region '{region}'" if region else ""
            city_filter_status = "" # Default to empty
            if cities and not ("all" in [c.lower() for c in cities]):
                if exact_match_found: # Should not happen if not limited alerts, but for safety
                    city_filter_status = f" (exact match for {cities})"
                elif not exact_match_found and cities:
                    if matched_cities:
                        city_filter_status = f" (fuzzy match for {list(matched_cities)}, threshold {FUZZY_THRESHOLD})"
                    else:
                        city_filter_status = f" (no fuzzy matches found for {cities}, threshold {FUZZY_THRESHOLD})"

            logger.info(f"📋 No historical alerts found{filter_text}{city_filter_status}")
            return f"No historical alerts found{filter_text}{city_filter_status} from the API."
        
        # Add filter info to the header
        filter_info = ""
        if cities and not ("all" in [c.lower() for c in cities]):
            if exact_match_found:
                filter_info = f" (exact match for {cities})"
            elif matched_cities:
                filter_info = f" (fuzzy match for {list(matched_cities)})"
        if region:
            filter_info += f" in region '{region}'"
            
        history_text = f"📋 **Recent Alert History from API**{filter_info} (showing {len(limited_alerts)} alerts)\n\n"
        history_text += "| Areas | Alert Time |\n"
        history_text += "|---|---|\n"
        
        for i, alert in enumerate(limited_alerts, 1):
            logger.debug(f"📊 Processing alert {i}. Type: {type(alert)}, Content: {alert}")
            # Ensure alert is a dictionary
            if not isinstance(alert, dict):
                logger.warning(f"📊 Alert {i} is not a dict: {type(alert)} - {alert}")
                continue
                
            # History API has a different structure for city data
            city_data = alert.get('data', '')
            if isinstance(city_data, str):
                cities = [city_data] if city_data else []
            elif isinstance(city_data, list):
                cities = city_data
            else:
                cities = []

            areas_str = ', '.join(cities)
            alert_time_str = alert.get('alertDate', 'N/A')
            
            history_text += f"| {areas_str} | {alert_time_str} |\n"
        
        logger.info(f"📋 Returned {len(limited_alerts)} alerts from history API")
        return history_text
        
    except httpx.RequestError as e:
        logger.error(f"❌ Error fetching alert history from API: {e}")
        return f"❌ A network error occurred while fetching alert history: {str(e)}"
    except Exception as e:
        logger.error(f"❌ Error processing alert history: {e}")
        return f"❌ An unexpected error occurred while retrieving alert history: {str(e)}"

logger.info("✅ get_alert_history tool defined")

@mcp.tool()
async def get_connection_status() -> str:
    """
    Get the current status of the SSE subscription connection.
    """
    logger.info("📊 Checking SSE connection status")
    
    # Ensure subscription is active to report on it
    alert_subscriber.start_subscription()
    
    status_text = "📊 **SSE Subscription Status**\n\n"
    status_text += f"**Connection Status:** {'✅ Connected' if alert_subscriber.is_connected else '❌ Disconnected'}\n"
    status_text += f"**Webhook URL:** {alert_subscriber.webhook_url}\n"
    status_text += f"**Reconnection Attempts:** {alert_subscriber.reconnect_attempts}/{alert_subscriber.max_reconnect_attempts}\n"
    
    if last_alert:
        status_text += f"**Last Alert Received:** {last_alert.get('received_at', 'N/A')}\n"
        status_text += f"**Last Alert ID:** {last_alert.get('id', 'N/A')}\n"
    else:
        status_text += f"**Last Alert Received:** No alerts received yet\n"
    
    status_text += f"**Check Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    
    return status_text

@mcp.resource("poha://alerts/current-status")
async def get_current_status() -> str:
    """Get current status of the alert monitoring system"""
    logger.info("📊 Providing system status resource")
    return json.dumps({
        "status": "active",
        "webhook_url": WEBHOOK_URL,
        "sse_connected": alert_subscriber.is_connected,
        "last_alert_received_at": last_alert.get("received_at") if last_alert else None,
        "reconnect_attempts": alert_subscriber.reconnect_attempts,
        "subscription_active": alert_subscriber.subscription_task is not None and not alert_subscriber.subscription_task.done(),
        "timestamp": datetime.now().isoformat(),
        "server_name": "Pikud Haoref Alert MCP Server (SSE Client)",
        "version": "2.0.0"
    }, indent=2)


@mcp.tool()
async def get_city_alerts(city: str, limit: int = 20) -> str:
    """
    Get alert history for a specific city from the local SQLite database.

    Args:
        city: City name in Hebrew (e.g., "תל אביב - יפו")
        limit: Maximum number of alerts to return (1-100, default: 20)
    """
    logger.info(f"🔍 Querying SQLite for alerts in city: {city}")
    try:
        await init_db()
        alerts = await db_get_alerts_by_city(city, limit=min(max(1, limit), 100))
    except Exception as e:
        logger.error(f"Error querying city alerts: {e}")
        return f"❌ Error querying alerts for {city}: {e}"

    if not alerts:
        return f"No alerts found for city: {city}"

    text = f"📋 **Alert History for {city}** (showing {len(alerts)} alerts)\n\n"
    text += "| Areas | Time |\n|---|---|\n"
    for a in alerts:
        areas = ", ".join(a.get("data", []))
        text += f"| {areas} | {a.get('timestamp', 'N/A')} |\n"
    return text


@mcp.tool()
async def get_db_stats() -> str:
    """Get statistics about the local alert database."""
    logger.info("📊 Querying database statistics")
    try:
        await init_db()
        stats = await get_alert_stats()
    except Exception as e:
        logger.error(f"Error querying stats: {e}")
        return f"❌ Error: {e}"

    text = f"📊 **Alert Database Statistics**\n\n"
    text += f"**Total Alerts:** {stats['total_alerts']}\n"
    text += f"**Total City Entries:** {stats['total_city_entries']}\n\n"
    if stats["top_cities"]:
        text += "**Top Cities:**\n"
        for c in stats["top_cities"]:
            text += f"- {c['city']}: {c['count']} alerts\n"
    return text



from starlette.requests import Request
from starlette.responses import JSONResponse

@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "mcp-tools"})


if __name__ == "__main__":
    port = int(os.getenv("PORT", os.getenv("MCP_PORT", "8001")))
    logger.info("🚀 Starting Pikud Haoref Alert MCP Server (HTTP Transport)")
    logger.info(f"🔗 Will connect to SSE webhook: {WEBHOOK_URL}")
    logger.info(f"🌐 Listening on port: {port}")

    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
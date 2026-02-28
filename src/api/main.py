import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from dotenv import load_dotenv
# Rate limiting imports disabled (not needed for emergency alerts)
# from slowapi.errors import RateLimitExceeded  
# from slowapi.middleware import SlowAPIMiddleware
from pydantic import BaseModel
from typing import List, Optional

# Local imports - must be direct, not relative
from ..services.polling import poll_for_alerts
from ..utils.security import geo_ip_middleware, get_api_key, limiter
from ..services.sse import alert_event_generator
from ..core.state import app_state
from ..core.alert_queue import alert_queue
from ..db.database import init_db, close_db, save_alert, get_alerts_by_city, get_recent_alerts, get_alert_stats

# Load environment variables from .env file at the start
load_dotenv()

# Configure logging for the application
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Alert category mappings with Hebrew and English descriptions
ALERT_CATEGORIES = {
    "1": {
        "type": "missiles",
        "title_he": "התרעת צבע אדום",
        "title_en": "Red Alert - Missile Threat",
        "description_he": "היכנסו למרחב המוגן, סגרו דלתות וחלונות",
        "description_en": "Enter protected space, close doors and windows",
        "instructions_he": "היכנסו למבנה, נעלו את הדלתות וסגרו את החלונות",
        "instructions_en": "Enter a building, lock the doors and close the windows"
    },
    "2": {
        "type": "radiologicalEvent", 
        "title_he": "אירוע רדיולוגי",
        "title_en": "Radiological Event",
        "description_he": "התרחקו מהאזור, הישארו במבנה סגור",
        "description_en": "Stay away from the area, remain in a closed building",
        "instructions_he": "התרחקו מהאזור, הישארו במבנה סגור",
        "instructions_en": "Stay away from the area, remain in a closed building"
    },
    "3": {
        "type": "earthQuake",
        "title_he": "רעידת אדמה", 
        "title_en": "Earthquake",
        "description_he": "צאו למקום פתוח, הרחק ממבנים",
        "description_en": "Go to an open area, away from buildings",
        "instructions_he": "צאו למקום פתוח, הרחק ממבנים",
        "instructions_en": "Go to an open area, away from buildings"
    },
    "4": {
        "type": "tsunami",
        "title_he": "צונאמי",
        "title_en": "Tsunami", 
        "description_he": "התרחקו מקו החוף, עלו למקום גבוה",
        "description_en": "Stay away from the coastline, go to high ground",
        "instructions_he": "התרחקו מקו החוף, עלו למקום גבוה",
        "instructions_en": "Stay away from the coastline, go to high ground"
    },
    "5": {
        "type": "hostileAircraftIntrusion",
        "title_he": "חדירת כלי טיס עוין",
        "title_en": "Hostile Aircraft Intrusion",
        "description_he": "היכנסו למבנה, הישארו רחוק מחלונות",
        "description_en": "Enter a building, stay away from windows",
        "instructions_he": "היכנסו למבנה, הישארו רחוק מחלונות",
        "instructions_en": "Enter a building, stay away from windows"
    },
    "6": {
        "type": "hazardousMaterials",
        "title_he": "חומרים מסוכנים",
        "title_en": "Hazardous Materials",
        "description_he": "סגרו חלונות ודלתות, כבו מזגנים",
        "description_en": "Close windows and doors, turn off air conditioning",
        "instructions_he": "סגרו חלונות ודלתות, כבו מזגנים",
        "instructions_en": "Close windows and doors, turn off air conditioning"
    },
    "7": {
        "type": "terroristInfiltration",
        "title_he": "חדירת מחבלים",
        "title_en": "Terrorist Infiltration",
        "description_he": "נעלו דלתות, הימנעו מיציאה",
        "description_en": "Lock doors, avoid going outside",
        "instructions_he": "נעלו דלתות, הימנעו מיציאה", 
        "instructions_en": "Lock doors, avoid going outside"
    },
    "101": {
        "type": "missilesDrill",
        "title_he": "תרגיל - התרעת צבע אדום",
        "title_en": "Drill - Red Alert",
        "description_he": "זהו תרגיל - פעלו כמו באירוע אמיתי",
        "description_en": "This is a drill - act as in a real event", 
        "instructions_he": "זהו תרגיל - היכנסו למרחב המוגן",
        "instructions_en": "This is a drill - enter protected space"
    },
    "102": {
        "type": "generalDrill",
        "title_he": "תרגיל כללי",
        "title_en": "General Drill",
        "description_he": "זהו תרגיל - פעלו לפי ההוראות",
        "description_en": "This is a drill - follow instructions",
        "instructions_he": "זהו תרגיל - פעלו לפי ההוראות",
        "instructions_en": "This is a drill - follow instructions"
    }
}

# Pydantic models for API request/response
class FakeAlert(BaseModel):
    """Model for creating fake alerts for testing purposes"""
    data: List[str]  # List of affected areas/cities
    cat: str = "1"  # Alert category (1=missile threat, 2=terrorist infiltration, etc.)
    title: Optional[str] = None  # Alert title (auto-generated if not provided)
    desc: Optional[str] = None  # Alert description (auto-generated if not provided)
    language: str = "he"  # Language for auto-generated content (he/en)
    
class AlertResponse(BaseModel):
    """Model for alert response with enhanced information"""
    success: bool
    message: str
    alert_id: Optional[str] = None
    alert_details: Optional[dict] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles application startup and shutdown events.
    """
    logger.info("Application startup: Initializing database and background tasks.")
    await init_db()
    poll_task = asyncio.create_task(poll_for_alerts())
    yield
    logger.info("Application shutdown: Cleaning up resources.")
    poll_task.cancel()
    await close_db()

app = FastAPI(
    title="Pikud Haoref Real-Time Alert Service",
    description="A middleware service that polls the Pikud Haoref API and streams alerts via Server-Sent Events (SSE). Includes testing endpoints for fake alerts.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add the Geo-IP middleware to the application
app.middleware("http")(geo_ip_middleware)

# Rate limiting disabled for emergency alert system
# Emergency alerts require immediate access during critical situations
# app.state.limiter = limiter
# app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# app.add_middleware(SlowAPIMiddleware)

@app.get("/", summary="Service Status")
async def root():
    """
    Provides a simple status message to confirm the service is running
    and directs users to the main SSE endpoint.
    """
    return {"message": "Welcome to the Pikud Haoref Real-Time Alert Service"}

@app.get("/api/alerts-stream", summary="Real-Time Alert Stream")
# Note: No rate limiting for emergency alerts - people need immediate access during emergencies
async def alerts_stream(request: Request, api_key: str = Depends(get_api_key)):
    """
    Establishes a Server-Sent Events (SSE) connection with the client.

    This endpoint keeps the connection open and streams new alerts as they
    become available from the background polling service.
    """
    return StreamingResponse(alert_event_generator(request), media_type="text/event-stream")

@app.get("/api/webhook/alerts", summary="Internal Alert Webhook")
async def alerts_webhook(request: Request, api_key: str = Depends(get_api_key)):
    """
    Internal SSE endpoint for services (requires API key authentication).
    
    Used by MCP server and other internal services to subscribe to real-time alerts.
    This endpoint is designed for server-to-server communication and requires
    the same API key authentication as the client endpoint for security.
    """
    return StreamingResponse(alert_event_generator(request), media_type="text/event-stream")

@app.post("/api/test/fake-alert", summary="Create Fake Alert for Testing", response_model=AlertResponse)
# Note: No rate limiting on test endpoint for easier development and testing
async def create_fake_alert(request: Request, fake_alert: FakeAlert, api_key: str = Depends(get_api_key)):
    """
    Creates a fake alert for testing the webhook and MCP integration with Hebrew/English descriptions.
    
    This endpoint allows you to simulate alerts for testing purposes. The fake alert
    will be added to the alert queue and broadcast via SSE to all connected clients.
    
    **Request Body:**
    - `data`: List of affected cities/areas (e.g., ["תל אביב - מרכז העיר", "רמת גן"])
    - `cat`: Alert category (see categories below, default: "1")
    - `title`: Alert title (auto-generated if not provided)
    - `desc`: Alert description (auto-generated if not provided)
    - `language`: Language for auto-generated content - "he" (Hebrew) or "en" (English)
    
    **Alert Categories:**
    - `1`: Red Alert - Missile Threat (התרעת צבע אדום)
    - `2`: Radiological Event (אירוע רדיולוגי)  
    - `3`: Earthquake (רעידת אדמה)
    - `4`: Tsunami (צונאמי)
    - `5`: Hostile Aircraft Intrusion (חדירת כלי טיס עוין)
    - `6`: Hazardous Materials (חומרים מסוכנים)
    - `7`: Terrorist Infiltration (חדירת מחבלים)
    - `101`: Drill - Red Alert (תרגיל - התרעת צבע אדום)
    - `102`: General Drill (תרגיל כללי)
    
    **Examples:**
    ```json
    {
        "data": ["תל אביב - מרכז העיר", "רמת גן"],
        "cat": "1",
        "language": "he"
    }
    ```
    
    ```json
    {
        "data": ["Jerusalem", "Haifa"],
        "cat": "3", 
        "language": "en",
        "title": "Custom Earthquake Alert",
        "desc": "Custom earthquake description for testing"
    }
    ```
    """
    import uuid
    
    # Generate a unique alert ID
    alert_id = str(uuid.uuid4())[:8]
    
    # Get category information
    category_info = ALERT_CATEGORIES.get(fake_alert.cat, ALERT_CATEGORIES["1"])
    
    # Auto-generate title and description if not provided
    title = fake_alert.title
    desc = fake_alert.desc
    
    if not title:
        title = category_info.get(f"title_{fake_alert.language}", category_info["title_he"])
    
    if not desc:
        desc = category_info.get(f"description_{fake_alert.language}", category_info["description_he"])
    
    # Create the alert data structure matching the real API format
    alert_data = {
        "id": alert_id,
        "data": fake_alert.data,
        "cat": fake_alert.cat,
        "title": title,
        "desc": desc
    }
    
    # Create enhanced alert details for response
    alert_details = {
        "id": alert_id,
        "type": category_info["type"],
        "category": fake_alert.cat,
        "areas": fake_alert.data,
        "title_he": category_info["title_he"],
        "title_en": category_info["title_en"],
        "description_he": category_info["description_he"], 
        "description_en": category_info["description_en"],
        "instructions_he": category_info["instructions_he"],
        "instructions_en": category_info["instructions_en"],
        "language_used": fake_alert.language,
        "title_sent": title,
        "description_sent": desc
    }
    
    # Add the fake alert to the queue for SSE broadcasting
    try:
        await alert_queue.put(alert_data)
        # Also persist to SQLite so it appears in history/city queries
        structured = {
            "id": alert_id,
            "type": category_info["type"],
            "cities": fake_alert.data,
            "instructions": category_info.get(f"instructions_{fake_alert.language}", ""),
        }
        await save_alert(structured)
        logger.info(f"Fake alert created: {alert_id} - {title} (Category: {fake_alert.cat}, Type: {category_info['type']})")
        
        return AlertResponse(
            success=True,
            message=f"Fake alert '{title}' created successfully and will be broadcast to all SSE clients",
            alert_id=alert_id,
            alert_details=alert_details
        )
    except Exception as e:
        logger.error(f"Failed to create fake alert: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create fake alert: {str(e)}")


# --- REST API Endpoints (backed by SQLite) ---

@app.get("/health", summary="Health Check")
async def health_check():
    """Returns service health status."""
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/alerts/current", summary="Current Active Alerts")
async def get_current_alerts():
    """Get the current active alert (if any) from the in-memory state."""
    if app_state.last_alert_id:
        return {"active": True, "last_alert_id": app_state.last_alert_id}
    return {"active": False, "last_alert_id": None}


@app.get("/api/alerts/history", summary="Alert History")
async def get_alert_history(
    city: Optional[str] = None,
    limit: int = 50,
    since: Optional[str] = None,
):
    """
    Get alert history from the database.

    - **city**: Filter by city name (Hebrew)
    - **limit**: Max results (1-100, default 50)
    - **since**: ISO timestamp to filter alerts after
    """
    limit = max(1, min(100, limit))
    if city:
        alerts = await get_alerts_by_city(city, limit)
    else:
        alerts = await get_recent_alerts(limit, since)
    return {"alerts": alerts, "count": len(alerts)}


@app.get("/api/alerts/city/{city_name}", summary="Alerts by City")
async def get_city_alerts(city_name: str, limit: int = 50):
    """Get alert history for a specific city."""
    limit = max(1, min(100, limit))
    alerts = await get_alerts_by_city(city_name, limit)
    return {"city": city_name, "alerts": alerts, "count": len(alerts)}


@app.get("/api/alerts/stats", summary="Alert Statistics")
async def alerts_stats():
    """Get aggregate statistics about stored alerts."""
    stats = await get_alert_stats()
    return stats

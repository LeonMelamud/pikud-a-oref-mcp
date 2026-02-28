import asyncio
import httpx
import json
import logging
from ..core.alert_queue import alert_queue
from ..core.state import app_state
from ..db.database import save_alert

logger = logging.getLogger(__name__)

# Constants for the Pikud Haoref API
POHA_API_URL = "https://www.oref.org.il/WarningMessages/alert/alerts.json"
REQUEST_HEADERS = {
    "Referer": "https://www.oref.org.il/",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}
POLL_INTERVAL_SECONDS = 2
POLL_BACKOFF_ON_403 = 30  # Wait 30s before retrying after a 403

def get_alert_type_by_category(category: int) -> str:
    """Maps an alert category ID to its type."""
    alert_types = {
        1: "missiles",
        2: "radiologicalEvent",
        3: "earthQuake",
        4: "tsunami",
        5: "hostileAircraftIntrusion",
        6: "hazardousMaterials",
        7: "terroristInfiltration",
        8: "missilesDrill",
        9: "earthQuakeDrill",
        10: "radiologicalEventDrill",
        11: "tsunamiDrill",
        12: "hostileAircraftIntrusionDrill",
        13: "hazardousMaterialsDrill",
        14: "terroristInfiltrationDrill",
        20: "newsFlash", # As per the node.js library, earlyWarning is now newsFlash
        99: "unknown",
    }
    return alert_types.get(category, "unknown")

async def fetch_and_process_alerts(client: httpx.AsyncClient, url: str):
    """Fetches alerts from a given URL and processes them."""
    response = await client.get(url, headers=REQUEST_HEADERS)
    response.raise_for_status()

    text = response.content.decode("utf-8-sig").strip()
    if not text:
        return None

    try:
        alert_data = json.loads(text)
        return alert_data
    except json.JSONDecodeError:
        logger.error(f"Failed to decode JSON from response: '{text}'")
        return None

async def poll_for_alerts():
    """
    Polls the Pikud Haoref API periodically for new alerts.

    If a new alert is found, it is put into the shared alert_queue.
    """
    async with httpx.AsyncClient() as client:
        while True:
            try:
                alert_data = await fetch_and_process_alerts(client, POHA_API_URL)

                if not alert_data:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                # The history API is no longer polled here, so we don't need to check for list type
                current_id = alert_data.get("id")
                if alert_data and current_id != app_state.last_alert_id:
                    # Filter out test alerts
                    cities = [city.strip() for city in alert_data.get("data", []) if "בדיקה" not in city]
                    if not cities:
                        logger.info(f"Ignoring test alert: {alert_data}")
                        await asyncio.sleep(POLL_INTERVAL_SECONDS)
                        continue

                    structured_alert = {
                        "id": current_id,
                        "cat": alert_data.get("cat"),
                        "type": get_alert_type_by_category(alert_data.get("cat")),
                        "title": alert_data.get("title"),
                        "cities": cities,
                        "instructions": alert_data.get("title")
                    }
                    
                    app_state.last_alert_id = current_id
                    logger.info(f"New alert detected: {structured_alert}")
                    await alert_queue.put(structured_alert)
                    await save_alert(structured_alert)

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:
                    logger.warning(f"403 Forbidden from oref.org.il — likely geo-blocked (non-Israeli IP). Retrying in {POLL_BACKOFF_ON_403}s.")
                    await asyncio.sleep(POLL_BACKOFF_ON_403)
                    continue
                logger.error(f"HTTP error from oref API: {e}")
            except httpx.RequestError as e:
                logger.error(f"A network error occurred while requesting alerts: {e}")
            except Exception as e:
                logger.error(f"An unexpected error occurred in poller: {e}", exc_info=True)

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

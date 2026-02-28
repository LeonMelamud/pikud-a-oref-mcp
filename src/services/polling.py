import asyncio
import hashlib
import httpx
import json
import logging
from collections import defaultdict
from ..core.alert_queue import alert_queue
from ..core.state import app_state
from ..db.database import save_alert

logger = logging.getLogger(__name__)

# Constants for the Pikud Haoref API
POHA_API_URL = "https://www.oref.org.il/WarningMessages/alert/alerts.json"
POHA_HISTORY_URL = "https://www.oref.org.il/WarningMessages/alert/History/AlertsHistory.json"
HISTORY_SYNC_INTERVAL = 300  # sync history every 5 minutes
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


async def sync_history(client: httpx.AsyncClient):
    """
    Fetch from the oref.org.il history API and backfill all missing alerts into DB.
    The history API returns per-city entries, so we group them by (alertDate, title, category)
    into proper alert objects before saving.
    """
    try:
        response = await client.get(POHA_HISTORY_URL, headers=REQUEST_HEADERS)
        response.raise_for_status()
        text = response.content.decode("utf-8-sig").strip()
        if not text:
            return 0

        history = json.loads(text)
        if not isinstance(history, list):
            logger.warning("History API returned non-list data")
            return 0

        # Group per-city entries into alerts by (alertDate, title, category)
        groups: dict[str, dict] = defaultdict(lambda: {"cities": [], "title": "", "category": "", "alertDate": ""})
        for entry in history:
            alert_date = entry.get("alertDate", "")
            title = entry.get("title", "")
            category = str(entry.get("category", ""))
            city = entry.get("data", "")
            if not city or not alert_date:
                continue

            # Group key: date + category (same time + same type = same alert)
            key = f"{alert_date}|{category}"
            g = groups[key]
            g["alertDate"] = alert_date
            g["title"] = title
            g["category"] = category
            if city not in g["cities"]:
                g["cities"].append(city)

        # Save each group as an alert
        saved = 0
        for key, g in groups.items():
            # Generate a stable ID from the group key
            alert_id = hashlib.md5(key.encode()).hexdigest()[:16]
            # Convert alertDate "YYYY-MM-DD HH:MM:SS" to ISO format
            iso_ts = g["alertDate"].replace(" ", "T")
            alert_obj = {
                "id": alert_id,
                "cat": g["category"],
                "title": g["title"],
                "desc": g["title"],
                "type": get_alert_type_by_category(int(g["category"]) if g["category"].isdigit() else 0),
                "cities": g["cities"],
                "data": g["cities"],
                "timestamp": iso_ts,
            }
            try:
                await save_alert(alert_obj)
                saved += 1
            except Exception:
                pass  # INSERT OR IGNORE handles duplicates

        logger.info(f"History sync: processed {len(groups)} alert groups from {len(history)} entries, saved {saved}")
        return saved
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            logger.warning("History sync: 403 from oref.org.il — geo-blocked")
        else:
            logger.error(f"History sync HTTP error: {e}")
    except Exception as e:
        logger.error(f"History sync error: {e}", exc_info=True)
    return 0

async def poll_for_alerts():
    """
    Polls the Pikud Haoref API periodically for new alerts.

    If a new alert is found, it is put into the shared alert_queue.
    Also syncs from the oref history API on startup and every HISTORY_SYNC_INTERVAL seconds.
    """
    async with httpx.AsyncClient() as client:
        # Initial history sync on startup — backfill all missing alerts
        logger.info("Running initial history sync from oref.org.il...")
        await sync_history(client)
        last_history_sync = asyncio.get_event_loop().time()

        while True:
            try:
                # Periodic history sync
                now = asyncio.get_event_loop().time()
                if now - last_history_sync >= HISTORY_SYNC_INTERVAL:
                    logger.info("Running periodic history sync...")
                    await sync_history(client)
                    last_history_sync = now

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

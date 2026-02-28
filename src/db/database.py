import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

try:
    import aiosqlite
except ImportError:
    aiosqlite = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

DATABASE_PATH = os.getenv("DATABASE_PATH", "data/alerts.db")

_db: Optional[aiosqlite.Connection] = None

# In-memory cache: city name -> integer ID (avoids DB round-trip on every insert)
_city_cache: Dict[str, int] = {}


async def init_db():
    """Initialize database connection and create tables."""
    global _db
    os.makedirs(os.path.dirname(DATABASE_PATH) or ".", exist_ok=True)
    _db = await aiosqlite.connect(DATABASE_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA foreign_keys=ON")
    await _db.executescript("""
        CREATE TABLE IF NOT EXISTS alerts (
            id TEXT PRIMARY KEY,
            title TEXT,
            category TEXT,
            description TEXT,
            data_json TEXT,
            raw_json TEXT,
            timestamp TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS city_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id TEXT NOT NULL,
            city_id INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            UNIQUE(alert_id, city_id)
        );
        CREATE INDEX IF NOT EXISTS idx_city_alerts_city_id ON city_alerts(city_id);
        CREATE INDEX IF NOT EXISTS idx_city_alerts_timestamp ON city_alerts(timestamp);
        CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp);
    """)
    await _db.commit()

    # Pre-load city cache from DB
    cursor = await _db.execute("SELECT id, name FROM cities")
    rows = await cursor.fetchall()
    _city_cache.clear()
    for row in rows:
        _city_cache[row["name"]] = row["id"]
    logger.info(f"Database initialized at {DATABASE_PATH} ({len(_city_cache)} cities cached)")


async def close_db():
    """Close database connection."""
    global _db
    if _db:
        await _db.close()
        _db = None
    _city_cache.clear()


async def _get_city_id(city_name: str) -> int:
    """Resolve a city name to its integer ID, inserting if new. Uses in-memory cache."""
    if city_name in _city_cache:
        return _city_cache[city_name]
    # Not in cache — insert or fetch from DB
    await _db.execute("INSERT OR IGNORE INTO cities (name) VALUES (?)", (city_name,))
    cursor = await _db.execute("SELECT id FROM cities WHERE name = ?", (city_name,))
    row = await cursor.fetchone()
    city_id = row["id"]
    _city_cache[city_name] = city_id
    return city_id


async def save_alert(alert: Dict[str, Any]):
    """Save an alert and its per-city entries."""
    if not _db:
        logger.warning("Database not initialized, skipping save")
        return

    timestamp = alert.get("timestamp") or datetime.now().isoformat()
    cities = alert.get("cities") or alert.get("data", [])
    if isinstance(cities, str):
        cities = [cities]

    await _db.execute(
        "INSERT OR IGNORE INTO alerts (id, title, category, description, data_json, raw_json, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            alert.get("id"),
            alert.get("title"),
            alert.get("category") or alert.get("cat"),
            alert.get("desc"),
            json.dumps(cities, ensure_ascii=False),
            json.dumps(alert, ensure_ascii=False),
            timestamp,
        ),
    )

    for city in cities:
        city_id = await _get_city_id(city)
        await _db.execute(
            "INSERT OR IGNORE INTO city_alerts (alert_id, city_id, timestamp) VALUES (?, ?, ?)",
            (alert.get("id"), city_id, timestamp),
        )

    await _db.commit()


def _normalize_alert_row(r) -> Dict[str, Any]:
    """Build a normalized alert dict from a DB row, falling back to raw_json for missing fields."""
    raw = {}
    if r["raw_json"]:
        try:
            raw = json.loads(r["raw_json"])
        except json.JSONDecodeError:
            pass
    return {
        "id": r["id"],
        "title": r["title"] or raw.get("title") or raw.get("instructions", ""),
        "category": r["category"] or raw.get("cat", ""),
        "desc": r["description"] or raw.get("desc") or raw.get("instructions", ""),
        "type": raw.get("type", ""),
        "data": json.loads(r["data_json"]) if r["data_json"] else raw.get("cities") or raw.get("data") or [],
        "timestamp": r["timestamp"],
    }


async def get_alerts_by_city(city: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get alerts for a specific city."""
    if not _db:
        return []
    limit = min(limit, 100)
    # Resolve city name to ID; if city not in DB, no results
    city_id = _city_cache.get(city)
    if city_id is None:
        return []
    cursor = await _db.execute(
        "SELECT a.id, a.title, a.category, a.description, a.data_json, a.raw_json, a.timestamp "
        "FROM city_alerts ca JOIN alerts a ON ca.alert_id = a.id "
        "WHERE ca.city_id = ? ORDER BY a.timestamp DESC LIMIT ?",
        (city_id, limit),
    )
    rows = await cursor.fetchall()
    return [_normalize_alert_row(r) for r in rows]


async def get_recent_alerts(limit: int = 50, since: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get recent alerts, optionally filtered by timestamp."""
    if not _db:
        return []
    limit = min(limit, 100)
    if since:
        cursor = await _db.execute(
            "SELECT id, title, category, description, data_json, raw_json, timestamp "
            "FROM alerts WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
            (since, limit),
        )
    else:
        cursor = await _db.execute(
            "SELECT id, title, category, description, data_json, raw_json, timestamp "
            "FROM alerts ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
    rows = await cursor.fetchall()
    return [_normalize_alert_row(r) for r in rows]


async def get_alert_stats() -> Dict[str, Any]:
    """Get basic statistics about stored alerts."""
    if not _db:
        return {"total_alerts": 0, "total_city_entries": 0, "top_cities": []}
    cur = await _db.execute("SELECT COUNT(*) as c FROM alerts")
    total = (await cur.fetchone())["c"]
    cur2 = await _db.execute("SELECT COUNT(*) as c FROM city_alerts")
    total_cities = (await cur2.fetchone())["c"]
    cur3 = await _db.execute(
        "SELECT c.name as city, COUNT(*) as cnt FROM city_alerts ca "
        "JOIN cities c ON ca.city_id = c.id "
        "GROUP BY ca.city_id ORDER BY cnt DESC LIMIT 10"
    )
    top = [{"city": r["city"], "count": r["cnt"]} for r in await cur3.fetchall()]
    return {"total_alerts": total, "total_city_entries": total_cities, "top_cities": top}

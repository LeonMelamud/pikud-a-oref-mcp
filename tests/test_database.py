import pytest
import os
import asyncio
from unittest.mock import patch, AsyncMock
from src.db import database


@pytest.fixture
async def test_db(tmp_path):
    """Initialize a temporary test database."""
    db_path = str(tmp_path / "test_alerts.db")
    with patch.object(database, 'DATABASE_PATH', db_path):
        await database.init_db()
        yield db_path
        await database.close_db()


@pytest.mark.asyncio
async def test_init_db_creates_tables(test_db):
    """Test that init_db creates the expected tables."""
    assert database._db is not None
    cursor = await database._db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row["name"] for row in await cursor.fetchall()]
    assert "alerts" in tables
    assert "city_alerts" in tables


@pytest.mark.asyncio
async def test_save_and_get_recent_alerts(test_db):
    """Test saving an alert and retrieving it."""
    alert = {
        "id": "test-1",
        "title": "Test Alert",
        "category": "1",
        "desc": "Rocket fire",
        "data": ["תל אביב - יפו", "רמת גן"],
    }
    await database.save_alert(alert)

    recent = await database.get_recent_alerts(limit=10)
    assert len(recent) == 1
    assert recent[0]["id"] == "test-1"
    assert "תל אביב - יפו" in recent[0]["data"]


@pytest.mark.asyncio
async def test_get_alerts_by_city(test_db):
    """Test filtering alerts by city."""
    alert = {
        "id": "test-2",
        "title": "Test",
        "category": "1",
        "desc": "desc",
        "data": ["חיפה", "עכו"],
    }
    await database.save_alert(alert)

    haifa = await database.get_alerts_by_city("חיפה")
    assert len(haifa) == 1
    assert haifa[0]["id"] == "test-2"

    tlv = await database.get_alerts_by_city("תל אביב")
    assert len(tlv) == 0


@pytest.mark.asyncio
async def test_get_alert_stats(test_db):
    """Test alert statistics."""
    for i in range(3):
        await database.save_alert({
            "id": f"stat-{i}",
            "title": "Stat",
            "data": ["ירושלים"],
        })
    stats = await database.get_alert_stats()
    assert stats["total_alerts"] == 3
    assert stats["total_city_entries"] == 3
    assert stats["top_cities"][0]["city"] == "ירושלים"


@pytest.mark.asyncio
async def test_get_recent_alerts_with_since(test_db):
    """Test filtering recent alerts by timestamp."""
    await database.save_alert({
        "id": "old-1",
        "title": "Old",
        "data": ["a"],
        "timestamp": "2024-01-01T00:00:00",
    })
    await database.save_alert({
        "id": "new-1",
        "title": "New",
        "data": ["b"],
        "timestamp": "2025-06-01T00:00:00",
    })

    since = await database.get_recent_alerts(limit=50, since="2025-01-01T00:00:00")
    assert len(since) == 1
    assert since[0]["id"] == "new-1"

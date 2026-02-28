import pytest
import asyncio
import threading
import time
import uvicorn
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

# Mock the background tasks and db init before importing
with patch('src.services.polling.poll_for_alerts', new=AsyncMock()), \
     patch('src.db.database.init_db', new=AsyncMock()), \
     patch('src.db.database.close_db', new=AsyncMock()):
    from src.api.main import app


@pytest.fixture
def live_server():
    """
    Creates a live server for integration testing.
    Returns the base URL of the server.
    """
    # Use TestClient for synchronous testing of FastAPI apps
    client = TestClient(app)
    return "http://testserver"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def client():
    """
    FastAPI TestClient fixture for testing the application.
    """
    return TestClient(app)
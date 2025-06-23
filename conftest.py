import pytest
import asyncio
import threading
import time
import uvicorn
from fastapi.testclient import TestClient
from main import app


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
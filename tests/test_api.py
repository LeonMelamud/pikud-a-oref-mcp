import os
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

# Set environment for testing
os.environ["API_KEY"] = "test-key"

# Mock the infinite background tasks before importing main
with patch('polling.poll_for_alerts', new=AsyncMock()):
    from main import app

@pytest.fixture
def client():
    """Test client fixture with fresh state for each test"""
    return TestClient(app)

def test_root_endpoint(client):
    """
    Tests that the root endpoint is accessible.
    """
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to the Pikud Haoref Real-Time Alert Service"}

@patch('security.API_KEY', 'test-key')
@patch('main.alert_event_generator')
def test_alerts_stream_requires_api_key(mock_generator, client):
    """
    Tests that the alerts stream endpoint returns a 401 Unauthorized
    error when no API key is provided.
    """
    response = client.get("/api/alerts-stream")
    assert response.status_code == 401
    assert "API key is missing" in response.text

@patch('security.API_KEY', 'test-key')
@patch('main.alert_event_generator')
def test_alerts_stream_with_invalid_api_key(mock_generator, client):
    """
    Tests that the alerts stream endpoint returns a 401 Unauthorized
    error when an invalid API key is provided.
    """
    headers = {"X-API-Key": "invalid-key"}
    response = client.get("/api/alerts-stream", headers=headers)
    assert response.status_code == 401
    assert "Invalid API key" in response.text

@patch('security.API_KEY', 'test-key')
@patch('main.alert_event_generator')
def test_alerts_stream_with_valid_api_key(mock_generator, client):
    """
    Tests that the alerts stream endpoint can be connected to with a valid API key.
    We'll check that the connection can be established successfully.
    """
    # Mock the generator to return a simple test response
    async def mock_gen(request):
        yield "data: test\n\n"
    
    mock_generator.return_value = mock_gen(None)
    
    headers = {"X-API-Key": "test-key"}
    response = client.get("/api/alerts-stream", headers=headers)
    assert response.status_code == 200 
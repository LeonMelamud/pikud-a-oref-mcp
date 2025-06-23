import pytest
from unittest.mock import patch, Mock
from fastapi import Request, HTTPException
from fastapi.responses import Response
from security import geo_ip_middleware, get_api_key
from geolocation import MAXMIND_DB_PATH

# A simple async function to be used as the 'call_next' argument in middleware
async def mock_call_next(request: Request):
    # In a real scenario, this would pass the request to the next middleware
    # or the endpoint. For testing, we just need an awaitable that returns
    # a mock response.
    return Mock(status_code=200)

@pytest.mark.asyncio
async def test_geo_ip_middleware_allows_non_stream_requests():
    """
    Tests that requests to endpoints other than '/api/alerts-stream' are not
    checked and are allowed to pass through.
    """
    # Arrange: Create a mock request for a non-protected endpoint
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "client": ("1.2.3.4", 123)})
    
    # Act: Call the middleware
    response = await geo_ip_middleware(request, mock_call_next)

    # Assert: The response should be the one from `mock_call_next`
    assert response.status_code == 200

@pytest.mark.asyncio
@patch('security.get_geoip_reader')
async def test_geo_ip_middleware_allows_israel_ip(mock_get_reader):
    """
    Tests that an IP address identified as being from Israel ('IL') is
    allowed to access the protected stream endpoint.
    """
    # Arrange
    request = Request({"type": "http", "method": "GET", "path": "/api/alerts-stream", "headers": [], "client": ("1.2.3.4", 123)})
    
    # Mock the response from the GeoIP database lookup
    mock_country_response = Mock()
    mock_country_response.country.iso_code = "IL"
    
    mock_reader = Mock()
    mock_reader.country.return_value = mock_country_response
    
    # Configure the patched async context manager to yield our mock reader
    mock_get_reader.return_value.__aenter__.return_value = mock_reader
    
    # Act
    response = await geo_ip_middleware(request, mock_call_next)
    
    # Assert
    assert response.status_code == 200
    mock_reader.country.assert_called_with('1.2.3.4')

@pytest.mark.asyncio
@patch('src.security.get_geoip_reader')
async def test_geo_ip_middleware_blocks_non_israel_ip(mock_get_reader):
    """
    Tests that an IP address from outside Israel is blocked with an
    HTTP 403 Forbidden error.
    """
    # Arrange
    # A dummy 'call_next' function that the middleware will invoke
    async def call_next(request):
        return Response("OK")

    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/alerts-stream",
        "headers": [],
        "client": ("8.8.8.8", 123)
    })

    mock_country_response = Mock()
    mock_country_response.country.iso_code = "US"
    mock_country_response.country.name = "United States"

    mock_reader = Mock()
    mock_reader.country.return_value = mock_country_response
    mock_get_reader.return_value.__aenter__.return_value = mock_reader

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await geo_ip_middleware(request, call_next)
    
    assert exc_info.value.status_code == 403
    assert "Access denied" in exc_info.value.detail

@pytest.mark.asyncio
async def test_geo_ip_middleware_allows_if_db_not_configured():
    """
    Tests that if the GeoIP database is not configured (path is None),
    the middleware allows the request to proceed without performing an IP check.
    """
    with patch('geolocation.MAXMIND_DB_PATH', None):
        with patch('security.get_geoip_reader') as mock_get_reader:
            # Arrange
            request = Request({"type": "http", "method": "GET", "path": "/api/alerts-stream", "headers": [], "client": ("1.2.3.4", 123)})

            # Simulate the DB being unavailable
            mock_get_reader.return_value.__aenter__.return_value = None
            
            # Act
            response = await geo_ip_middleware(request, mock_call_next)
            
            # Assert
            assert response.status_code == 200 
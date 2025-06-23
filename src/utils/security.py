import logging
import os
from contextlib import asynccontextmanager

import geoip2.database
from fastapi import HTTPException, Request, Depends
from geoip2.errors import AddressNotFoundError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from fastapi.security import APIKeyHeader
from .geolocation import get_geoip_reader

logger = logging.getLogger(__name__)

# --- API Key Authentication ---
API_KEY = os.getenv("API_KEY")
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key: str = Depends(api_key_header)):
    """
    Dependency to validate the API key from the request header.
    
    Raises HTTPException 401 if the key is missing or invalid.
    """
    if not API_KEY:
        # If the server has no API_KEY configured, authentication is disabled.
        # This allows the service to run without security for local development.
        logger.warning("API_KEY not configured. Allowing request without authentication.")
        return None
        
    if not api_key:
        logger.warning("API key missing from request.")
        raise HTTPException(status_code=401, detail="API key is missing")
        
    if api_key != API_KEY:
        logger.warning("Invalid API key received.")
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return api_key

# --- Rate Limiting Setup ---
# The key function uses the client's IP address to identify them.
limiter = Limiter(key_func=get_remote_address)

# Load the path to the GeoIP database from an environment variable
# This is crucial for keeping paths and sensitive info out of the code.
GEOIP_DB_PATH = os.getenv("GEOIP_DB_PATH")

@asynccontextmanager
async def get_geoip_reader():
    """
    An asynchronous context manager to safely open and close the GeoIP database.
    Yields a database reader object.
    """
    if not GEOIP_DB_PATH or not os.path.exists(GEOIP_DB_PATH):
        logger.warning("GEOIP_DB_PATH is not configured or the file does not exist. Geo-restriction is disabled.")
        yield None
        return

    reader = None
    try:
        reader = geoip2.database.Reader(GEOIP_DB_PATH)
        yield reader
    finally:
        if reader:
            reader.close()

async def geo_ip_middleware(request: Request, call_next):
    """
    FastAPI middleware to perform geo-restriction based on client IP.

    It checks if the incoming request is for the alert stream and, if so,
    validates that the client's IP address originates from Israel ('IL').
    """
    # We only want to protect the actual data stream endpoint
    if request.url.path == "/api/alerts-stream":
        # In a production setup behind a proxy, the client IP is often in this header.
        # Fallback to the direct request IP if the header is not present.
        client_ip = request.headers.get("X-Forwarded-For", request.client.host)

        async with get_geoip_reader() as reader:
            if reader:
                try:
                    response = reader.country(client_ip)
                    # Check if the country code is NOT Israel
                    if response.country.iso_code != "IL":
                        logger.warning(f"Blocking request from non-IL IP: {client_ip} ({response.country.name})")
                        raise HTTPException(
                            status_code=403,
                            detail="Access denied: This service is only available in Israel.",
                        )
                except AddressNotFoundError:
                    logger.warning(f"Could not find location for IP: {client_ip}. Allowing request.")
                except Exception as e:
                    logger.error(f"An unexpected error occurred during GeoIP lookup: {e}", exc_info=True)
                    # If the exception is the one we're deliberately raising, re-raise it.
                    if isinstance(e, HTTPException):
                        raise
                    # Otherwise, fail open for other unexpected errors.
            # If the reader is None (not configured), the request is allowed to pass.

    # Proceed to the actual endpoint
    response = await call_next(request)
    return response 
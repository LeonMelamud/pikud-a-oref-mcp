import os
import geoip2.database
from contextlib import asynccontextmanager
import logging

logger = logging.getLogger(__name__)

# Define the path to the GeoIP database file.
# This assumes the database is in a 'data' directory at the project root.
MAXMIND_DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'GeoLite2-Country.mmdb')

@asynccontextmanager
async def get_geoip_reader():
    """
    An async context manager to provide a GeoIP2 database reader.

    This function checks if the database file exists and yields a reader
    instance. If the file doesn't exist or an error occurs, it yields None
    and logs a warning.
    """
    reader = None
    if not os.path.exists(MAXMIND_DB_PATH):
        logger.warning(f"GeoIP database not found at: {MAXMIND_DB_PATH}. Geo-blocking is disabled.")
        yield None
        return

    try:
        # geoip2 is synchronous, but we can wrap it in an async context manager
        # for consistent async patterns in the application.
        reader = geoip2.database.Reader(MAXMIND_DB_PATH)
        yield reader
    except Exception as e:
        logger.error(f"Failed to load GeoIP database: {e}")
        yield None
    finally:
        if reader:
            reader.close() 
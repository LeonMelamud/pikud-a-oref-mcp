import asyncio
from dataclasses import dataclass

# A queue to broadcast new alerts to all connected clients
alert_queue: asyncio.Queue = asyncio.Queue()

@dataclass
class AppState:
    """A simple class to hold the application's shared state."""
    # In-memory store for the last alert ID.
    # For a production system, this might be moved to a more persistent store like Redis.
    last_alert_id: str | None = None

# A single, shared instance of the application state
app_state = AppState()

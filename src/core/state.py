import asyncio
from dataclasses import dataclass
from typing import Optional

# A queue to broadcast new alerts to all connected clients
alert_queue: asyncio.Queue = asyncio.Queue()

@dataclass
class AppState:
    """A simple class to hold the application's shared state."""
    last_alert_id: Optional[str] = None

# A single, shared instance of the application state
app_state = AppState()

import asyncio
import json
import logging
from ..core.alert_queue import alert_queue
from fastapi import Request

logger = logging.getLogger(__name__)

async def alert_event_generator(request: Request):
    """
    Yields server-sent events for new alerts.

    This generator waits for new alerts to be placed in the alert_queue
    and sends them to the client in the SSE format.
    """
    try:
        while True:
            # Check if the client has disconnected
            if await request.is_disconnected():
                logger.warning("Client disconnected, stopping alert stream.")
                break

            try:
                # Wait for a new alert from the queue, with a timeout
                alert = await asyncio.wait_for(alert_queue.get(), timeout=1.0)
                # Format and yield the alert as an SSE message
                yield f"event: new_alert\ndata: {json.dumps(alert)}\n\n"
            except asyncio.TimeoutError:
                # If no alert is received, send a keep-alive comment
                yield ": keep-alive\n\n"
    except Exception as e:
        logger.error(f"An unexpected error occurred in event generator: {e}")
        # Optionally, re-raise or handle specific exceptions
    finally:
        logger.info("Alert event generator finished.")

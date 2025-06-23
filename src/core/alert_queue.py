import asyncio

# A simple in-memory queue for passing alerts from the poller to the SSE streamer.
alert_queue = asyncio.Queue() 
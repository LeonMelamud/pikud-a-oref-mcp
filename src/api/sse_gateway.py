#!/usr/bin/env python3
"""
SSE Gateway Server for VSCode Extension

This server provides an SSE endpoint for the VSCode extension to receive alerts.
It subscribes to the FastAPI webhook and broadcasts alerts to connected VSCode clients.
"""
import asyncio
import json
import logging
import os
from typing import Dict, Any, Set
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# SSE Client Configuration
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://localhost:8000/api/webhook/alerts")
API_KEY = os.getenv("API_KEY", "poha-test-key-2024-secure")

# Store connected SSE clients for broadcasting
connected_clients: Set[asyncio.Queue] = set()

class AlertSubscriber:
    """SSE client for subscribing to alerts from the FastAPI webhook"""
    
    def __init__(self, webhook_url: str, api_key: str):
        self.webhook_url = webhook_url
        self.api_key = api_key
        self.is_connected = False
        self.subscription_task = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        
    async def subscribe(self):
        """Subscribe to SSE webhook and process events"""
        while self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                logger.info(f"🔗 Connecting to SSE webhook: {self.webhook_url}")
                headers = {"X-API-Key": self.api_key}
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream("GET", self.webhook_url, headers=headers) as response:
                        if response.status_code == 200:
                            self.is_connected = True
                            self.reconnect_attempts = 0
                            logger.info("✅ Successfully connected to SSE webhook")
                            
                            async for line in response.aiter_lines():
                                if line.startswith("data: "):
                                    try:
                                        event_data = line[6:]  # Remove "data: " prefix
                                        
                                        # Handle keep-alive messages
                                        if event_data.strip() == "keep-alive":
                                            continue
                                            
                                        # Try to parse as JSON
                                        alert_data = json.loads(event_data)
                                        await self.process_alert(alert_data)
                                        
                                    except json.JSONDecodeError:
                                        # Non-JSON data (like keep-alive), skip
                                        continue
                                    except Exception as e:
                                        logger.error(f"Error processing SSE event: {e}")
                        else:
                            logger.error(f"SSE connection failed with status {response.status_code}")
                            self.is_connected = False
                            break
                            
            except Exception as e:
                self.is_connected = False
                self.reconnect_attempts += 1
                logger.error(f"SSE connection error (attempt {self.reconnect_attempts}): {e}")
                if self.reconnect_attempts < self.max_reconnect_attempts:
                    await asyncio.sleep(5)  # Wait 5 seconds before reconnecting
                else:
                    logger.error("Max reconnection attempts reached. SSE client disabled.")
                    break
    
    async def process_alert(self, alert_data: Dict[str, Any]):
        """Process incoming alert from SSE stream"""
        if not alert_data or not isinstance(alert_data, dict):
            return
            
        # Add received timestamp and store as the last alert
        enhanced_alert = {
            **alert_data,
            "received_at": datetime.now().isoformat()
        }
        
        logger.warning(f"🚨 NEW ALERT RECEIVED via SSE: {enhanced_alert.get('id')}")
        
        # Broadcast to connected VSCode extension clients
        await broadcast_alert_to_clients(enhanced_alert)
        
    def start_subscription(self):
        """Start the SSE subscription in the background"""
        if self.subscription_task is None or self.subscription_task.done():
            self.subscription_task = asyncio.create_task(self.subscribe())
            logger.info("🚀 Started SSE subscription task")

# Global subscriber instance
alert_subscriber = AlertSubscriber(WEBHOOK_URL, API_KEY)

async def broadcast_alert_to_clients(alert_data: Dict[str, Any]):
    """Broadcast alert to all connected VSCode extension clients"""
    global connected_clients
    
    if not connected_clients:
        logger.info("No connected clients to broadcast to")
        return
        
    disconnected_clients = set()
    broadcast_data = json.dumps(alert_data)
    
    for client_queue in connected_clients:
        try:
            await client_queue.put(f"data: {broadcast_data}\n\n")
        except Exception as e:
            logger.error(f"Error broadcasting to client: {e}")
            disconnected_clients.add(client_queue)
    
    # Remove disconnected clients
    connected_clients -= disconnected_clients
    logger.info(f"Broadcasted alert to {len(connected_clients)} clients")

async def sse_generator(request: Request):
    """SSE generator for VSCode extension clients"""
    global connected_clients
    
    client_queue = asyncio.Queue()
    connected_clients.add(client_queue)
    logger.info(f"New client connected. Total clients: {len(connected_clients)}")
    
    try:
        # Send initial connection message
        yield "data: {\"type\": \"connection\", \"message\": \"Connected to SSE Gateway\"}\n\n"
        
        # Send keep-alive messages and alert data
        while True:
            try:
                # Wait for data with timeout for keep-alive
                data = await asyncio.wait_for(client_queue.get(), timeout=30.0)
                yield data
            except asyncio.TimeoutError:
                # Send keep-alive message
                yield "data: keep-alive\n\n"
                
    except Exception as e:
        logger.error(f"SSE client disconnected: {e}")
    finally:
        connected_clients.discard(client_queue)
        logger.info(f"Client disconnected. Remaining clients: {len(connected_clients)}")

# Define lifespan handler
@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifespan handler"""
    logger.info("🚀 Starting alert subscription on app startup")
    alert_subscriber.start_subscription()
    yield
    logger.info("🛑 App shutting down")

# Create FastAPI app for SSE endpoint  
app = FastAPI(title="SSE Gateway for VSCode Extension", lifespan=lifespan)

# Add CORS middleware for VSCode extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/alerts-stream")
async def alerts_stream(request: Request):
    """SSE endpoint for VSCode extension"""
    return StreamingResponse(
        sse_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
        }
    )

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "SSE Gateway for VSCode Extension", "status": "active"}

if __name__ == "__main__":
    logger.info("🚀 Starting SSE Gateway Server for VSCode Extension")
    logger.info(f"🔗 Will connect to SSE webhook: {WEBHOOK_URL}")
    
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
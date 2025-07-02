from fastapi import WebSocket
from typing import Dict, Optional, Any
import logging
import json
from config import settings
from prometheus_client import Counter, Gauge
from redis_service import redis_service

# Set up logging
logger = logging.getLogger(__name__)

# Set up metrics
websocket_connections = Gauge(
    "websocket_connections_total", 
    "Number of active WebSocket connections",
    ["instance_id"]
)
websocket_messages = Counter(
    "websocket_messages_total", 
    "Number of WebSocket messages processed",
    ["instance_id", "direction"]  # direction: inbound or outbound
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, dict] = {}
        self.connection_count = 0
        
    async def connect(self, websocket: WebSocket, client_id: str, client_ip: str = None):
        await websocket.accept()
        
        # Store connection information including IP address
        connection_info = {
            "websocket": websocket,
            "client_id": client_id,
            "client_ip": client_ip,
            "user_id": redis_service.get_user_id(client_id, client_ip or "unknown")
        }
        
        self.active_connections[client_id] = connection_info
        self.connection_count += 1
        websocket_connections.labels(instance_id=settings.INSTANCE_ID).set(self.connection_count)
        
        # Store connection in Redis
        await redis_service.store_user_connection(
            connection_info["user_id"], 
            client_id, 
            client_ip or "unknown"
        )
        
        logger.info(f"Client {client_id} connected from {client_ip}. Total connections: {self.connection_count}")

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            self.connection_count -= 1
            websocket_connections.labels(instance_id=settings.INSTANCE_ID).set(self.connection_count)
            logger.info(f"Client {client_id} disconnected. Total connections: {self.connection_count}")

    async def send_personal_message(self, message: dict, client_id: str):
        if client_id in self.active_connections:
            connection_info = self.active_connections[client_id]
            websocket = connection_info["websocket"]
            user_id = connection_info["user_id"]
            
            websocket_messages.labels(instance_id=settings.INSTANCE_ID, direction="outbound").inc()
            
            # Store the message in Redis if it's a chat message
            if message.get("type") == "chat":
                await redis_service.store_message(message, user_id)
                
            await websocket.send_json(message)
            logger.debug(f"Message sent to client {client_id}")

    async def broadcast(self, message: dict):
        websocket_messages.labels(instance_id=settings.INSTANCE_ID, direction="outbound").inc(len(self.active_connections))
        
        # Store chat messages in Redis for each connected user
        if message.get("type") == "chat":
            sender_id = None
            # Try to find the sender's user_id if available
            sender_client_id = message.get("client_id")
            if sender_client_id and sender_client_id in self.active_connections:
                sender_id = self.active_connections[sender_client_id]["user_id"]
            
            # Store the message once in the global message history
            await redis_service.store_message(message, "global")
            
            # If this is from a user, store in their personal history too
            if sender_id:
                await redis_service.store_message(message, sender_id)
        
        for client_id, connection_info in self.active_connections.items():
            websocket = connection_info["websocket"]
            await websocket.send_json(message)
        
        logger.debug(f"Broadcast message sent to {len(self.active_connections)} clients")

    async def get_user_history(self, client_id: str, limit: int = 50) -> list:
        """Fetch message history for a specific user"""
        if client_id in self.active_connections:
            user_id = self.active_connections[client_id]["user_id"]
            return await redis_service.get_user_messages(user_id, limit)
        return []

    async def get_chat_history(self, limit: int = 50) -> list:
        """Fetch global chat history"""
        return await redis_service.get_recent_messages(limit)

    def get_connection_stats(self):
        return {
            "instance_id": settings.INSTANCE_ID,
            "active_connections": self.connection_count,
        }

# Create a global connection manager instance
manager = ConnectionManager()
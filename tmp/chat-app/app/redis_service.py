import json
import logging
import time
from datetime import datetime, timedelta
import redis.asyncio as aioredis  # Use redis.asyncio instead of aioredis
from typing import Dict, List, Optional, Any
from config import settings

logger = logging.getLogger(__name__)

class RedisService:
    def __init__(self):
        self.redis = None
        self.connection_initialized = False
    
    async def initialize(self):
        if not self.connection_initialized:
            try:
                self.redis = await aioredis.from_url(
                    settings.REDIS_URL,
                    password=settings.REDIS_PASSWORD,
                    encoding="utf-8",
                    decode_responses=True
                )
                self.connection_initialized = True
                logger.info(f"Connected to Redis at {settings.REDIS_HOST}")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {str(e)}")
                raise
    
    def get_user_id(self, client_id: str, client_ip: str) -> str:
        """
        Generate a unique user identifier from client ID and IP
        This allows tracking the same user across different connections
        """
        return f"{client_ip}_{client_id}"
    
    async def store_message(self, message: Dict[str, Any], user_id: str) -> bool:
        """
        Store a message in Redis for a specific user
        Messages are stored in a sorted set with timestamp as score for chronological access
        """
        await self.initialize()
        
        try:
            # Add timestamp if not present
            if "timestamp" not in message:
                message["timestamp"] = time.time()
            
            # Serialize the message
            message_str = json.dumps(message)
            
            # Get a pipeline for atomic operations
            pipeline = self.redis.pipeline()
            
            # Add the message to the user's message list (sorted set)
            user_key = f"user:{user_id}:messages"
            
            # Store the message itself using the timestamp as score
            pipeline.zadd(user_key, {message_str: float(message["timestamp"])})
            
            # Set expiration on the key if it doesn't exist
            pipeline.expire(user_key, timedelta(days=settings.MESSAGE_RETENTION_DAYS).total_seconds())
            
            # Trim to max message count if needed
            pipeline.zremrangebyrank(user_key, 0, -settings.MAX_MESSAGES_PER_USER-1)
            
            # Also add to the global message history
            global_key = "messages:global"
            pipeline.zadd(global_key, {message_str: float(message["timestamp"])})
            pipeline.expire(global_key, timedelta(days=settings.MESSAGE_RETENTION_DAYS).total_seconds())
            pipeline.zremrangebyrank(global_key, 0, -10000)  # Keep the last 10000 messages globally
            
            # Execute all commands
            await pipeline.execute()
            
            return True
        except Exception as e:
            logger.error(f"Failed to store message: {str(e)}")
            return False
    
    async def get_user_messages(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieve the most recent messages for a specific user
        """
        await self.initialize()
        
        try:
            user_key = f"user:{user_id}:messages"
            
            # Get messages from newest to oldest (reverse chronological order)
            message_data = await self.redis.zrevrange(user_key, 0, limit - 1)
            
            # Parse JSON strings back to dictionaries
            messages = [json.loads(msg) for msg in message_data]
            
            return messages
        except Exception as e:
            logger.error(f"Failed to get user messages: {str(e)}")
            return []
    
    async def get_recent_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieve the most recent global messages
        """
        await self.initialize()
        
        try:
            global_key = "messages:global"
            
            # Get messages from newest to oldest
            message_data = await self.redis.zrevrange(global_key, 0, limit - 1)
            
            # Parse JSON strings back to dictionaries
            messages = [json.loads(msg) for msg in message_data]
            
            return messages
        except Exception as e:
            logger.error(f"Failed to get recent messages: {str(e)}")
            return []
    
    async def store_user_connection(self, user_id: str, client_id: str, ip_address: str) -> None:
        """
        Track user connection information
        """
        await self.initialize()
        
        try:
            user_connection_key = f"user:{user_id}:connections"
            connection_data = {
                "client_id": client_id,
                "ip_address": ip_address,
                "connected_at": time.time(),
                "instance_id": settings.INSTANCE_ID
            }
            
            await self.redis.hset(user_connection_key, client_id, json.dumps(connection_data))
            await self.redis.expire(user_connection_key, timedelta(days=1).total_seconds())
        except Exception as e:
            logger.error(f"Failed to store user connection: {str(e)}")

# Create a global redis service instance
redis_service = RedisService()

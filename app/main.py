import asyncio
import logging
import time
import uuid
import uvicorn
import json
from typing import Dict, Any, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Gauge
import redis.asyncio as redis

from websocket_manager import manager
from background_tasks import task_manager
from redis_service import redis_service
from config import settings
from models import TaskRequest, InstanceInfo

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize metrics
http_requests = Counter("http_requests_total", "HTTP requests count", ["method", "endpoint", "status_code"])
startup_time = time.time()
uptime = Gauge("app_uptime_seconds", "Application uptime in seconds")

# Redis Pub/Sub channels
CHAT_CHANNEL = "chat_messages"
SYSTEM_CHANNEL = "system_messages"

# Redis pub/sub client
pubsub_redis = None



# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="A WebSocket scaling demonstration with FastAPI",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    global pubsub_redis
    logger.info(f"Starting up {settings.APP_NAME}")
    logger.info(f"Instance ID: {settings.INSTANCE_ID}")
    
    # Initialize Redis connection
    try:
        await redis_service.initialize()
        logger.info("Redis connection established")
        
        # Initialize Redis pub/sub
        pubsub_redis = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True
        )
        
        # Start listening to Redis channels
        asyncio.create_task(redis_listener())
        logger.info("Redis pub/sub listener started")
        
    except Exception as e:
        logger.error(f"Failed to initialize Redis: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info(f"Shutting down {settings.APP_NAME}")
    if pubsub_redis:
        await pubsub_redis.close()

async def redis_listener():
    """Listen to Redis pub/sub channels and broadcast to WebSocket clients"""
    try:
        pubsub = pubsub_redis.pubsub()
        await pubsub.subscribe(CHAT_CHANNEL, SYSTEM_CHANNEL)
        
        logger.info(f"Subscribed to Redis channels: {CHAT_CHANNEL}, {SYSTEM_CHANNEL}")
        
        async for message in pubsub.listen():
            if message['type'] == 'message':
                try:
                    data = json.loads(message['data'])
                    # Don't re-broadcast messages from the same instance
                    if data.get('source_instance') != settings.INSTANCE_ID:
                        await manager.broadcast(data)
                        logger.debug(f"Broadcasted message from Redis: {data['type']}")
                except json.JSONDecodeError:
                    logger.error(f"Failed to decode Redis message: {message['data']}")
                except Exception as e:
                    logger.error(f"Error processing Redis message: {e}")
                    
    except Exception as e:
        logger.error(f"Redis listener error: {e}")

async def publish_to_redis(channel: str, data: dict):
    """Publish message to Redis channel"""
    try:
        # Add source instance to avoid re-broadcasting
        data['source_instance'] = settings.INSTANCE_ID
        message = json.dumps(data)
        await pubsub_redis.publish(channel, message)
        logger.debug(f"Published to Redis channel {channel}: {data['type']}")
    except Exception as e:
        logger.error(f"Failed to publish to Redis: {e}")

# Root endpoint serving frontend
@app.get("/")
async def get_root():
    return FileResponse("static/index.html")

# Health check endpoint
@app.get("/health")
async def health_check():
    http_requests.labels(method="GET", endpoint="/health", status_code=200).inc()
    return {"status": "healthy", "instance_id": settings.INSTANCE_ID}

# Instance information endpoint
@app.get("/instance", response_model=InstanceInfo)
async def instance_info():
    http_requests.labels(method="GET", endpoint="/instance", status_code=200).inc()
    uptime_value = time.time() - startup_time
    uptime.set(uptime_value)
    
    return {
        "instance_id": settings.INSTANCE_ID,
        "uptime": uptime_value,
        "connection_count": manager.connection_count,
        "active_tasks": task_manager.active_task_count
    }

# Metrics endpoint
@app.get("/metrics")
async def metrics():
    http_requests.labels(method="GET", endpoint="/metrics", status_code=200).inc()
    return PlainTextResponse(generate_latest().decode(), media_type=CONTENT_TYPE_LATEST)

# Helper function to get client IP
def get_client_ip(websocket: WebSocket) -> str:
    """Extract client IP address from WebSocket connection"""
    client = websocket.client
    if client:
        host = client.host
        return host if host else "unknown"
    return "unknown"

# WebSocket endpoint
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    # Get the client's IP address
    client_ip = get_client_ip(websocket)
    
    # Connect with IP information
    await manager.connect(websocket, client_id, client_ip)
    
    # Get user message history
    user_history = await manager.get_user_history(client_id, 20)
    
    # Send initial connection info
    await manager.send_personal_message({
        "type": "connection_info",
        "instance_id": settings.INSTANCE_ID,
        "client_id": client_id,
        "connection_count": manager.connection_count,
        "client_ip": client_ip
    }, client_id)
    
    # Send message history if available
    if user_history:
        await manager.send_personal_message({
            "type": "message_history",
            "messages": user_history,
            "source": "user_history"
        }, client_id)
    else:
        # If no user history, send global history
        global_history = await manager.get_chat_history(20)
        if global_history:
            await manager.send_personal_message({
                "type": "message_history",
                "messages": global_history,
                "source": "global_history"
            }, client_id)
    
    try:
        while True:
            # Wait for messages from the client
            data = await websocket.receive_json()
            
            message_type = data.get("type", "chat")
            
            if message_type == "chat":
                # Process chat message
                message = {
                    "type": "chat",
                    "client_id": client_id,
                    "client_ip": client_ip,  # Include client IP in the message
                    "content": data.get("content", ""),
                    "instance_id": settings.INSTANCE_ID,
                    "timestamp": data.get("timestamp") or time.time()
                }
                
                # Broadcast message to local clients first
                await manager.broadcast(message)
                
                # Publish to Redis for other instances
                await publish_to_redis(CHAT_CHANNEL, message)
                await publish_to_redis(CHAT_CHANNEL, message)  # Publish to Redis channel
                

            elif message_type == "task_request":
                # Handle background task request
                task_id, task_info = await task_manager.create_task(client_id)
                
                # Notify client that task was created
                await manager.send_personal_message({
                    "type": "task_created",
                    "task_id": task_id,
                    "details": task_info
                }, client_id)
                
                # Run the task in the background
                asyncio.create_task(process_background_task(task_id, client_id))
                
            elif message_type == "get_history":
                # Request for message history
                limit = data.get("limit", 50)
                history_type = data.get("history_type", "user")
                
                if history_type == "user":
                    messages = await manager.get_user_history(client_id, limit)
                else:
                    messages = await manager.get_chat_history(limit)
                
                await manager.send_personal_message({
                    "type": "message_history",
                    "messages": messages,
                    "source": history_type + "_history"
                }, client_id)
                
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        disconnect_message = {
            "type": "system",
            "content": f"Client #{client_id} left the chat",
            "instance_id": settings.INSTANCE_ID
        }
        
        # Broadcast locally and to other instances
        await manager.broadcast(disconnect_message)
        await publish_to_redis(SYSTEM_CHANNEL, disconnect_message)

async def process_background_task(task_id: str, client_id: str):
    # Run the task
    task_id, task_result = await task_manager.run_task(task_id)
    
    # Notify client when task is complete
    if task_result:
        await manager.send_personal_message({
            "type": "task_completed",
            "task_id": task_id,
            "details": task_result
        }, client_id)

# Background task endpoint
@app.post("/tasks")
async def create_task(request: TaskRequest, background_tasks: BackgroundTasks):
    http_requests.labels(method="POST", endpoint="/tasks", status_code=200).inc()
    
    client_id = request.client_id
    task_id, task_info = await task_manager.create_task(client_id)
    
    # Run the task in the background
    background_tasks.add_task(process_background_task, task_id, client_id)
    
    return {"task_id": task_id, "details": task_info}

# Chat history endpoint
@app.get("/chat/history")
async def get_chat_history(request: Request, limit: int = 50, history_type: str = "global"):
    http_requests.labels(method="GET", endpoint="/chat/history", status_code=200).inc()
    
    client_ip = request.client.host if request.client else "unknown"
    client_id = request.query_params.get("client_id", "api-client")
    
    if history_type == "global":
        messages = await redis_service.get_recent_messages(limit)
    else:
        user_id = redis_service.get_user_id(client_id, client_ip)
        messages = await redis_service.get_user_messages(user_id, limit)
    
    return {
        "messages": messages,
        "count": len(messages),
        "history_type": history_type
    }



if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
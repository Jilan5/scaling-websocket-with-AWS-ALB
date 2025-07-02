import os
import uuid
import socket

class Settings:
    # Generate a persistent instance ID (simulating different EC2 instances)
    INSTANCE_ID = os.getenv("INSTANCE_ID", f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}")
    
    # Application settings
    APP_NAME = "FastAPI WebSocket Scaling Demo"
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    
    # CORS settings
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
    
    # Prometheus metrics path
    METRICS_PATH = "/metrics"
    
    # Background task delay range (seconds)
    MAX_TASK_DELAY = 15
    MIN_TASK_DELAY = 5
    
    # Redis configuration - supports both local and AWS ElastiCache
    REDIS_HOST = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
    
    # For AWS ElastiCache, use the cluster endpoint
    if REDIS_PASSWORD:
        REDIS_URL = os.getenv("REDIS_URL", f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")
    else:
        REDIS_URL = os.getenv("REDIS_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")
    
    # AWS specific settings
    AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    
    # Message storage settings
    MESSAGE_RETENTION_DAYS = 7
    MAX_MESSAGES_PER_USER = 1000

settings = Settings()
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
import time

class ChatMessage(BaseModel):
    client_id: str
    content: str
    client_ip: Optional[str] = None
    instance_id: Optional[str] = None
    timestamp: Union[str, float] = Field(default_factory=lambda: time.time())
    type: str = "chat"
    
class SystemMessage(BaseModel):
    content: str
    instance_id: Optional[str] = None
    timestamp: Union[str, float] = Field(default_factory=lambda: time.time())
    type: str = "system"

class MessageHistoryRequest(BaseModel):
    limit: int = 50
    client_id: str
    history_type: str = "user"  # "user" or "global"
    
class MessageHistoryResponse(BaseModel):
    messages: List[Dict[str, Any]]
    count: int
    history_type: str
    
class TaskRequest(BaseModel):
    client_id: str

class InstanceInfo(BaseModel):
    instance_id: str
    uptime: float
    connection_count: int
    active_tasks: int
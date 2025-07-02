import asyncio
import random
import uuid
import logging
from typing import Dict, Any, Tuple
from datetime import datetime
from prometheus_client import Histogram
from config import settings

logger = logging.getLogger(__name__)

# Track task execution time
task_execution_time = Histogram(
    "background_task_execution_seconds",
    "Time spent executing background tasks",
    ["instance_id"]
)

class TaskManager:
    def __init__(self):
        self.tasks = {}
        self.active_task_count = 0

    async def create_task(self, client_id: str) -> Tuple[str, Dict[str, Any]]:
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        duration = random.randint(settings.MIN_TASK_DELAY, settings.MAX_TASK_DELAY)
        
        self.tasks[task_id] = {
            "client_id": client_id,
            "status": "running",
            "duration": duration,
            "started_at": datetime.utcnow().isoformat(),
            "instance_id": settings.INSTANCE_ID
        }
        self.active_task_count += 1
        
        logger.info(f"Task {task_id} created for client {client_id}, duration: {duration}s")
        
        # Return the task immediately but process it in the background
        return task_id, self.tasks[task_id]
        
    async def run_task(self, task_id: str) -> Tuple[str, Dict[str, Any]]:
        try:
            task = self.tasks.get(task_id)
            if not task:
                logger.error(f"Task {task_id} not found")
                return task_id, {"error": "Task not found"}
                
            # Simulate work with a timer
            with task_execution_time.labels(instance_id=settings.INSTANCE_ID).time():
                logger.info(f"Task {task_id} running for {task['duration']}s")
                await asyncio.sleep(task['duration'])
            
            # Update task status
            self.tasks[task_id]["status"] = "completed"
            self.tasks[task_id]["completed_at"] = datetime.utcnow().isoformat()
            self.active_task_count -= 1
            
            logger.info(f"Task {task_id} completed")
            return task_id, self.tasks[task_id]
            
        except Exception as e:
            logger.error(f"Error in task {task_id}: {str(e)}")
            if task_id in self.tasks:
                self.tasks[task_id]["status"] = "failed"
                self.tasks[task_id]["error"] = str(e)
                self.active_task_count -= 1
            return task_id, self.tasks.get(task_id, {"error": str(e)})

    def get_task_stats(self):
        return {
            "instance_id": settings.INSTANCE_ID,
            "active_tasks": self.active_task_count,
            "total_tasks": len(self.tasks)
        }

# Create a global task manager instance
task_manager = TaskManager()
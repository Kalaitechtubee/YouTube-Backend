import asyncio
from typing import Dict, Any
from src.core.interfaces.queue_manager import IQueueManager
from src.workers.jobs import cancel_task

# Shared in-memory queue
_async_queue: asyncio.Queue = asyncio.Queue()

class InMemoryQueueManager(IQueueManager):
    async def enqueue_job(self, task_id: str, payload: Dict[str, Any]) -> str:
        payload["task_id"] = task_id
        await _async_queue.put(payload)
        return task_id

    async def cancel_job(self, task_id: str) -> bool:
        cancel_task(task_id)
        return True

def get_shared_queue() -> asyncio.Queue:
    return _async_queue

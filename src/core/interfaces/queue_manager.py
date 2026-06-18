from abc import ABC, abstractmethod
from typing import Any, Dict

class IQueueManager(ABC):
    @abstractmethod
    async def enqueue_job(self, task_id: str, payload: Dict[str, Any]) -> str:
        """Add task job payload to background processing queue."""
        pass

    @abstractmethod
    async def cancel_job(self, task_id: str) -> bool:
        """Cancel a running task or pull it from the queue."""
        pass

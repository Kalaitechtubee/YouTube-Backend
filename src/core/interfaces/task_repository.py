import uuid
from abc import ABC, abstractmethod
from typing import List, Optional
from src.core.entities.task import DownloadTask

class ITaskRepository(ABC):
    @abstractmethod
    async def save(self, task: DownloadTask) -> DownloadTask:
        pass

    @abstractmethod
    async def get_by_id(self, task_id: uuid.UUID) -> Optional[DownloadTask]:
        pass

    @abstractmethod
    async def delete(self, task_id: uuid.UUID) -> bool:
        pass

    @abstractmethod
    async def list_history(self, limit: int = 50, offset: int = 0) -> List[DownloadTask]:
        pass

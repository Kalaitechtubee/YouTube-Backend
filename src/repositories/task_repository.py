import uuid
from typing import List, Optional
from sqlalchemy.orm import Session
from src.core.entities.task import DownloadTask, TaskStatus
from src.core.interfaces.task_repository import ITaskRepository
from src.database.models import DownloadTaskModel

class SQLAlchemyTaskRepository(ITaskRepository):
    def __init__(self, db: Session):
        self.db = db

    def _to_entity(self, model: DownloadTaskModel) -> DownloadTask:
        return DownloadTask(
            id=uuid.UUID(model.id),
            url=model.url,
            provider_name=model.provider_name,
            status=TaskStatus(model.status),
            title=model.title,
            thumbnail_url=model.thumbnail_url,
            file_path=model.file_path,
            file_size=model.file_size,
            progress=model.progress,
            download_speed=model.download_speed,
            eta=model.eta,
            worker_id=model.worker_id,
            error_message=model.error_message,
            created_at=model.created_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
            expires_at=model.expires_at
        )

    def _to_model(self, entity: DownloadTask) -> DownloadTaskModel:
        return DownloadTaskModel(
            id=str(entity.id),
            url=entity.url,
            provider_name=entity.provider_name,
            status=entity.status.value,
            title=entity.title,
            thumbnail_url=entity.thumbnail_url,
            file_path=entity.file_path,
            file_size=entity.file_size,
            progress=entity.progress,
            download_speed=entity.download_speed,
            eta=entity.eta,
            worker_id=entity.worker_id,
            error_message=entity.error_message,
            created_at=entity.created_at,
            started_at=entity.started_at,
            completed_at=entity.completed_at,
            expires_at=entity.expires_at
        )

    async def save(self, task: DownloadTask) -> DownloadTask:
        model = self.db.query(DownloadTaskModel).filter(DownloadTaskModel.id == str(task.id)).first()
        if not model:
            model = self._to_model(task)
            self.db.add(model)
        else:
            # Update fields
            model.status = task.status.value
            model.title = task.title
            model.thumbnail_url = task.thumbnail_url
            model.file_path = task.file_path
            model.file_size = task.file_size
            model.progress = task.progress
            model.download_speed = task.download_speed
            model.eta = task.eta
            model.worker_id = task.worker_id
            model.error_message = task.error_message
            model.started_at = task.started_at
            model.completed_at = task.completed_at
            model.expires_at = task.expires_at

        self.db.commit()
        self.db.refresh(model)
        return self._to_entity(model)

    async def get_by_id(self, task_id: uuid.UUID) -> Optional[DownloadTask]:
        model = self.db.query(DownloadTaskModel).filter(DownloadTaskModel.id == str(task_id)).first()
        if model:
            return self._to_entity(model)
        return None

    async def delete(self, task_id: uuid.UUID) -> bool:
        model = self.db.query(DownloadTaskModel).filter(DownloadTaskModel.id == str(task_id)).first()
        if model:
            self.db.delete(model)
            self.db.commit()
            return True
        return False

    async def list_history(self, limit: int = 50, offset: int = 0) -> List[DownloadTask]:
        models = self.db.query(DownloadTaskModel).order_by(
            DownloadTaskModel.created_at.desc()
        ).limit(limit).offset(offset).all()
        return [self._to_entity(m) for m in models]

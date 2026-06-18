from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid

class TaskStatus(str, Enum):
    QUEUED = "QUEUED"
    INITIALIZING = "INITIALIZING"
    FETCHING_METADATA = "FETCHING_METADATA"
    FETCHING_STREAMS = "FETCHING_STREAMS"
    DOWNLOADING_VIDEO = "DOWNLOADING_VIDEO"
    DOWNLOADING_AUDIO = "DOWNLOADING_AUDIO"
    MERGING = "MERGING"
    VERIFYING = "VERIFYING"
    READY = "READY"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"

class DownloadTask(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    url: str
    provider_name: str
    status: TaskStatus = TaskStatus.QUEUED
    title: Optional[str] = None
    thumbnail_url: Optional[str] = None
    file_path: Optional[str] = None
    file_size: int = 0
    progress: float = 0.0
    download_speed: Optional[str] = "0 KB/s"
    eta: Optional[str] = "00:00:00"
    worker_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

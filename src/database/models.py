import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Boolean
from src.database.connection import Base

class DownloadTaskModel(Base):
    __tablename__ = "download_tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    url = Column(String(2048), nullable=False)
    provider_name = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False, default="QUEUED")
    title = Column(String(512), nullable=True)
    thumbnail_url = Column(String(2048), nullable=True)
    file_path = Column(String(1024), nullable=True)
    file_size = Column(Integer, default=0)
    progress = Column(Float, default=0.0)
    download_speed = Column(String(50), default="0 KB/s")
    eta = Column(String(50), default="00:00:00")
    worker_id = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

class ProviderModel(Base):
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    rate_limit_hits = Column(Integer, default=0)
    cookies_updated_at = Column(DateTime, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)

class WorkerLogsModel(Base):
    __tablename__ = "worker_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    worker_id = Column(String(100), nullable=False)
    task_id = Column(String(36), nullable=True)
    log_level = Column(String(10), nullable=False)
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

class DownloadOptionModel(Base):
    __tablename__ = "download_options"

    id = Column(String(36), primary_key=True)
    url = Column(String(2048), nullable=False)
    video_stream_url = Column(String(2048), nullable=True)
    audio_stream_url = Column(String(2048), nullable=True)
    format = Column(String(10), nullable=False)
    resolution = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


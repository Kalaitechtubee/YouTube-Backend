import uuid
import os
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List

from src.database.connection import get_db
from src.database.models import DownloadOptionModel
from src.repositories.task_repository import SQLAlchemyTaskRepository
from src.services.provider_resolver import ProviderResolver
from src.services.queue_manager import InMemoryQueueManager
from src.services.media_formatter import MediaFormatter
from src.core.entities.task import DownloadTask, TaskStatus
from src.api.schemas import ParseRequest, DownloadRequest, TaskStatusResponse

router = APIRouter(prefix="/media", tags=["media"])
queue_manager = InMemoryQueueManager()
provider_resolver = ProviderResolver()

@router.post("/parse")
async def parse_media(request: ParseRequest, db: Session = Depends(get_db)):
    try:
        provider = provider_resolver.resolve(request.url)
        metadata = await provider.extract_metadata(request.url)
        
        # Format using the production-grade formatter
        formatter = MediaFormatter(db)
        clean_response = formatter.format_metadata(metadata, request.url)
        return clean_response
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/download", status_code=status.HTTP_202_ACCEPTED)
async def queue_download(request: DownloadRequest, db: Session = Depends(get_db)):
    repo = SQLAlchemyTaskRepository(db)
    
    # 1. Resolve secure download_id configuration from DB
    option = db.query(DownloadOptionModel).filter(DownloadOptionModel.id == request.download_id).first()
    if not option:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Download option not found or expired. Please parse the media again."
        )

    # 2. Resolve provider to validate url
    try:
        provider = provider_resolver.resolve(option.url)
        provider_name = provider.__class__.__name__.replace("Provider", "").lower()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    # 3. Create domain entity
    task = DownloadTask(
        url=option.url,
        provider_name=provider_name,
        status=TaskStatus.QUEUED
    )

    # 4. Save to database
    await repo.save(task)

    # 5. Enqueue in background queue
    payload = {
        "url": option.url,
        "video_stream_url": option.video_stream_url,
        "audio_stream_url": option.audio_stream_url,
        "format": option.format,
        "resolution": option.resolution
    }
    await queue_manager.enqueue_job(str(task.id), payload)

    return {
        "task_id": str(task.id),
        "status": task.status.value,
        "created_at": task.created_at
    }

@router.get("/task/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str, db: Session = Depends(get_db)):
    repo = SQLAlchemyTaskRepository(db)
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid task ID format. Must be UUID."
        )

    task = await repo.get_by_id(task_uuid)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    return TaskStatusResponse(
        task_id=str(task.id),
        status=task.status.value,
        progress=task.progress,
        download_speed=task.download_speed or "0 KB/s",
        eta=task.eta or "00:00:00",
        title=task.title,
        thumbnail_url=task.thumbnail_url,
        error_message=task.error_message
    )

@router.get("/file/{task_id}")
async def get_task_file(task_id: str, db: Session = Depends(get_db)):
    repo = SQLAlchemyTaskRepository(db)
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid task ID format."
        )

    task = await repo.get_by_id(task_uuid)
    if not task or task.status != TaskStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task file is not ready or failed."
        )

    file_path = task.file_path
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stitched output file not found on disk."
        )

    filename = os.path.basename(file_path)
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream"
    )

@router.delete("/task/{task_id}")
async def cancel_task_endpoint(task_id: str, db: Session = Depends(get_db)):
    repo = SQLAlchemyTaskRepository(db)
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid task ID format."
        )

    task = await repo.get_by_id(task_uuid)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found."
        )

    # Trigger cancellation
    await queue_manager.cancel_job(str(task_uuid))
    
    # Update state
    task.status = TaskStatus.FAILED
    task.error_message = "Task cancelled by user request."
    await repo.save(task)

    return {"message": "Task cancellation signal sent."}

@router.get("/history")
async def list_task_history(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    repo = SQLAlchemyTaskRepository(db)
    history = await repo.list_history(limit=limit, offset=offset)
    return [
        {
            "task_id": str(t.id),
            "url": t.url,
            "provider": t.provider_name,
            "status": t.status.value,
            "title": t.title,
            "progress": t.progress,
            "file_size": t.file_size,
            "created_at": t.created_at
        }
        for t in history
    ]

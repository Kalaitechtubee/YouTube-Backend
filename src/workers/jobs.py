import os
import uuid
import time
from datetime import datetime, timedelta
from typing import Optional, Set
from src.core.entities.task import TaskStatus
from src.database.connection import SessionLocal
from src.database.models import DownloadTaskModel
from src.repositories.task_repository import SQLAlchemyTaskRepository
from src.services.provider_resolver import ProviderResolver
from src.services.ffmpeg_merger import FFmpegMerger

# Thread-safe set of cancelled task IDs
CANCELLED_TASKS: Set[str] = set()

def cancel_task(task_id: str):
    CANCELLED_TASKS.add(task_id)

def is_task_cancelled(task_id: str) -> bool:
    return task_id in CANCELLED_TASKS

async def run_download_job(
    task_id_str: str,
    url: str,
    video_stream_url: Optional[str],
    audio_stream_url: Optional[str],
    format_ext: str,
    resolution: Optional[str] = None
) -> None:
    db = SessionLocal()
    repo = SQLAlchemyTaskRepository(db)
    task_id = uuid.UUID(task_id_str)
    
    # Initialize dirs
    base_dir = os.getcwd()
    storage_dir = os.path.join(base_dir, "storage")
    temp_dir = os.path.join(storage_dir, "temp")
    downloads_dir = os.path.join(storage_dir, "downloads")
    
    for d in [temp_dir, downloads_dir]:
        os.makedirs(d, exist_ok=True)

    task = await repo.get_by_id(task_id)
    if not task:
        db.close()
        return

    try:
        # Step 1: INITIALIZING
        task.status = TaskStatus.INITIALIZING
        task.started_at = datetime.utcnow()
        await repo.save(task)
        
        # Step 2: Resolve Provider & Fetch Title/Metadata if missing
        resolver = ProviderResolver()
        provider = resolver.resolve(url)
        
        task.status = TaskStatus.FETCHING_METADATA
        await repo.save(task)
        
        metadata = await provider.extract_metadata(url)
        task.title = metadata.title
        task.thumbnail_url = metadata.thumbnail_url
        await repo.save(task)

        # Sanitize filename
        safe_title = "".join([c if c.isalnum() or c in " .-_" else "_" for c in metadata.title]).strip()
        if not safe_title:
            safe_title = "download"
        
        # Setup paths
        unique_suffix = str(uuid.uuid4())[:8]
        temp_video_path = os.path.join(temp_dir, f"video_{unique_suffix}.tmp")
        temp_audio_path = os.path.join(temp_dir, f"audio_{unique_suffix}.tmp")
        
        output_filename = f"{safe_title}_{unique_suffix}.{format_ext}"
        final_output_path = os.path.join(downloads_dir, output_filename)

        # Progress reporting wrapper
        def make_progress_callback(status_state: TaskStatus):
            def cb(downloaded: int, total: int, speed: float, eta_str: str):
                if is_task_cancelled(task_id_str):
                    raise InterruptedError("Aborted by user.")
                
                # Check DB task state and update
                task.status = status_state
                task.download_speed = f"{speed:.2f} MB/s" if speed > 0 else "0 KB/s"
                task.eta = eta_str
                if total > 0:
                    task.progress = min(99.0, (downloaded / total) * 100)
                
                # Update task progress in the database synchronously
                model = db.query(DownloadTaskModel).filter(DownloadTaskModel.id == task_id_str).first()
                if model:
                    model.status = task.status.value
                    model.download_speed = task.download_speed
                    model.eta = task.eta
                    model.progress = task.progress
                    db.commit()
            return cb

        # Download Video Stream
        if video_stream_url:
            task.status = TaskStatus.DOWNLOADING_VIDEO
            await repo.save(task)
            await provider.download_stream(
                stream_url=video_stream_url,
                destination_path=temp_video_path,
                progress_callback=make_progress_callback(TaskStatus.DOWNLOADING_VIDEO),
            )

        # Download Audio Stream
        if audio_stream_url:
            task.status = TaskStatus.DOWNLOADING_AUDIO
            await repo.save(task)
            await provider.download_stream(
                stream_url=audio_stream_url,
                destination_path=temp_audio_path,
                progress_callback=make_progress_callback(TaskStatus.DOWNLOADING_AUDIO),
            )

        # Merge or Copy
        if is_task_cancelled(task_id_str):
            raise InterruptedError("Aborted by user.")

        task.status = TaskStatus.MERGING
        task.progress = 95.0
        await repo.save(task)

        merger = FFmpegMerger()
        
        if video_stream_url and audio_stream_url:
            # Stitch them
            merger.merge_video_audio(temp_video_path, temp_audio_path, final_output_path)
        elif video_stream_url:
            # Move single video
            if os.path.exists(final_output_path):
                os.remove(final_output_path)
            os.rename(temp_video_path, final_output_path)
        elif audio_stream_url:
            # Move single audio
            if os.path.exists(final_output_path):
                os.remove(final_output_path)
            os.rename(temp_audio_path, final_output_path)

        # Embedding details
        task.status = TaskStatus.VERIFYING
        await repo.save(task)
        
        # Cleanup temp fragments
        for p in [temp_video_path, temp_audio_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except:
                    pass

        # Finalizing status
        task.status = TaskStatus.READY
        task.progress = 100.0
        task.download_speed = "0 KB/s"
        task.eta = "00:00:00"
        task.file_path = final_output_path
        task.file_size = os.path.getsize(final_output_path) if os.path.exists(final_output_path) else 0
        task.completed_at = datetime.utcnow()
        # Tasks expire in 2 hours
        task.expires_at = datetime.utcnow() + timedelta(hours=2)
        await repo.save(task)

    except Exception as e:
        # Update state to FAILED
        task.status = TaskStatus.FAILED
        task.error_message = str(e)
        task.completed_at = datetime.utcnow()
        await repo.save(task)

        # Cleanup paths
        for p in [temp_video_path, temp_audio_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except:
                    pass
    finally:
        # Delete task cancellation registration
        CANCELLED_TASKS.discard(task_id_str)
        db.close()

import asyncio
import logging
from src.services.queue_manager import get_shared_queue
from src.workers.jobs import run_download_job

logger = logging.getLogger("worker")

async def start_worker_loop():
    queue = get_shared_queue()
    logger.info("Background asyncio Task Worker started.")
    print("Background asyncio Task Worker started.")

    while True:
        try:
            payload = await queue.get()
            task_id = payload.get("task_id")
            url = payload.get("url")
            video_stream_url = payload.get("video_stream_url")
            audio_stream_url = payload.get("audio_stream_url")
            format_ext = payload.get("format", "mp4")
            resolution = payload.get("resolution")

            logger.info(f"Worker picked up task: {task_id}")
            
            # Execute concurrently via asyncio.create_task
            asyncio.create_task(
                run_download_job(
                    task_id_str=task_id,
                    url=url,
                    video_stream_url=video_stream_url,
                    audio_stream_url=audio_stream_url,
                    format_ext=format_ext,
                    resolution=resolution
                )
            )

            queue.task_done()
        except asyncio.CancelledError:
            logger.info("Worker loop cancelled.")
            break
        except Exception as e:
            logger.error(f"Worker iteration exception: {str(e)}")
            await asyncio.sleep(1)

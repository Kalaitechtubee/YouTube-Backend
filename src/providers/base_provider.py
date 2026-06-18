from abc import ABC, abstractmethod
from typing import List, Optional, Callable
from src.core.entities.media import MediaMetadata, MediaStream

class BaseProvider(ABC):
    @abstractmethod
    def validate_url(self, url: str) -> bool:
        """Verify that the provided URL belongs to this provider and is properly formatted."""
        pass

    @abstractmethod
    async def extract_metadata(self, url: str) -> MediaMetadata:
        """Extract media title, duration, streams, thumbnails, etc. from source."""
        pass

    @abstractmethod
    async def download_stream(
        self, 
        stream_url: str, 
        destination_path: str, 
        progress_callback: Optional[Callable[[int, int, float, str], None]] = None
    ) -> None:
        """
        Download a single video or audio stream chunk-by-chunk.
        progress_callback signature: (bytes_downloaded, total_bytes, speed_mbps, eta_str)
        """
        pass

    def get_subtitles(self, url: str) -> Optional[List[dict]]:
        """Optional: Fetch closed captions/subtitles."""
        return None

    def get_chapters(self, url: str) -> Optional[List[dict]]:
        """Optional: Fetch chapter divisions of the media."""
        return None

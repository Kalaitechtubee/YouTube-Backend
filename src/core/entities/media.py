from typing import List, Optional
from pydantic import BaseModel, Field

class MediaStream(BaseModel):
    url: str
    resolution: Optional[str] = None  # e.g., '1080p', '720p', 'Audio'
    quality: Optional[str] = None     # e.g., '320kbps', '128kbps'
    extension: str                    # e.g., 'mp4', 'm4a', 'webm'
    filesize: Optional[str] = "N/A"
    filesize_bytes: Optional[int] = 0
    has_video: bool = True
    has_audio: bool = True
    audio_url: Optional[str] = None   # For video streams requiring adaptive merging
    codec: Optional[str] = None
    fps: Optional[int] = None
    hdr: Optional[bool] = False
    channels: Optional[int] = None
    sample_rate: Optional[str] = None

class MediaMetadata(BaseModel):
    title: str
    thumbnail_url: str
    duration: str                     # e.g., '3:45'
    duration_seconds: int
    provider: str                     # e.g., 'youtube', 'instagram'
    streams: List[MediaStream] = Field(default_factory=list)
    is_carousel: bool = False
    carousel_media: List['MediaMetadata'] = Field(default_factory=list)
    subtitles: List[dict] = Field(default_factory=list)

# Re-update references for self-referential Pydantic model
MediaMetadata.model_rebuild()

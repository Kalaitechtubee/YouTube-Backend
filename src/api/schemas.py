from pydantic import BaseModel, Field
from typing import Optional, List

class ParseRequest(BaseModel):
    url: str = Field(..., description="The media URL to parse (YouTube, Instagram, etc.)")

class DownloadRequest(BaseModel):
    download_id: str = Field(..., description="The generated download ID for the selected stream")

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: float
    download_speed: str
    eta: str
    title: Optional[str] = None
    thumbnail_url: Optional[str] = None
    error_message: Optional[str] = None

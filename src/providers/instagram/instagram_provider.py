import os
import re
from typing import List, Optional, Callable
import yt_dlp
from src.providers.base_provider import BaseProvider
from src.core.entities.media import MediaMetadata, MediaStream
from src.utils.downloader_client import DownloaderClient

class InstagramProvider(BaseProvider):
    def __init__(self, cookies_file_path: Optional[str] = None):
        self.cookies_file_path = cookies_file_path
        # Look for default cookies.txt in config directory if not provided
        if not self.cookies_file_path:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            default_cookies = os.path.join(base_dir, "config", "cookies", "instagram_cookies.txt")
            if os.path.exists(default_cookies):
                self.cookies_file_path = default_cookies
            else:
                # Fallback to general cookies.txt in current working dir
                if os.path.exists("cookies.txt"):
                    self.cookies_file_path = "cookies.txt"

    def validate_url(self, url: str) -> bool:
        instagram_regexes = [
            r'instagram\.com/reel/',
            r'instagram\.com/p/',
            r'instagram\.com/tv/',
        ]
        return any(re.search(pattern, url, re.IGNORECASE) for pattern in instagram_regexes)

    async def extract_metadata(self, url: str) -> MediaMetadata:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'no_check_certificates': True,
            'extract_flat': False,
        }
        if self.cookies_file_path and os.path.exists(self.cookies_file_path):
            ydl_opts['cookiefile'] = self.cookies_file_path

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            title = info.get('title') or info.get('description', '')[:60] or 'Instagram Post'
            thumbnail_url = info.get('thumbnail', '')
            duration_seconds = int(info.get('duration', 0)) if info.get('duration') else 0
            
            # Format duration as H:MM:SS or M:SS
            minutes = duration_seconds // 60
            hours = minutes // 60
            minutes = minutes % 60
            seconds = duration_seconds % 60
            duration_str = f"{hours}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes}:{seconds:02d}"

            # Carousel check
            entries = info.get('entries', None)
            streams: List[MediaStream] = []
            carousel_media: List[MediaMetadata] = []
            is_carousel = False

            if entries:
                is_carousel = True
                for i, entry in enumerate(entries):
                    if entry and entry.get('url'):
                        entry_duration = entry.get('duration', 0) or 0
                        entry_duration_str = f"{int(entry_duration) // 60}:{int(entry_duration) % 60:02d}"
                        
                        entry_filesize = entry.get('filesize') or entry.get('filesize_approx') or 0
                        entry_filesize_str = f"{entry_filesize / (1024 * 1024):.2f} MB" if entry_filesize else "N/A"
                        
                        entry_title = entry.get('title') or f"Instagram Item {i+1}"
                        entry_thumb = entry.get('thumbnail') or ''
                        
                        # Add as a stream option inside the carousel
                        streams.append(MediaStream(
                            url=entry.get('url'),
                            resolution=f"{entry.get('height', '1080')}p",
                            extension=entry.get('ext', 'mp4'),
                            filesize=entry_filesize_str,
                            filesize_bytes=entry_filesize,
                            has_video=True,
                            has_audio=True
                        ))
            else:
                # Single media
                video_url = info.get('url', '')
                if not video_url and info.get('formats'):
                    best = None
                    for fmt in info['formats']:
                        if fmt.get('vcodec') != 'none' and fmt.get('acodec') != 'none':
                            best = fmt
                    if not best:
                        best = info['formats'][-1]
                    video_url = best.get('url', '')

                # Build formats
                if info.get('formats'):
                    seen_res = set()
                    for fmt in info['formats']:
                        if fmt.get('vcodec') == 'none':
                            continue
                        height = fmt.get('height', 0)
                        if not height or height in seen_res:
                            continue
                        seen_res.add(height)
                        
                        fmt_filesize = fmt.get('filesize') or fmt.get('filesize_approx') or 0
                        fmt_filesize_str = f"{fmt_filesize / (1024*1024):.2f} MB" if fmt_filesize else 'N/A'
                        
                        vcodec = fmt.get('vcodec', 'unknown')
                        codec = vcodec.split('.')[0] if vcodec else None
                        fps = int(fmt.get('fps')) if fmt.get('fps') else None
                        dynamic_range = fmt.get('dynamic_range') or ''
                        hdr = 'HDR' in dynamic_range or 'hdr' in dynamic_range

                        streams.append(MediaStream(
                            url=fmt.get('url'),
                            resolution=f"{height}p",
                            extension=fmt.get('ext', 'mp4'),
                            filesize=fmt_filesize_str,
                            filesize_bytes=fmt_filesize,
                            has_video=True,
                            has_audio=fmt.get('acodec') != 'none',
                            codec=codec,
                            fps=fps,
                            hdr=hdr
                        ))

                # Fallback to single URL
                if not streams and video_url:
                    filesize = info.get('filesize') or info.get('filesize_approx') or 0
                    filesize_str = f"{filesize / (1024*1024):.2f} MB" if filesize else 'N/A'
                    
                    vcodec = info.get('vcodec', 'unknown')
                    codec = vcodec.split('.')[0] if vcodec else None
                    fps = int(info.get('fps')) if info.get('fps') else None
                    dynamic_range = info.get('dynamic_range') or ''
                    hdr = 'HDR' in dynamic_range or 'hdr' in dynamic_range

                    streams.append(MediaStream(
                        url=video_url,
                        resolution=f"{info.get('height', 720)}p",
                        extension=info.get('ext', 'mp4'),
                        filesize=filesize_str,
                        filesize_bytes=filesize,
                        has_video=True,
                        has_audio=True,
                        codec=codec,
                        fps=fps,
                        hdr=hdr
                    ))

            return MediaMetadata(
                title=title,
                thumbnail_url=thumbnail_url,
                duration=duration_str,
                duration_seconds=duration_seconds,
                provider="instagram",
                streams=streams,
                is_carousel=is_carousel,
                carousel_media=carousel_media
            )
        except Exception as e:
            raise RuntimeError(f"Instagram metadata extraction failed: {str(e)}")

    async def download_stream(
        self, 
        stream_url: str, 
        destination_path: str, 
        progress_callback: Optional[Callable[[int, int, float, str], None]] = None
    ) -> None:
        DownloaderClient.download_file(
            url=stream_url,
            destination_path=destination_path,
            progress_callback=progress_callback
        )

import os
import re
from typing import List, Optional, Callable
import yt_dlp
from src.providers.base_provider import BaseProvider
from src.core.entities.media import MediaMetadata, MediaStream
from src.utils.downloader_client import DownloaderClient

class YouTubeProvider(BaseProvider):
    def __init__(self, cookies_file_path: Optional[str] = None):
        self.cookies_file_path = cookies_file_path
        # Look for default cookies.txt in config directory if not provided
        if not self.cookies_file_path:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            default_cookies = os.path.join(base_dir, "config", "cookies", "youtube_cookies.txt")
            if os.path.exists(default_cookies):
                self.cookies_file_path = default_cookies
            else:
                # Fallback to general cookies.txt in current working dir
                if os.path.exists("cookies.txt"):
                    self.cookies_file_path = "cookies.txt"

    def validate_url(self, url: str) -> bool:
        youtube_regex = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
        return bool(re.match(youtube_regex, url))

    async def extract_metadata(self, url: str) -> MediaMetadata:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'no_check_certificates': True,
            'js_runtimes': {'node': {}},
            'remote_components': ['ejs:github'],
        }
        if self.cookies_file_path and os.path.exists(self.cookies_file_path):
            ydl_opts['cookiefile'] = self.cookies_file_path

        try:
            # We wrap blocking yt-dlp in a loop or run directly.
            # Since extract_metadata is async, in a production framework we'd run this in an executor thread.
            # For simplicity and robust parsing, we execute the extract.
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            title = info.get('title', 'YouTube Video')
            duration_seconds = int(info.get('duration', 0))
            
            # Format duration as H:MM:SS or M:SS
            minutes = duration_seconds // 60
            hours = minutes // 60
            minutes = minutes % 60
            seconds = duration_seconds % 60
            if hours > 0:
                duration_str = f"{hours}:{minutes:02d}:{seconds:02d}"
            else:
                duration_str = f"{minutes}:{seconds:02d}"

            thumbnail_url = info.get('thumbnail', '')
            if not thumbnail_url and info.get('thumbnails'):
                thumbnail_url = info['thumbnails'][0].get('url', '')

            streams: List[MediaStream] = []
            
            # Extract streams from formats
            formats = info.get('formats', [])
            
            # Get best audio format for adaptive merging
            audio_formats = []
            for f in formats:
                if f.get('vcodec') == 'none' and f.get('acodec') != 'none':
                    abr = f.get('abr', 0) or 0
                    audio_formats.append((abr, f))
            
            # Sort by bitrate descending
            audio_formats.sort(key=lambda x: x[0], reverse=True)
            best_audio = audio_formats[0][1] if audio_formats else None
            best_audio_url = best_audio.get('url') if best_audio else None

            seen_formats = set()

            for f in formats:
                # Video formats
                if f.get('vcodec') != 'none':
                    height = f.get('height')
                    ext = f.get('ext', 'mp4')
                    if not height:
                        continue
                    
                    res_label = f"{height}p"
                    format_key = f"{res_label}_{ext}"
                    if format_key in seen_formats:
                        continue
                    
                    seen_formats.add(format_key)
                    filesize_bytes = f.get('filesize') or f.get('filesize_approx') or 0
                    filesize_str = f"{filesize_bytes / (1024 * 1024):.2f} MB" if filesize_bytes else "N/A"
                    has_audio = f.get('acodec') != 'none'

                    # Extract extra metadata
                    vcodec = f.get('vcodec', 'unknown')
                    codec = vcodec.split('.')[0] if vcodec else None
                    fps = int(f.get('fps')) if f.get('fps') else None
                    dynamic_range = f.get('dynamic_range') or ''
                    hdr = 'HDR' in dynamic_range or 'hdr' in dynamic_range or 'Dolby Vision' in dynamic_range

                    streams.append(MediaStream(
                        url=f.get('url'),
                        resolution=res_label,
                        quality=None,
                        extension=ext,
                        filesize=filesize_str,
                        filesize_bytes=filesize_bytes,
                        has_video=True,
                        has_audio=has_audio,
                        audio_url=None if has_audio else best_audio_url,
                        codec=codec,
                        fps=fps,
                        hdr=hdr
                    ))

                # Audio formats
                elif f.get('acodec') != 'none':
                    abr = f.get('abr')
                    ext = f.get('ext', 'm4a')
                    if not abr:
                        continue
                    
                    qual_label = f"{int(abr)}kbps"
                    format_key = f"{qual_label}_{ext}"
                    if format_key in seen_formats:
                        continue
                        
                    seen_formats.add(format_key)
                    filesize_bytes = f.get('filesize') or f.get('filesize_approx') or 0
                    filesize_str = f"{filesize_bytes / (1024 * 1024):.2f} MB" if filesize_bytes else "N/A"

                    # Extract extra metadata
                    acodec = f.get('acodec', 'unknown')
                    codec = acodec.split('.')[0] if acodec else None
                    channels = int(f.get('audio_channels')) if f.get('audio_channels') else None
                    asr = f.get('asr')
                    sample_rate = f"{asr / 1000:.1f} kHz" if asr else None

                    streams.append(MediaStream(
                        url=f.get('url'),
                        resolution="Audio",
                        quality=qual_label,
                        extension=ext,
                        filesize=filesize_str,
                        filesize_bytes=filesize_bytes,
                        has_video=False,
                        has_audio=True,
                        codec=codec,
                        channels=channels,
                        sample_rate=sample_rate
                    ))

            # Extract subtitles
            subtitles_list = []
            raw_subs = info.get('subtitles') or {}
            raw_auto = info.get('automatic_captions') or {}
            
            # Combine both raw subtitles and auto captions
            all_subs = {**raw_auto, **raw_subs}
            for lang_code, formats in all_subs.items():
                vtt_fmt = next((f for f in formats if f.get('ext') == 'vtt'), None)
                if not vtt_fmt and formats:
                    vtt_fmt = formats[0]
                if vtt_fmt:
                    subtitles_list.append({
                        "language": vtt_fmt.get('name') or lang_code,
                        "code": lang_code,
                        "format": vtt_fmt.get('ext') or 'vtt',
                        "ext": vtt_fmt.get('ext') or 'vtt',
                        "url": vtt_fmt.get('url')
                    })

            return MediaMetadata(
                title=title,
                thumbnail_url=thumbnail_url,
                duration=duration_str,
                duration_seconds=duration_seconds,
                provider="youtube",
                streams=streams,
                subtitles=subtitles_list
            )
        except Exception as e:
            raise RuntimeError(f"YouTube metadata extraction failed: {str(e)}")

    async def download_stream(
        self, 
        stream_url: str, 
        destination_path: str, 
        progress_callback: Optional[Callable[[int, int, float, str], None]] = None
    ) -> None:
        # Check if cancellation occurs. Inside task execution we pass task indicators.
        # DownloaderClient handles requests
        DownloaderClient.download_file(
            url=stream_url,
            destination_path=destination_path,
            progress_callback=progress_callback
        )

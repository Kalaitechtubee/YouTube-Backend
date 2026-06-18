import os
import subprocess
from typing import Optional

class FFmpegMerger:
    def __init__(self, ffmpeg_path: Optional[str] = None):
        self.ffmpeg_path = ffmpeg_path or os.environ.get('FFMPEG_PATH', 'ffmpeg')

    def merge_video_audio(
        self, 
        video_path: str, 
        audio_path: str, 
        output_path: str
    ) -> None:
        """
        Merges video_path (no audio) and audio_path into output_path using ffmpeg.
        """
        hide_window_kwargs = {}
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            hide_window_kwargs['startupinfo'] = startupinfo

        command = [
            self.ffmpeg_path, "-i", video_path, "-i", audio_path,
            "-c:v", "copy", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0",
            "-shortest", output_path, "-y"
        ]

        try:
            process = subprocess.run(
                command, 
                capture_output=True, 
                text=True, 
                check=True, 
                **hide_window_kwargs
            )
        except subprocess.CalledProcessError as e:
            # Fallback mapping if streams are layout formatted differently
            command_fallback = [
                self.ffmpeg_path, "-i", video_path, "-i", audio_path,
                "-c:v", "copy", "-c:a", "aac", "-map", "0", "-map", "1",
                "-shortest", output_path, "-y"
            ]
            try:
                subprocess.run(
                    command_fallback, 
                    capture_output=True, 
                    text=True, 
                    check=True, 
                    **hide_window_kwargs
                )
            except subprocess.CalledProcessError as e_fallback:
                raise RuntimeError(
                    f"FFmpeg merging failed. Fallback error: {e_fallback.stderr}"
                )

    def embed_thumbnail(
        self, 
        media_path: str, 
        thumbnail_path: str, 
        output_path: str
    ) -> None:
        """
        Embeds a cover thumbnail image into the media file.
        """
        hide_window_kwargs = {}
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            hide_window_kwargs['startupinfo'] = startupinfo

        # command mapping depends on file type
        ext = os.path.splitext(media_path)[1].lower()
        if ext == '.mp3':
            command = [
                self.ffmpeg_path, "-i", media_path, "-i", thumbnail_path,
                "-map", "0:0", "-map", "1:0", "-c", "copy", 
                "-id3v2_version", "3", "-metadata:s:v", 'title="Album cover"', 
                "-metadata:s:v", 'comment="Cover (Front)"', output_path, "-y"
            ]
        else:
            # MP4 thumbnail embedding
            command = [
                self.ffmpeg_path, "-i", media_path, "-i", thumbnail_path,
                "-map", "0", "-map", "1", "-c", "copy", 
                "-disposition:v:1", "attached_pic", output_path, "-y"
            ]

        try:
            subprocess.run(
                command, 
                capture_output=True, 
                text=True, 
                check=True, 
                **hide_window_kwargs
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"FFmpeg thumbnail embedding failed: {e.stderr}")

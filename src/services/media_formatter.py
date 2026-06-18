import uuid
import re
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from src.core.entities.media import MediaMetadata, MediaStream
from src.database.models import DownloadOptionModel

def clean_codec(codec_name: Optional[str]) -> str:
    if not codec_name or codec_name.lower() == 'none':
        return 'none'
    codec_name = codec_name.lower().strip()
    if 'avc' in codec_name or 'h264' in codec_name:
        return 'h264'
    if 'vp9' in codec_name or 'vp09' in codec_name:
        return 'vp9'
    if 'av1' in codec_name or 'av01' in codec_name:
        return 'av1'
    if 'h265' in codec_name or 'hevc' in codec_name:
        return 'hevc'
    if 'mp4a' in codec_name or 'aac' in codec_name:
        return 'aac'
    if 'opus' in codec_name:
        return 'opus'
    return codec_name.split('.')[0]

def get_res_height(res_str: Optional[str]) -> int:
    if not res_str:
        return 0
    clean = re.sub(r'\D', '', res_str)
    try:
        return int(clean)
    except ValueError:
        return 0

def get_audio_bitrate(bitrate_str: Optional[str]) -> int:
    if not bitrate_str:
        return 0
    clean = re.sub(r'\D', '', bitrate_str)
    try:
        return int(clean)
    except ValueError:
        return 0

class DownloadIdGenerator:
    @staticmethod
    def generate_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def register_option(
        db: Session,
        url: str,
        video_stream_url: Optional[str],
        audio_stream_url: Optional[str],
        format_ext: str,
        resolution: Optional[str]
    ) -> str:
        download_id = DownloadIdGenerator.generate_id()
        option = DownloadOptionModel(
            id=download_id,
            url=url,
            video_stream_url=video_stream_url,
            audio_stream_url=audio_stream_url,
            format=format_ext,
            resolution=resolution
        )
        db.add(option)
        db.commit()
        return download_id

class VideoResolver:
    @staticmethod
    def is_valid_video_stream(stream: MediaStream) -> bool:
        # Filter out HLS playlists, empty/broken URLs
        if not stream.url:
            return False
        if '.m3u8' in stream.url or 'hls' in (stream.codec or '').lower():
            return False
        if not stream.resolution or stream.resolution.lower() == 'audio':
            return False
        return True

    @staticmethod
    def process_and_group(streams: List[MediaStream]) -> Dict[str, List[MediaStream]]:
        grouped: Dict[str, List[MediaStream]] = {}
        for s in streams:
            if not VideoResolver.is_valid_video_stream(s):
                continue
            res = s.resolution.lower()
            if res not in grouped:
                grouped[res] = []
            grouped[res].append(s)
        return grouped

    @staticmethod
    def resolve_best_stream(streams: List[MediaStream]) -> MediaStream:
        # Prefer progressive (has_audio=True), then higher filesize, then mp4 extension
        def sorting_key(s: MediaStream):
            has_audio_score = 1 if s.has_audio else 0
            is_mp4_score = 1 if s.extension.lower() == 'mp4' else 0
            size_score = s.filesize_bytes or 0
            return (has_audio_score, is_mp4_score, size_score)
        
        sorted_streams = sorted(streams, key=sorting_key, reverse=True)
        return sorted_streams[0]

class AudioResolver:
    @staticmethod
    def is_valid_audio_stream(stream: MediaStream) -> bool:
        if not stream.url:
            return False
        if stream.has_video:
            return False
        if not stream.quality:
            return False
        return True

    @staticmethod
    def resolve_and_sort(streams: List[MediaStream]) -> List[MediaStream]:
        valid_streams = [s for s in streams if AudioResolver.is_valid_audio_stream(s)]
        
        # Merge duplicate bitrates, keeping the best one (prefer m4a/aac)
        best_by_bitrate: Dict[int, MediaStream] = {}
        for s in valid_streams:
            bitrate = get_audio_bitrate(s.quality)
            if bitrate == 0:
                continue
            if bitrate not in best_by_bitrate:
                best_by_bitrate[bitrate] = s
            else:
                existing = best_by_bitrate[bitrate]
                # Prefer m4a over webm, or larger file size
                existing_score = (1 if existing.extension.lower() == 'm4a' else 0, existing.filesize_bytes or 0)
                current_score = (1 if s.extension.lower() == 'm4a' else 0, s.filesize_bytes or 0)
                if current_score > existing_score:
                    best_by_bitrate[bitrate] = s
        
        # Sort by bitrate ascending
        sorted_bitrates = sorted(best_by_bitrate.keys())
        return [best_by_bitrate[b] for b in sorted_bitrates]

class MediaFormatter:
    def __init__(self, db: Session):
        self.db = db

    def format_metadata(self, metadata: MediaMetadata, source_url: str) -> Dict[str, Any]:
        # 1. Resolve videos
        video_groups = VideoResolver.process_and_group(metadata.streams)
        
        # Sort video qualities (resolutions) ascending: 144p, 240p, 360p, 480p, 720p, 1080p, 1440p, 2160p
        sorted_resolutions = sorted(video_groups.keys(), key=get_res_height)
        
        formatted_videos = []
        best_video_res_height = 0
        best_video_idx = -1

        for idx, res in enumerate(sorted_resolutions):
            best_stream = VideoResolver.resolve_best_stream(video_groups[res])
            
            # Generate ID and register in database
            download_id = DownloadIdGenerator.register_option(
                db=self.db,
                url=source_url,
                video_stream_url=best_stream.url,
                audio_stream_url=best_stream.audio_url,
                format_ext=best_stream.extension,
                resolution=best_stream.resolution
            )
            
            # Determine isAdaptive and requiresMerge
            # Video-only (no audio) is adaptive and requires merging
            requires_merge = not best_stream.has_audio
            is_adaptive = requires_merge
            
            # Estimated size
            est_size = best_stream.filesize
            
            # Availability and downloadMethod
            availability = "available"
            download_method = "http"
            
            video_card = {
                "download_id": download_id,
                "resolution": best_stream.resolution,
                "quality": best_stream.resolution,
                "container": best_stream.extension,
                "extension": best_stream.extension, # For frontend backward compatibility
                "codec": clean_codec(best_stream.codec),
                "fps": best_stream.fps or 30,
                "hdr": best_stream.hdr or False,
                "filesize": best_stream.filesize,
                "estimated_size": est_size,
                "type": "video",
                "isAdaptive": is_adaptive,
                "requiresMerge": requires_merge,
                "hasAudio": best_stream.has_audio,
                "recommended": False,  # Will flag the best one later
                "downloadMethod": download_method,
                "availability": availability
            }
            formatted_videos.append(video_card)
            
            res_height = get_res_height(best_stream.resolution)
            if res_height > best_video_res_height:
                best_video_res_height = res_height
                best_video_idx = idx

        # Set recommended flag for the highest quality video format
        if best_video_idx != -1:
            formatted_videos[best_video_idx]["recommended"] = True

        # 2. Resolve audio
        sorted_audio_streams = AudioResolver.resolve_and_sort(metadata.streams)
        formatted_audios = []
        
        for s in sorted_audio_streams:
            bitrate_val = get_audio_bitrate(s.quality)
            bitrate_label = f"{bitrate_val} kbps"
            
            download_id = DownloadIdGenerator.register_option(
                db=self.db,
                url=source_url,
                video_stream_url=None,
                audio_stream_url=s.url,
                format_ext=s.extension,
                resolution=s.quality
            )
            
            audio_card = {
                "download_id": download_id,
                "bitrate": bitrate_label,
                "quality": s.quality,  # For frontend backward compatibility
                "container": s.extension,
                "extension": s.extension, # For frontend backward compatibility
                "codec": clean_codec(s.codec) or "aac",
                "filesize": s.filesize,
                "channels": s.channels or 2,
                "sampleRate": s.sample_rate or "44.1 kHz"
            }
            formatted_audios.append(audio_card)

        # 3. Resolve subtitles
        formatted_subtitles = []
        for sub in getattr(metadata, 'subtitles', []):
            sub_id = DownloadIdGenerator.register_option(
                db=self.db,
                url=source_url,
                video_stream_url=sub.get('url'),
                audio_stream_url=None,
                format_ext=sub.get('ext') or 'vtt',
                resolution=sub.get('language')
            )
            formatted_subtitles.append({
                "download_id": sub_id,
                "language": sub.get('language'),
                "code": sub.get('code'),
                "format": sub.get('format') or 'vtt',
                "ext": sub.get('ext') or 'vtt'
            })

        # Build response using ResponseBuilder
        return ResponseBuilder.build_success_response(
            media_id=source_url,
            title=metadata.title,
            thumbnail=metadata.thumbnail_url,
            duration=metadata.duration,
            provider=metadata.provider,
            video_downloads=formatted_videos,
            audio_downloads=formatted_audios,
            subtitle_downloads=formatted_subtitles
        )

class ResponseBuilder:
    @staticmethod
    def build_success_response(
        media_id: str,
        title: str,
        thumbnail: str,
        duration: str,
        provider: str,
        video_downloads: List[Dict[str, Any]],
        audio_downloads: List[Dict[str, Any]],
        subtitle_downloads: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        return {
            "status": "success",
            "media": {
                "id": media_id,
                "title": title,
                "thumbnail": thumbnail,
                "duration": duration,
                "provider": provider,
                "type": "video"
            },
            "downloads": {
                "video": video_downloads,
                "audio": audio_downloads,
                "subtitle": subtitle_downloads
            },
            "capabilities": {
                "video": len(video_downloads) > 0,
                "audio": len(audio_downloads) > 0,
                "subtitles": len(subtitle_downloads) > 0
            }
        }

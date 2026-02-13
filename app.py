import os
import subprocess
import tempfile
import uuid
import re
import time
import threading

import requests
from flask import Flask, request, jsonify, Response, stream_with_context, send_file
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

# --- Configuration ---
# FFMPEG_PATH: Set via environment variable, or defaults to 'ffmpeg' (must be in system PATH)
FFMPEG_PATH = os.environ.get('FFMPEG_PATH', 'ffmpeg')

# Path to cookies for yt-dlp to bypass bot detection
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_FILE = os.path.join(BASE_DIR, 'cookies.txt')

if not os.path.exists(COOKIES_FILE):
    COOKIES_FILE = None # Fallback if not found

@app.route('/proxy_download/')
def proxy_download():
    url = request.args.get('url')
    filename = request.args.get('filename', 'download')

    if not url:
        return "No URL provided", 400

    try:
        req = requests.get(url, stream=True)

        def generate():
            for chunk in req.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    yield chunk

        # Determine correct content type from filename extension
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        content_type_map = {
            'mp4': 'video/mp4',
            'webm': 'video/webm',
            'mp3': 'audio/mpeg',
            'm4a': 'audio/mp4',
        }
        content_type = content_type_map.get(ext, req.headers.get('Content-Type', 'application/octet-stream'))

        headers = {
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Type': content_type,
            'Content-Length': req.headers.get('Content-Length')
        }

        return Response(stream_with_context(generate()), headers=headers)
    except Exception as e:
        return str(e), 500

# Temporary storage for merges
# Format: { download_id: { 'status': 'preparing'|'merging'|'ready'|'error', 'path': str, 'filename': str, 'error': str } }
merge_status = {}

def background_merge(download_id, video_url, audio_url, filename):
    temp_dir = tempfile.gettempdir()
    unique_id = str(uuid.uuid4())
    video_path = os.path.join(temp_dir, f"video_{unique_id}.tmp")
    audio_path = os.path.join(temp_dir, f"audio_{unique_id}.tmp")
    output_path = os.path.join(temp_dir, f"output_{unique_id}.mp4")

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Referer': 'https://www.youtube.com/',
        'Origin': 'https://www.youtube.com'
    })

    def cleanup_temps(paths):
        for p in paths:
            try:
                if os.path.exists(p): os.remove(p)
            except: pass

    def download_with_retry(url, path, label, progress_key):
        for attempt in range(3):
            try:
                with session.get(url, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get('content-length', 0))
                    downloaded = 0
                    
                    with open(path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_size > 0:
                                    percent = min(99, int((downloaded / total_size) * 100))
                                    merge_status[download_id][progress_key] = percent
                    
                    merge_status[download_id][progress_key] = 100
                return True
            except Exception as e:
                if attempt == 2: raise e
                time.sleep(2)
        return False

    try:
        merge_status[download_id]['status'] = 'downloading'
        merge_status[download_id]['v_prog'] = 0
        merge_status[download_id]['a_prog'] = 0
        
        # Parallel Downloads
        threads = []
        if video_url:
            v_thread = threading.Thread(target=download_with_retry, args=(video_url, video_path, "Video", "v_prog"))
            threads.append(v_thread)
            v_thread.start()
        
        if audio_url:
            a_thread = threading.Thread(target=download_with_retry, args=(audio_url, audio_path, "Audio", "a_prog"))
            threads.append(a_thread)
            a_thread.start()
            
        for t in threads:
            t.join()

        # Check for errors
        if merge_status[download_id].get('status') == 'error':
            return

        merge_status[download_id]['status'] = 'merging'

        # Merge or Rename Logic
        hide_window_kwargs = {}
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            hide_window_kwargs['startupinfo'] = startupinfo

        if video_url and audio_url:
            # Full Merge
            command = [
                FFMPEG_PATH, "-i", video_path, "-i", audio_path,
                "-c:v", "copy", "-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0",
                "-shortest", output_path, "-y"
            ]
            process = subprocess.run(command, capture_output=True, text=True, **hide_window_kwargs)
            
            if process.returncode != 0:
                # Fallback mapping
                command[10:14] = ["-map", "0", "-map", "1"]
                process = subprocess.run(command, capture_output=True, text=True, **hide_window_kwargs)
        
        elif audio_url and not video_url:
             # Audio Only - direct move
             if os.path.exists(output_path): os.remove(output_path)
             if os.path.exists(audio_path):
                 os.rename(audio_path, output_path)
        
        elif video_url and not audio_url:
             # Video Only - direct move
             if os.path.exists(output_path): os.remove(output_path)
             if os.path.exists(video_path):
                 os.rename(video_path, output_path)

        cleanup_temps([video_path, audio_path])

        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            merge_status[download_id].update({
                'status': 'ready',
                'path': output_path
            })
        else:
            raise Exception("File generation failed or file too small.")

    except Exception as e:
        cleanup_temps([video_path, audio_path, output_path])
        merge_status[download_id].update({
            'status': 'error',
            'error': str(e)
        })

@app.route('/prepare_download/', methods=['POST'])
def prepare_download():
    data = request.json
    if not data or 'video_url' not in data or 'audio_url' not in data:
        return jsonify({'error': 'Missing URLs'}), 400
    
    download_id = str(uuid.uuid4())
    merge_status[download_id] = {
        'status': 'starting',
        'filename': data.get('filename', 'video.mp4')
    }
    
    # Start merge in background
    thread = threading.Thread(
        target=background_merge,
        args=(download_id, data['video_url'], data['audio_url'], data['filename'])
    )
    thread.start()
    
    return jsonify({'download_id': download_id})

@app.route('/check_status/')
def check_status():
    download_id = request.args.get('id')
    status = merge_status.get(download_id)
    if not status:
        return jsonify({'error': 'Invalid ID'}), 404
    return jsonify(status)

@app.route('/execute_download/')
def execute_download():
    download_id = request.args.get('id')
    status_data = merge_status.get(download_id)
    
    if not status_data or status_data['status'] != 'ready':
        return "File not ready or expired.", 400
    
    output_path = status_data['path']
    filename = status_data['filename']

    def generate():
        try:
            with open(output_path, 'rb') as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk: break
                    yield chunk
        finally:
            # Cleanup output file after streaming
            try:
                if os.path.exists(output_path): os.remove(output_path)
            except: pass
            # Optionally remove from status tracking
            merge_status.pop(download_id, None)

    return Response(stream_with_context(generate()), headers={
        'Content-Disposition': f'attachment; filename="{filename}"',
        'Content-Type': 'video/mp4'
    })


# **************************************************Instagram Download Start**********************************************

# Allowed Instagram URL patterns (public content only)
ALLOWED_INSTAGRAM_PATTERNS = [
    r'instagram\.com/reel/',
    r'instagram\.com/p/',
    r'instagram\.com/tv/',
]

# Blocked Instagram URL patterns
BLOCKED_INSTAGRAM_PATTERNS = [
    r'instagram\.com/stories/',
    r'/private',
]

def is_valid_instagram_url(url):
    """Validate that the URL is a public Instagram reel/post/tv."""
    if not url or 'instagram.com' not in url:
        return False, 'Invalid Instagram URL'
    
    # Check for blocked patterns
    for pattern in BLOCKED_INSTAGRAM_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return False, 'Stories and private content are not supported. Only public reels, posts, and IGTV are allowed.'
    
    # Check if URL matches any allowed pattern
    for pattern in ALLOWED_INSTAGRAM_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return True, None
    
    return False, 'Unsupported Instagram URL. Please use a direct link to a public reel, post, or IGTV video.'


@app.route('/instagram/', methods=['GET'])
def instagram_download():
    """Fetch public Instagram video metadata using yt-dlp."""
    try:
        url = request.args.get('url')
        if not url:
            return jsonify({'error': 'No URL provided'}), 400

        # Validate URL
        is_valid, error_msg = is_valid_instagram_url(url)
        if not is_valid:
            return jsonify({'error': error_msg}), 400

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'no_check_certificates': True,
            'extract_flat': False,
            'cookiefile': COOKIES_FILE,
            'format': 'bestvideo+bestaudio/best',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        # Handle carousel/multiple entries
        entries = info.get('entries', None)

        if entries:
            # Carousel post — multiple videos
            videos = []
            for i, entry in enumerate(entries):
                if entry and entry.get('url'):
                    duration = entry.get('duration', 0)
                    duration_str = f"{int(duration) // 60}:{int(duration) % 60:02d}" if duration else 'N/A'
                    
                    videos.append({
                        'title': entry.get('title') or entry.get('description', '')[:60] or f'Instagram Video {i+1}',
                        'thumbnail': entry.get('thumbnail', ''),
                        'video_url': entry.get('url', ''),
                        'duration': duration_str,
                        'duration_seconds': int(duration) if duration else 0,
                        'resolution': entry.get('resolution') or entry.get('height', 'N/A'),
                        'filesize': f"{round(entry.get('filesize', 0) / (1024 * 1024), 2)} MB" if entry.get('filesize') else 'N/A',
                        'extension': entry.get('ext', 'mp4'),
                    })

            data_set = {
                'title': info.get('title') or info.get('description', '')[:60] or 'Instagram Carousel',
                'thumbnail': videos[0]['thumbnail'] if videos else '',
                'duration': videos[0]['duration'] if videos else 'N/A',
                'content_type': 'instagram',
                'is_carousel': True,
                'videos': videos,
                'streams': videos,  # For frontend compatibility
            }
        else:
            # Single video (reel/post/IGTV)
            duration = info.get('duration', 0)
            duration_str = f"{int(duration) // 60}:{int(duration) % 60:02d}" if duration else 'N/A'

            # Get best format URL
            video_url = info.get('url', '')
            
            # Sometimes yt-dlp puts best format in 'formats' list
            if not video_url and info.get('formats'):
                # Pick best format with both video and audio
                best = None
                for fmt in info['formats']:
                    if fmt.get('vcodec') != 'none' and fmt.get('acodec') != 'none':
                        best = fmt
                if not best:
                    best = info['formats'][-1]  # fallback to last (usually best)
                video_url = best.get('url', '')

            # Build streams list from available formats for quality selection
            streams_data = []
            if info.get('formats'):
                seen_res = set()
                for fmt in info['formats']:
                    if fmt.get('vcodec') == 'none':  # Skip audio-only
                        continue
                    height = fmt.get('height', 0)
                    if not height or height in seen_res:
                        continue
                    seen_res.add(height)
                    
                    fmt_filesize = fmt.get('filesize') or fmt.get('filesize_approx', 0)
                    streams_data.append({
                        'title': info.get('title') or 'Instagram Video',
                        'thumbnail': info.get('thumbnail', ''),
                        'video_url': fmt.get('url', ''),
                        'duration': duration_str,
                        'resolution': f"{height}p",
                        'filesize': f"{round(fmt_filesize / (1024*1024), 2)} MB" if fmt_filesize else 'N/A',
                        'extension': fmt.get('ext', 'mp4'),
                        'has_audio': fmt.get('acodec') != 'none',
                    })
                
                # Sort by resolution descending
                streams_data.sort(key=lambda x: int(x['resolution'].replace('p','') or 0), reverse=True)
            
            # If no formats found, use the single URL as the only stream
            if not streams_data:
                filesize = info.get('filesize') or info.get('filesize_approx', 0)
                streams_data = [{
                    'title': info.get('title') or 'Instagram Video',
                    'thumbnail': info.get('thumbnail', ''),
                    'video_url': video_url,
                    'duration': duration_str,
                    'resolution': f"{info.get('height', 720)}p",
                    'filesize': f"{round(filesize / (1024*1024), 2)} MB" if filesize else 'N/A',
                    'extension': info.get('ext', 'mp4'),
                    'has_audio': True,
                }]

            data_set = {
                'title': info.get('title') or info.get('description', '')[:60] or 'Instagram Video',
                'thumbnail': info.get('thumbnail', ''),
                'duration': duration_str,
                'content_type': 'instagram',
                'is_carousel': False,
                'streams': streams_data,
            }

        return jsonify(data_set)

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        if 'Private' in error_msg or 'login' in error_msg.lower():
            return jsonify({'error': 'This content appears to be private or requires login. Only public content is supported.'}), 403
        return jsonify({'error': f'Could not extract video: {error_msg}'}), 500
    except Exception as e:
        print(f"Instagram Error: {e}")
        return jsonify({'error': str(e)}), 500

# **************************************************Instagram Download End*********************************************


# **************************************************HomePage Start**********************************************
@app.route('/', methods=['GET'])
def home_page():
    data_set = {'Page': 'HomePage of YouTube Downloader',
                'Message': 'Successfully loaded the HomePage'}
    return jsonify(data_set)
# **************************************************HomePage End*************************************************


# *************************************************Audio Download End******************************************


if __name__ == '__main__':
    app.run(debug=False)

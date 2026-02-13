from pytubefix import YouTube

url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
try:
    yt = YouTube(url)
    print(f"Title: {yt.title}")
    print("--- Progressive Streams ---")
    progressive = yt.streams.filter(progressive=True)
    for s in progressive:
        print(f"Tag: {s.itag}, Res: {s.resolution}, VCodec: {s.video_codec}, ACodec: {s.audio_codec}, Type: {s.mime_type}")
    
    print("\n--- Adaptive Video Streams ---")
    adaptive = yt.streams.filter(adaptive=True, only_video=True)
    for s in adaptive:
        print(f"Tag: {s.itag}, Res: {s.resolution}, VCodec: {s.video_codec}, Type: {s.mime_type}")
except Exception as e:
    print(f"Error: {e}")

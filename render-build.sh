#!/usr/bin/env bash
# Exit on error
set -o errexit

# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Install FFmpeg into the root directory (matching your ./ffmpeg path)
if [ ! -f ffmpeg ]; then
    echo "Downloading FFmpeg..."
    curl -L https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz -o ffmpeg.tar.xz
    tar -xJf ffmpeg.tar.xz
    
    # Find the extracted folder and move only the binary to root
    FFMPEG_FOLDER=$(ls -d ffmpeg-*-static)
    cp "$FFMPEG_FOLDER/ffmpeg" ./ffmpeg
    cp "$FFMPEG_FOLDER/ffprobe" ./ffprobe
    
    # Make executable
    chmod +x ./ffmpeg ./ffprobe
    
    # Cleanup
    rm -rf ffmpeg.tar.xz "$FFMPEG_FOLDER"
    echo "FFmpeg ready"
fi

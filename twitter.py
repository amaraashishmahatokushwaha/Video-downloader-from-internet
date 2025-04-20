from flask import Flask, request, Response, render_template, jsonify
import subprocess
import os
import signal
import re
import json
import time
import random
from urllib.parse import urlparse

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

current_process = None

@app.route('/')
def index():
    return render_template('twitter.html')

@app.route('/twitter', methods=['GET', 'POST'])
def twitter():
    # Add support for both GET and POST requests
    if request.method == 'GET':
        return render_template('twitter.html')
    elif request.method == 'POST':
        # Process POST request - likely need to handle form data
        # Forward to the appropriate download handler based on the form data
        data = request.get_json() or request.form.to_dict()
        return download_twitter()

def generate_command(data):
    url = data.get("url")
    fmt = data.get("format", "best")
    quality = data.get("quality")
    is_playlist = data.get("isPlaylist", False)
    playlist_start = data.get("playlistStart")
    playlist_end = data.get("playlistEnd")
    create_folder = data.get("createFolder", True)
    platform = data.get("platform", "youtube")
    
    cmd = ["yt-dlp"]
    
    # Format selection
    if fmt == "mp3":
        cmd.extend(["--extract-audio", "--audio-format", "mp3"])
    elif quality:
        cmd.extend(["-f", quality])
    else:
        cmd.extend(["-f", fmt])
    
    # Playlist options for YouTube
    if platform == "youtube" and is_playlist:
        cmd.append("--yes-playlist")
        if playlist_start:
            cmd.extend(["--playlist-start", playlist_start])
        if playlist_end:
            cmd.extend(["--playlist-end", playlist_end])
    elif platform == "youtube":
        cmd.append("--no-playlist")
    
    # Platform-specific options
    if platform == "instagram":
        # For Instagram, download all media from post (carousels, etc.)
        cmd.append("--no-warnings")
    elif platform == "twitter":
        cmd.append("--no-warnings")
        
        # Twitter-specific format options
        if fmt == "video-hd":
            cmd.extend(["-f", "best[height>=720]"])
        elif fmt == "video-sd":
            cmd.extend(["-f", "best[height<=480]"])
        elif fmt == "gif":
            cmd.extend(["--convert-to", "gif"])
        elif fmt == "image":
            cmd.extend(["-f", "image"])
    
    # Output format
    if platform == "youtube" and is_playlist and create_folder:
        output_tpl = os.path.join(DOWNLOAD_FOLDER, "youtube/%(playlist_title)s/%(title)s.%(ext)s")
    elif platform == "instagram":
        output_tpl = os.path.join(DOWNLOAD_FOLDER, "instagram/%(uploader)s/%(title)s.%(ext)s")
    elif platform == "twitter":
        # Handle Twitter user content vs single tweet differently
        if data.get("isUser", False) and create_folder:
            output_tpl = os.path.join(DOWNLOAD_FOLDER, "twitter/%(uploader)s/%(title)s.%(ext)s")
        else:
            output_tpl = os.path.join(DOWNLOAD_FOLDER, "twitter/%(title)s.%(ext)s")
    else:
        output_tpl = os.path.join(DOWNLOAD_FOLDER, "youtube/%(title)s.%(ext)s")
    
    cmd.extend(["-o", output_tpl])
    
    # Add URL at the end
    cmd.append(url)
    
    return cmd

@app.route('/download', methods=['POST'])
def download():
    global current_process
    
    data = request.get_json() or request.form.to_dict()
    url = data.get("url")
    
    if not url:
        return Response("❌ Error: No URL provided\n", status=400, mimetype='text/plain')
    
    cmd = generate_command(data)
    
    def run_command():
        global current_process
        yield f"🔍 Processing URL: {url}\n"
        yield f"🛠️ Running command: {' '.join(cmd)}\n"
        yield "⏳ Starting download...\n"
        
        current_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        for line in iter(current_process.stdout.readline, ''):
            # Add progress reporting
            if '[download]' in line and '%' in line:
                # Extract percentage
                match = re.search(r'(\d+\.\d+)%', line)
                if match:
                    percentage = float(match.group(1))
                    yield f"Progress: {int(percentage)}%\n"
            yield line
        
        current_process.stdout.close()
        
        # Check if download completed successfully
        if current_process.wait() == 0:
            yield "✨ Download completed successfully!"
        else:
            yield "❌ Download failed. Please check the error messages above."
    
    return Response(run_command(), mimetype='text/plain')

@app.route('/download/twitter', methods=['POST'])
def download_twitter():
    # This route calls the main download function with proper formatting for Twitter
    data = request.get_json() or request.form.to_dict()
    
    # Normalize the URL if it's a username
    url = data.get("url", "")
    if url.startswith('@') or (not url.startswith('http') and '/' not in url):
        # It's a username
        username = url.replace('@', '')
        data["url"] = f"https://twitter.com/{username}"
        data["isUser"] = True
    
    # Handle different Twitter formats
    format_type = data.get("format", "video-hd")
    
    # Set tweet count limits for user content
    if data.get("isUser", False):
        tweet_count = data.get("tweetCount", 50)
        data["url"] = f"{data['url']} ::{tweet_count}"
        
        # Handle including retweets
        if data.get("includeRetweets", False):
            data["url"] += " --include-retweets"
    
    # Add Twitter as platform
    data["platform"] = "twitter"
    
    # Forward to main download function
    return download()

@app.route('/stop', methods=['POST'])
def stop_download():
    global current_process
    
    if current_process:
        current_process.send_signal(signal.SIGINT)
        current_process = None
        return jsonify({"status": "stopped"}), 200
    else:
        return jsonify({"error": "No download in progress"}), 400

@app.route('/download/abort', methods=['POST'])
def abort_download():
    # Alias for /stop for Twitter downloader UI
    return stop_download()

@app.route('/detect-platform', methods=['POST'])
def detect_platform():
    data = request.get_json() or request.form.to_dict()
    url = data.get("url", "")
    
    platform = "unknown"
    
    if "youtube.com" in url or "youtu.be" in url:
        platform = "youtube"
        is_playlist = "playlist" in url or "list=" in url
        return jsonify({"platform": platform, "isPlaylist": is_playlist})
    elif "instagram.com" in url:
        platform = "instagram"
    elif "twitter.com" in url or "x.com" in url:
        platform = "twitter"
        is_user = "/status/" not in url
        return jsonify({"platform": platform, "isUser": is_user})
    
    return jsonify({"platform": platform})

if __name__ == '__main__':
    app.run(debug=True)
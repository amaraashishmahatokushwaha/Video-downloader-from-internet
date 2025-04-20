from flask import Flask, request, Response, render_template, jsonify
import subprocess
import os
import signal
import re

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

current_process = None

@app.route('/')
def index():
    return render_template('youtube.html')

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
        
    # Output format
    if platform == "youtube" and is_playlist and create_folder:
        output_tpl = os.path.join(DOWNLOAD_FOLDER, "youtube/%(playlist_title)s/%(title)s.%(ext)s")
    elif platform == "instagram":
        output_tpl = os.path.join(DOWNLOAD_FOLDER, "instagram/%(uploader)s/%(title)s.%(ext)s")
    elif platform == "twitter":
        output_tpl = os.path.join(DOWNLOAD_FOLDER, "twitter/%(uploader)s/%(title)s.%(ext)s")
    else:
        output_tpl = os.path.join(DOWNLOAD_FOLDER, "youtube/%(title)s.%(ext)s")
        
    cmd.extend(["-o", output_tpl])
    
    # Add URL at the end
    cmd.append(url)
    
    return cmd

@app.route('/download', methods=['POST'])
def download():
    global current_process
    
    data = request.get_json()
    url = data.get("url")
    
    if not url:
        return Response("❌ Error: No URL provided\n", status=400, mimetype='text/plain')
    
    cmd = generate_command(data)
    
    def run_command():
        global current_process
        current_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in iter(current_process.stdout.readline, ''):
            yield line
        current_process.stdout.close()
    
    return Response(run_command(), mimetype='text/plain')

@app.route('/stop', methods=['POST'])
def stop_download():
    global current_process

    if current_process:
        current_process.send_signal(signal.SIGINT)
        current_process = None
        return jsonify({"status": "stopped"}), 200
    else:
        return jsonify({"error": "No download in progress"}), 400

@app.route('/detect-platform', methods=['POST'])
def detect_platform():
    data = request.get_json()
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
    
    return jsonify({"platform": platform})

if __name__ == '__main__':
    app.run(debug=True)
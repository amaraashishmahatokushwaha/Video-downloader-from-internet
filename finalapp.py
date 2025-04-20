from flask import Flask, request, Response, render_template, jsonify
import subprocess
import os
import signal
import re
import platform

app = Flask(__name__)

# Get system-specific downloads folder
def get_downloads_folder():
    # Detect OS and set appropriate downloads path
    system = platform.system()
    if system == "Windows":
        return os.path.join(os.path.expanduser("~"), "Downloads")
    elif system == "Darwin":  # macOS
        return os.path.join(os.path.expanduser("~"), "Downloads")
    elif system == "Linux":
        return os.path.join(os.path.expanduser("~"), "Downloads")
    else:
        # Fallback to a local folder
        return "downloads"

DOWNLOAD_FOLDER = get_downloads_folder()
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

current_process = None

# === HTML ROUTES ===
@app.route('/')
def index():
    return render_template('home.html')  # Your main homepage

@app.route('/youtube')
def youtube():
    return render_template('youtube.html')  # YouTube downloader UI

@app.route('/twitter', methods=['GET', 'POST'])
def twitter():
    if request.method == 'GET':
        return render_template('twitter.html')  # Twitter downloader UI
    elif request.method == 'POST':
        # Handle POST request - forward to download_twitter function
        return download_twitter()

# === COMMAND GENERATOR ===
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
    
    # === FIX FOR THE SOUND ISSUE ===
    # Force merging of video and audio streams
    cmd.append("--merge-output-format")
    cmd.append("mp4")
    
    # Format options
    if fmt == "mp3":
        cmd.extend(["--extract-audio", "--audio-format", "mp3"])
    elif fmt == "video-hd" or fmt == "video-sd":
        # For videos with sound, use the best format that has both video and audio
        cmd.extend(["-f", "best"])
    elif quality:
        cmd.extend(["-f", quality])
    else:
        cmd.extend(["-f", fmt])
    
    # Playlist handling
    if platform == "youtube":
        if is_playlist:
            cmd.append("--yes-playlist")
            if playlist_start:
                cmd.extend(["--playlist-start", playlist_start])
            if playlist_end:
                cmd.extend(["--playlist-end", playlist_end])
        else:
            cmd.append("--no-playlist")
    
    # Platform-specific tweaks
    if platform in ["instagram", "twitter"]:
        cmd.append("--no-warnings")
    
    if platform == "twitter":
        if fmt == "video-hd":
            # For Twitter HD videos with sound, use format selection with both video and audio
            cmd.extend(["-f", "best[height>=720]"])
        elif fmt == "video-sd":
            # For Twitter SD videos with sound, use format selection with both video and audio
            cmd.extend(["-f", "best[height<=480]"])
        elif fmt == "gif":
            cmd.extend(["--convert-to", "gif"])
        elif fmt == "image":
            cmd.extend(["-f", "image"])
    
    # Output templates
    if platform == "youtube" and is_playlist and create_folder:
        output_tpl = os.path.join(DOWNLOAD_FOLDER, "youtube/%(playlist_title)s/%(title)s.%(ext)s")
    elif platform == "instagram":
        output_tpl = os.path.join(DOWNLOAD_FOLDER, "instagram/%(uploader)s/%(title)s.%(ext)s")
    elif platform == "twitter":
        if data.get("isUser", False) and create_folder:
            output_tpl = os.path.join(DOWNLOAD_FOLDER, "twitter/%(uploader)s/%(title)s.%(ext)s")
        else:
            output_tpl = os.path.join(DOWNLOAD_FOLDER, "twitter/%(title)s.%(ext)s")
    else:
        output_tpl = os.path.join(DOWNLOAD_FOLDER, "youtube/%(title)s.%(ext)s")
    
    cmd.extend(["-o", output_tpl])
    cmd.append(url)
    
    return cmd

# === DOWNLOAD HANDLER ===
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
        yield f"📂 Saving to: {DOWNLOAD_FOLDER}\n"
        yield "⏳ Starting download...\n"
        
        current_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        for line in iter(current_process.stdout.readline, ''):
            if '[download]' in line and '%' in line:
                match = re.search(r'(\d+\.\d+)%', line)
                if match:
                    percentage = float(match.group(1))
                    yield f"Progress: {int(percentage)}%\n"
            yield line
        
        current_process.stdout.close()
        if current_process.wait() == 0:
            yield "✨ Download completed successfully!"
        else:
            yield "❌ Download failed. Please check the error messages above."
    
    return Response(run_command(), mimetype='text/plain')

# === TWITTER SPECIAL HANDLER ===
@app.route('/download/twitter', methods=['GET', 'POST'])
def download_twitter():
    data = request.get_json() or request.form.to_dict()
    url = data.get("url", "")
    
    if url.startswith('@') or (not url.startswith('http') and '/' not in url):
        username = url.replace('@', '')
        data["url"] = f"https://twitter.com/{username}"
        data["isUser"] = True

    if data.get("isUser", False):
        tweet_count = data.get("tweetCount", 50)
        include_retweets = data.get("includeRetweets", False)
        extra = f" ::{tweet_count}"
        if include_retweets:
            extra += " --include-retweets"
        data["url"] = data["url"] + extra
    
    data["platform"] = "twitter"
    
    return download()

# === STOP DOWNLOAD ===
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
    return stop_download()

# === PLATFORM DETECTOR ===
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

# === RUN APP ===
if __name__ == '__main__':
    app.run(debug=True)
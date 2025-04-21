from flask import Flask, request, Response, render_template, jsonify, send_file
import subprocess
import os
import signal
import re
import platform
import glob
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get system-specific downloads folder
def get_downloads_folder():
    system = platform.system()
    if system == "Windows":
        return os.path.join(os.path.expanduser("~"), "Downloads")
    elif system == "Darwin":  # macOS
        return os.path.join(os.path.expanduser("~"), "Downloads")
    elif system == "Linux":
        return os.path.join(os.path.expanduser("~"), "Downloads")
    else:
        return os.path.join(os.getcwd(), "downloads")

DOWNLOAD_FOLDER = get_downloads_folder()
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

current_process = None

# === HTML ROUTES ===
@app.route('/')
def index():
    return render_template('home.html')

@app.route('/youtube')
def youtube():
    return render_template('youtube.html')

@app.route('/twitter', methods=['GET', 'POST'])
def twitter():
    try:
        if request.method == 'GET':
            return render_template('twitter.html')
        elif request.method == 'POST':
            return download_twitter()
    except Exception as e:
        logger.error(f"Error in twitter route: {str(e)}")
        return Response(f"❌ Error: {str(e)}\n", status=500, mimetype='text/plain')

@app.route('/instagram', methods=['GET', 'POST'])
def instagram():
    if request.method == 'GET':
        return render_template('instafb.html')
    elif request.method == 'POST':
        return download_instagram()

@app.route('/facebook', methods=['GET', 'POST'])
def facebook():
    if request.method == 'GET':
        return render_template('instafb.html')
    elif request.method == 'POST':
        return download_facebook()

@app.route('/instafacebook', methods=['GET', 'POST'])
def instafacebook():
    if request.method == 'GET':
        return render_template('instafb.html')
    elif request.method == 'POST':
        return download_instafacebook()

# === FILE HANDLING ROUTES ===
@app.route('/files/<platform>', methods=['GET'])
def list_files(platform):
    files = []
    for root, _, filenames in os.walk(DOWNLOAD_FOLDER):
        for filename in filenames:
            if filename.endswith(('.mp4', '.jpg', '.jpeg', '.png', '.json')):
                relative_path = os.path.relpath(os.path.join(root, filename), DOWNLOAD_FOLDER)
                files.append(relative_path)
    return jsonify(files)

@app.route('/file/<platform>/<path:filename>', methods=['GET'])
def serve_file(platform, filename):
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return jsonify({"error": "File not found"}), 404

# === COOKIES UPLOAD ROUTE ===
@app.route('/upload-cookies', methods=['POST'])
def upload_cookies():
    if 'cookies' not in request.files:
        logger.error("No cookies file provided in upload request")
        return Response("❌ Error: No cookies file provided\n", status=400, mimetype='text/plain')
    
    cookies_file = request.files['cookies']
    if cookies_file.filename == '':
        logger.error("No file selected for cookies upload")
        return Response("❌ Error: No file selected\n", status=400, mimetype='text/plain')
    
    # Save the cookies file
    cookies_path = os.path.join(os.getcwd(), "cookies.txt")
    cookies_file.save(cookies_path)
    logger.info(f"Cookies file saved to: {cookies_path}")
    
    return Response("✅ Cookies file uploaded successfully\n", mimetype='text/plain')

# === COMMAND GENERATOR ===
def generate_command(data):
    url = data.get("url")
    fmt = data.get("format", "best")
    quality = data.get("quality", "bestvideo+bestaudio/best")
    is_playlist = data.get("isPlaylist", False)
    playlist_start = data.get("playlistStart")
    playlist_end = data.get("playlistEnd")
    platform = data.get("platform", "youtube")

    cmd = ["yt-dlp", "--no-warnings", "--progress", "--ignore-errors"]

    # Add cookies file for YouTube if it exists
    if platform == "youtube":
        cookies_file = "cookies.txt"
        if os.path.exists(cookies_file):
            cmd.extend(["--cookies", cookies_file])
            logger.info("Using cookies file for YouTube authentication")

    # Format and quality
    if platform == "youtube":
        if fmt == "mp3":
            cmd.extend(["--extract-audio", "--audio-format", "mp3"])
        elif fmt == "bestaudio[ext=m4a]":
            cmd.extend(["-f", "bestaudio[ext=m4a]"])
        elif quality and quality != "best":
            cmd.extend(["-f", quality])
        else:
            cmd.extend(["-f", fmt])
        
        # Playlist options
        if is_playlist:
            cmd.append("--yes-playlist")
            if playlist_start:
                cmd.extend(["--playlist-start", playlist_start])
            if playlist_end:
                cmd.extend(["--playlist-end", playlist_end])
        else:
            cmd.append("--no-playlist")
        
        # Output template
        output_tpl = os.path.join(DOWNLOAD_FOLDER, "%(title)s.%(ext)s")
    
    elif platform == "twitter":
        if fmt == "video-hd":
            cmd.extend(["-f", "bestvideo[height>=720]+bestaudio/best"])
        elif fmt == "video-sd":
            cmd.extend(["-f", "bestvideo[height<=480]+bestaudio/best"])
        elif fmt == "gif":
            cmd.extend(["--recode-video", "gif"])
        elif fmt == "image":
            cmd.extend(["-f", "bestimage"])
        else:
            cmd.extend(["-f", quality, "--merge-output-format", "mp4"])
        
        # Output template
        output_tpl = os.path.join(DOWNLOAD_FOLDER, "%(title)s.%(ext)s")
    
    elif platform == "instagram":
        if fmt in ["video", "post", "reel", "story"]:
            cmd.extend(["-f", quality, "--merge-output-format", "mp4"])
        elif fmt == "photo":
            cmd.extend(["-f", "bestimage"])
        elif fmt == "profile":
            cmd.extend(["-f", quality, "--merge-output-format", "mp4"])
        
        if fmt == "story":
            cmd.extend(["--match-filter", "is_story"])
        elif fmt == "post":
            cmd.extend(["--match-filter", "!is_story"])
        elif fmt == "reel":
            cmd.extend(["--match-filter", "description contains 'reel'"])
        if data.get("includeCaption", False):
            cmd.extend(["--write-info-json", "--write-description"])
        if data.get("isProfile", False):
            cmd.extend(["--playlist-end", str(data.get("contentCount", 12))])
        
        # Output template
        output_tpl = os.path.join(DOWNLOAD_FOLDER, "%(title)s.%(ext)s")
    
    elif platform == "facebook":
        if fmt == "video":
            cmd.extend(["-f", quality, "--merge-output-format", "mp4"])
        elif fmt == "photo":
            cmd.extend(["-f", "bestimage"])
        if data.get("includeText", False):
            cmd.extend(["--write-info-json", "--write-description"])
        if data.get("isPage", False):
            cmd.extend(["--playlist-end", str(data.get("videoCount", 10))])
        
        # Output template
        output_tpl = os.path.join(DOWNLOAD_FOLDER, "%(title)s.%(ext)s")

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
        logger.error("No URL provided in download request")
        return Response("❌ Error: No URL provided\n", status=400, mimetype='text/plain')

    try:
        cmd = generate_command(data)
        logger.debug(f"Generated command: {' '.join(cmd)}")
    except Exception as e:
        logger.error(f"Error generating command: {str(e)}")
        return Response(f"❌ Error generating command: {str(e)}\n", status=500, mimetype='text/plain')

    def run_command():
        global current_process
        yield f"🔍 Processing URL: {url}\n"
        yield f"🛠️ Running command: {' '.join(cmd)}\n"
        yield f"📂 Saving to: {DOWNLOAD_FOLDER}\n"
        yield "⏳ Starting download...\n"

        try:
            current_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in iter(current_process.stdout.readline, ''):
                if '[download]' in line and '%' in line:
                    match = re.search(r'(\d+\.\d+)%', line)
                    if match:
                        percentage = float(match.group(1))
                        yield f"Progress: {int(percentage)}%\n"
                if "Sign in to confirm" in line:
                    yield "❌ Error: YouTube requires authentication. Please upload a valid cookies file.\n"
                yield line

            current_process.stdout.close()
            return_code = current_process.wait()
            if return_code == 0:
                yield "✨ Download completed successfully!\n"
            else:
                yield f"❌ Download failed with return code {return_code}. Please check the error messages above.\n"
        except Exception as e:
            logger.error(f"Error running download command: {str(e)}")
            yield f"❌ Error: {str(e)}\n"
        finally:
            current_process = None

    return Response(run_command(), mimetype='text/plain')

# === TWITTER SPECIAL HANDLER ===
@app.route('/download/twitter', methods=['GET', 'POST'])
def download_twitter():
    try:
        data = request.get_json() or request.form.to_dict()
        url = data.get("url", "")

        if not url:
            logger.error("No URL provided in Twitter download request")
            return Response("❌ Error: No URL provided\n", status=400, mimetype='text/plain')

        logger.debug(f"Processing Twitter URL: {url}")

        if url.startswith('@') or (not url.startswith('http') and '/' not in url):
            username = url.replace('@', '')
            data["url"] = f"https://twitter.com/{username}"
            data["isUser"] = True
            logger.debug(f"Converted username to URL: {data['url']}")

        if data.get("isUser", False):
            tweet_count = data.get("tweetCount", 50)
            include_retweets = data.get("includeRetweets", False)
            extra = f" ::{tweet_count}"
            if include_retweets:
                extra += " --include-retweets"
            data["url"] = data["url"] + extra
            logger.debug(f"Updated URL with tweet count and retweets: {data['url']}")

        data["platform"] = "twitter"
        return download()
    except Exception as e:
        logger.error(f"Error in download_twitter: {str(e)}")
        return Response(f"❌ Error: {str(e)}\n", status=500, mimetype='text/plain')

# === INSTAGRAM SPECIAL HANDLER ===
@app.route('/download/instagram', methods=['POST'])
def download_instagram():
    data = request.get_json() or request.form.to_dict()
    url = data.get("url", "")

    if url.startswith('@') or (not url.startswith('http') and '/' not in url):
        username = url.replace('@', '')
        data["url"] = f"https://www.instagram.com/{username}/"
        data["isProfile"] = True

    data["platform"] = "instagram"
    return download()

# === FACEBOOK SPECIAL HANDLER ===
@app.route('/download/facebook', methods=['POST'])
def download_facebook():
    data = request.get_json() or request.form.to_dict()
    url = data.get("url", "")

    if not url.startswith('http') and '/' not in url:
        page_name = url
        data["url"] = f"https://www.facebook.com/{page_name}/"
        data["isPage"] = True

    data["platform"] = "facebook"
    return download()

# === COMBINED INSTAGRAM/FACEBOOK HANDLER ===
@app.route('/download/instafacebook', methods=['POST'])
def download_instafacebook():
    data = request.get_json() or request.form.to_dict()
    platform = data.get("platform", "")

    if platform == "instagram":
        return download_instagram()
    elif platform == "facebook":
        return download_facebook()
    else:
        return Response("❌ Error: Invalid platform specified\n", status=400, mimetype='text/plain')

# === STOP DOWNLOAD ===
@app.route('/stop', methods=['POST'])
def stop_download():
    global current_process
    if current_process:
        try:
            current_process.send_signal(signal.SIGINT)
            current_process = None
            logger.info("Download stopped successfully")
            return jsonify({"status": "stopped"}), 200
        except Exception as e:
            logger.error(f"Error stopping download: {str(e)}")
            return jsonify({"error": str(e)}), 500
    else:
        logger.warning("No download in progress to stop")
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
        is_profile = "/p/" not in url and "/reel/" not in url
        return jsonify({"platform": platform, "isProfile": is_profile})
    elif "twitter.com" in url or "x.com" in url:
        platform = "twitter"
        is_user = "/status/" not in url
        return jsonify({"platform": platform, "isUser": is_user})
    elif "facebook.com" in url or "fb.com" in url or "fb.watch" in url:
        platform = "facebook"
        is_page = "/videos/" not in url and "/watch/" not in url
        return jsonify({"platform": platform, "isPage": is_page})

    return jsonify({"platform": platform})

# === RUN APP ===
if __name__ == '__main__':
    app.run(debug=True)
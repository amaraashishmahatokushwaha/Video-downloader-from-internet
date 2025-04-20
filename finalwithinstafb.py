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
    platform_folder = os.path.join(DOWNLOAD_FOLDER, platform)
    files = []
    if os.path.exists(platform_folder):
        for root, _, filenames in os.walk(platform_folder):
            for filename in filenames:
                if filename.endswith(('.mp4', '.jpg', '.jpeg', '.png', '.json')):
                    relative_path = os.path.relpath(os.path.join(root, filename), platform_folder)
                    files.append(relative_path)
    return jsonify(files)

@app.route('/file/<platform>/<path:filename>', methods=['GET'])
def serve_file(platform, filename):
    file_path = os.path.join(DOWNLOAD_FOLDER, platform, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return jsonify({"error": "File not found"}), 404

# === COMMAND GENERATOR ===
def generate_command(data):
    url = data.get("url")
    fmt = data.get("format", "best")
    quality = "bestvideo+bestaudio/best" if data.get("highestQuality", False) or data.get("highQuality", False) else "best"
    create_folder = True
    platform = data.get("platform", "youtube")

    cmd = ["yt-dlp", "--no-warnings", "--progress"]

    # Format and quality
    if platform == "twitter":
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
    elif fmt in ["video", "post", "reel", "story"]:
        cmd.extend(["-f", quality, "--merge-output-format", "mp4"])
    elif fmt == "photo":
        cmd.extend(["-f", "bestimage"])
    elif fmt == "profile" or fmt == "page":
        cmd.extend(["-f", quality, "--merge-output-format", "mp4"])

    # Platform-specific tweaks
    if platform == "instagram":
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

    elif platform == "facebook":
        if fmt == "video":
            cmd.extend(["-f", quality, "--merge-output-format", "mp4"])
        elif fmt == "photo":
            cmd.extend(["-f", "bestimage"])
        if data.get("includeText", False):
            cmd.extend(["--write-info-json", "--write-description"])
        if data.get("isPage", False):
            cmd.extend(["--playlist-end", str(data.get("videoCount", 10))])

    # Output templates
    if platform == "twitter":
        if data.get("isUser", False) and create_folder:
            output_tpl = os.path.join(DOWNLOAD_FOLDER, "twitter/%(uploader)s/%(title)s.%(ext)s")
        else:
            output_tpl = os.path.join(DOWNLOAD_FOLDER, "twitter/%(title)s.%(ext)s")
    elif platform == "instagram":
        if data.get("isProfile", False) and create_folder:
            output_tpl = os.path.join(DOWNLOAD_FOLDER, "instagram/%(uploader)s/%(title)s.%(ext)s")
        else:
            output_tpl = os.path.join(DOWNLOAD_FOLDER, "instagram/%(title)s.%(ext)s")
    elif platform == "facebook":
        if data.get("isPage", False) and create_folder:
            output_tpl = os.path.join(DOWNLOAD_FOLDER, "facebook/%(uploader)s/%(title)s.%(ext)s")
        else:
            output_tpl = os.path.join(DOWNLOAD_FOLDER, "facebook/%(title)s.%(ext)s")
    else:
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

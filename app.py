from flask import Flask, request, Response, render_template
import subprocess
import os
import signal

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

current_process = None

@app.route('/')
def index():
    return render_template('index.html')

def generate_command(url, fmt):
    if fmt == "mp3":
        return [
            "yt-dlp", "--extract-audio", "--audio-format", "mp3",
            "-o", os.path.join(DOWNLOAD_FOLDER, "%(title)s.%(ext)s"), url
        ]
    elif fmt == "playlist":
        return [
            "yt-dlp", "-f", "bestvideo+bestaudio",
            "--yes-playlist",
            "-o", os.path.join(DOWNLOAD_FOLDER, "%(playlist_title)s/%(title)s.%(ext)s"),
            url
        ]
    else:
        return [
            "yt-dlp", "-f", fmt,
            "-o", os.path.join(DOWNLOAD_FOLDER, "%(title)s.%(ext)s"),
            url
        ]

@app.route('/download', methods=['POST'])
def download():
    global current_process

    data = request.get_json()
    url = data.get("url")
    fmt = data.get("format", "best")

    if not url:
        return Response("❌ Error: No URL provided\n", status=400, mimetype='text/plain')

    cmd = generate_command(url, fmt)

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

if __name__ == '__main__':
    app.run(debug=True)

"""
YT Downloader UI - Web Edition
Educational demo: a Flask web app that wraps yt-dlp + ffmpeg so you can
fetch video info and download media through a browser instead of a
Windows desktop GUI.

IMPORTANT: Only use this to download content you have the right to
download (your own videos, public domain works, Creative Commons media,
or content you have explicit permission to save). Downloading copyrighted
videos you don't have rights to may violate YouTube's Terms of Service
and copyright law.
"""

import os
import re
import shutil
import tempfile
import threading
import uuid

from flask import Flask, jsonify, request, send_file, after_this_request
import yt_dlp

app = Flask(__name__, static_folder="static", static_url_path="")

DOWNLOAD_ROOT = os.path.join(tempfile.gettempdir(), "ytdlweb_downloads")
os.makedirs(DOWNLOAD_ROOT, exist_ok=True)

URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def ffmpeg_available():
    return shutil.which("ffmpeg") is not None


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/health")
def health():
    return jsonify({
        "ok": True,
        "ffmpeg_found": ffmpeg_available(),
    })


@app.route("/api/info", methods=["POST"])
def info():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url or not URL_RE.match(url):
        return jsonify({"error": "Please provide a valid http(s) URL."}), 400

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        return jsonify({"error": f"Could not fetch info: {e}"}), 400
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"Unexpected error: {e}"}), 500

    if result is None:
        return jsonify({"error": "No video info found for that URL."}), 400

    duration = result.get("duration")
    duration_str = None
    if duration:
        m, s = divmod(int(duration), 60)
        h, m = divmod(m, 60)
        duration_str = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    return jsonify({
        "title": result.get("title"),
        "uploader": result.get("uploader") or result.get("channel"),
        "thumbnail": result.get("thumbnail"),
        "duration": duration_str,
        "webpage_url": result.get("webpage_url", url),
    })


# Quality presets, mapped to yt-dlp format selectors.
QUALITY_PRESETS = {
    "best": {"format": "bestvideo+bestaudio/best", "ext": "mp4", "audio_only": False},
    "1080p": {"format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]", "ext": "mp4", "audio_only": False},
    "720p": {"format": "bestvideo[height<=720]+bestaudio/best[height<=720]", "ext": "mp4", "audio_only": False},
    "480p": {"format": "bestvideo[height<=480]+bestaudio/best[height<=480]", "ext": "mp4", "audio_only": False},
    "audio_mp3": {"format": "bestaudio/best", "ext": "mp3", "audio_only": True},
}


@app.route("/api/download", methods=["POST"])
def download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    quality = data.get("quality", "best")

    if not url or not URL_RE.match(url):
        return jsonify({"error": "Please provide a valid http(s) URL."}), 400

    preset = QUALITY_PRESETS.get(quality)
    if not preset:
        return jsonify({"error": "Unknown quality option."}), 400

    if preset["audio_only"] and not ffmpeg_available():
        return jsonify({"error": "ffmpeg is required for MP3 extraction and was not found on PATH."}), 400

    job_id = uuid.uuid4().hex
    job_dir = os.path.join(DOWNLOAD_ROOT, job_id)
    os.makedirs(job_dir, exist_ok=True)

    outtmpl = os.path.join(job_dir, "%(title).100s.%(ext)s")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": preset["format"],
        "outtmpl": outtmpl,
        "merge_output_format": "mp4" if not preset["audio_only"] else None,
    }

    if preset["audio_only"]:
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as e:
        shutil.rmtree(job_dir, ignore_errors=True)
        return jsonify({"error": f"Download failed: {e}"}), 400
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(job_dir, ignore_errors=True)
        return jsonify({"error": f"Unexpected error: {e}"}), 500

    files = os.listdir(job_dir)
    if not files:
        shutil.rmtree(job_dir, ignore_errors=True)
        return jsonify({"error": "Download completed but no output file was found."}), 500

    file_path = os.path.join(job_dir, files[0])

    @after_this_request
    def cleanup(response):
        def _delete():
            shutil.rmtree(job_dir, ignore_errors=True)
        threading.Timer(5.0, _delete).start()
        return response

    return send_file(file_path, as_attachment=True, download_name=files[0])


if __name__ == "__main__":
    print("Starting YT Downloader UI - Web Edition")
    print(f"ffmpeg found: {ffmpeg_available()}")
    app.run(host="127.0.0.1", port=5000, debug=False)

"""
YT Downloader UI - Web Edition
Educational demo: a Flask web app that wraps yt-dlp + ffmpeg so you can
fetch video info and download media through a browser instead of a
Windows desktop GUI.

Downloads run as background jobs so the HTTP request returns instantly.
Progress (percent, speed, ETA, status) is tracked from yt-dlp's real
progress_hooks/postprocessor_hooks and exposed via a polling endpoint.

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
import time
import uuid

from flask import Flask, jsonify, request, send_file, after_this_request
import yt_dlp

app = Flask(__name__, static_folder="static", static_url_path="")

DOWNLOAD_ROOT = os.path.join(tempfile.gettempdir(), "ytdlweb_downloads")
os.makedirs(DOWNLOAD_ROOT, exist_ok=True)

URL_RE = re.compile(r"^https?://", re.IGNORECASE)

# ---------------------------------------------------------------------------
# In-memory job store
# ---------------------------------------------------------------------------
# JOBS[job_id] = {
#     "status": "starting" | "downloading" | "postprocessing" | "finished" | "error",
#     "percent": float,
#     "downloaded_bytes": int,
#     "total_bytes": int | None,
#     "speed": float | None,        # bytes/sec
#     "eta": int | None,            # seconds
#     "error": str | None,
#     "filename": str | None,       # set once finished
#     "_job_dir": str,              # internal, never sent to client
#     "_file_path": str | None,     # internal, never sent to client
# }
JOBS = {}
JOBS_LOCK = threading.Lock()

QUALITY_PRESETS = {
    "best": {"format": "bestvideo+bestaudio/best", "audio_only": False},
    "1080p": {"format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]", "audio_only": False},
    "720p": {"format": "bestvideo[height<=720]+bestaudio/best[height<=720]", "audio_only": False},
    "480p": {"format": "bestvideo[height<=480]+bestaudio/best[height<=480]", "audio_only": False},
    "audio_mp3": {"format": "bestaudio/best", "audio_only": True},
}


def ffmpeg_available():
    return shutil.which("ffmpeg") is not None


def _update_job(job_id, **fields):
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(fields)


def _public_job_view(job):
    """Strip internal fields before sending a job to the client."""
    return {
        "status": job.get("status"),
        "percent": job.get("percent", 0),
        "downloaded_bytes": job.get("downloaded_bytes", 0),
        "total_bytes": job.get("total_bytes"),
        "speed": job.get("speed"),
        "eta": job.get("eta"),
        "error": job.get("error"),
        "filename": job.get("filename"),
    }


def _make_progress_hook(job_id):
    def hook(d):
        status = d.get("status")

        if status == "downloading":
            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            percent = (downloaded / total * 100) if total else 0
            _update_job(
                job_id,
                status="downloading",
                percent=round(percent, 1),
                downloaded_bytes=downloaded,
                total_bytes=total,
                speed=d.get("speed"),
                eta=d.get("eta"),
            )
        elif status == "finished":
            # One stream (video or audio) finished downloading; merging /
            # postprocessing may follow. Don't mark the whole job finished yet.
            _update_job(job_id, status="postprocessing", percent=100)
        elif status == "error":
            _update_job(job_id, status="error", error="yt-dlp reported a download error.")

    return hook


def _make_postprocessor_hook(job_id):
    def hook(d):
        if d.get("status") == "started":
            _update_job(job_id, status="postprocessing")
        elif d.get("status") == "finished":
            # Postprocessing step done; overall job is finalized after
            # ydl.download() returns in the worker thread.
            _update_job(job_id, status="postprocessing")

    return hook


def _run_download_job(job_id, url, quality):
    preset = QUALITY_PRESETS[quality]
    job_dir = JOBS[job_id]["_job_dir"]
    outtmpl = os.path.join(job_dir, "%(title).100s.%(ext)s")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": preset["format"],
        "outtmpl": outtmpl,
        "progress_hooks": [_make_progress_hook(job_id)],
        "postprocessor_hooks": [_make_postprocessor_hook(job_id)],
    }

    if preset["audio_only"]:
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    else:
        ydl_opts["merge_output_format"] = "mp4"

    try:
        _update_job(job_id, status="downloading")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        files = os.listdir(job_dir)
        if not files:
            _update_job(job_id, status="error", error="Download finished but no output file was found.")
            return

        file_path = os.path.join(job_dir, files[0])
        _update_job(
            job_id,
            status="finished",
            percent=100,
            filename=files[0],
            _file_path=file_path,
        )
    except yt_dlp.utils.DownloadError as e:
        _update_job(job_id, status="error", error=f"Download failed: {e}")
    except Exception as e:  # noqa: BLE001
        _update_job(job_id, status="error", error=f"Unexpected error: {e}")


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/health")
def health():
    return jsonify({"ok": True, "ffmpeg_found": ffmpeg_available()})


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

    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "starting",
            "percent": 0,
            "downloaded_bytes": 0,
            "total_bytes": None,
            "speed": None,
            "eta": None,
            "error": None,
            "filename": None,
            "_job_dir": job_dir,
            "_file_path": None,
        }

    thread = threading.Thread(target=_run_download_job, args=(job_id, url, quality), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id}), 202


@app.route("/api/progress/<job_id>")
def progress(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return jsonify({"error": "Unknown job_id."}), 404
        view = _public_job_view(job)
    return jsonify(view)


@app.route("/api/file/<job_id>")
def file(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return jsonify({"error": "Unknown job_id."}), 404
        if job["status"] != "finished" or not job["_file_path"]:
            return jsonify({"error": "File is not ready yet."}), 400
        file_path = job["_file_path"]
        filename = job["filename"]
        job_dir = job["_job_dir"]

    @after_this_request
    def cleanup(response):
        def _delete():
            shutil.rmtree(job_dir, ignore_errors=True)
            with JOBS_LOCK:
                JOBS.pop(job_id, None)
        threading.Timer(5.0, _delete).start()
        return response

    return send_file(file_path, as_attachment=True, download_name=filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    print("Starting YT Downloader UI - Web Edition")
    print(f"ffmpeg found: {ffmpeg_available()}")

    app.run(host="0.0.0.0", port=port, debug=False)

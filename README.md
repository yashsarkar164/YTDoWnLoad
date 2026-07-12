# YT Downloader UI — Web Edition

A browser-based version of the yt-dlp desktop GUI: paste a video URL, see its
title/thumbnail/duration, pick a quality, and download it straight from your
browser. It's a small Flask app that calls `yt-dlp` and `ffmpeg` under the hood.

> **Use responsibly.** Only download videos you own, that are public domain,
> Creative Commons licensed, or that you have explicit permission to save.
> Downloading copyrighted content without permission can violate YouTube's
> Terms of Service and copyright law. This project is for learning how a
> download manager UI and backend fit together.

## What's included
```
ytdl-web/
├── app.py              # Flask backend (info + download endpoints)
├── requirements.txt     # Python dependencies
├── static/
│   ├── index.html      # Page structure
│   ├── style.css        # Styling
│   └── script.js         # Frontend logic (fetch info, trigger download)
└── README.md
```

## Prerequisites
1. **Python 3.9+**
2. **ffmpeg** — required for merging video/audio and for MP3 extraction.
   - Windows: download from https://www.gyan.dev/ffmpeg/builds/ and add the
     `bin` folder to your PATH.
   - macOS: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg` (Debian/Ubuntu) or your distro's equivalent
3. Some videos require yt-dlp's JavaScript-challenge solver, which depends on
   **Node.js** being installed and on PATH (same requirement as the original
   desktop app). Get it from https://nodejs.org if downloads fail with a
   JS-related error.

## Setup
```bash
cd ytdl-web
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Run
```bash
python app.py
```
Then open **http://127.0.0.1:5000** in your browser.

## How it works
- **Fetch Info** calls `POST /api/info`, which uses `yt-dlp` in
  metadata-only mode (`skip_download`) to pull the title, uploader,
  thumbnail, and duration.
- **Download** calls `POST /api/download`, which runs `yt-dlp` with a format
  selector matching your chosen quality, merges video+audio (or extracts
  MP3 audio) with `ffmpeg`, and streams the finished file back to your
  browser as a normal download. Temp files are cleaned up automatically
  a few seconds after sending.

## Quality options
| Option            | What it does                                   |
|--------------------|-------------------------------------------------|
| Best available     | Highest quality video+audio yt-dlp can find     |
| 1080p / 720p / 480p | Caps the video resolution                       |
| Audio only (MP3)   | Extracts audio track and converts to MP3 (192kbps) |

## Notes on keeping yt-dlp working
YouTube frequently changes its site, which can break extraction. Keep
yt-dlp current with:
```bash
pip install -U yt-dlp
```

## Deploying beyond localhost
This app is meant to run on your own machine for personal/educational use.
If you host it anywhere multi-user, add authentication, rate limiting, and
review the legal implications for your jurisdiction — you'd be operating a
public download service, which carries different responsibilities than a
personal tool.

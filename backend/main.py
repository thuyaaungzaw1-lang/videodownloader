import os
import uuid
import subprocess

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import yt_dlp

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Serve static files
app.mount("/files", StaticFiles(directory=DOWNLOAD_DIR), name="files")

# frontend-side constant
SPECIAL_AUDIO_FORMAT = "bestaudio[ext=m4a]/bestaudio"


@app.get("/")
def root():
    return {"status": "ok", "message": "ThuYaAungZaw Video Downloader API (FFmpeg/H264)"}


# ------------------------------------------------------------
#  FORMATS
# ------------------------------------------------------------
@app.get("/formats")
def get_formats(url: str):
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "nocheckcertificate": True,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        extractor = (info.get("extractor") or "").lower()
        fmts = []

        for f in info.get("formats", []):
            vcodec = (f.get("vcodec") or "").lower()
            ext = (f.get("ext") or "").lower()

            # audio-only formats မပါအောင်ရယ်
            if vcodec == "none":
                continue

            # mp4 ကိုပဲ ထားမယ် (YouTube မှာတောင် ffmpeg နဲ့ mp4 ထုတ်မယ်)
            if ext != "mp4":
                continue

            height = f.get("height") or 0
            fps = f.get("fps")

            label_parts = []
            if height:
                label_parts.append(f"{height}p")
            if fps:
                label_parts.append(f"{fps}fps")

            if label_parts:
                label = " ".join(label_parts)
            else:
                label = f.get("format_note") or f.get("format_id") or "MP4"

            fmts.append(
                {
                    "format_id": f.get("format_id"),
                    "label": label,
                    "height": height,
                }
            )

        # အမြင့်ဆုံး resolution ကအပေါ်ဆုံး ဖြစ်အောင်
        fmts.sort(key=lambda x: x["height"], reverse=True)
        for f in fmts:
            f.pop("height", None)

        return {"formats": fmts}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------
#  INTERNAL DOWNLOAD HELPERS
# ------------------------------------------------------------

def download_audio(url: str, format_expr: str) -> str:
    """
    Audio only (MP3 / M4A) – MP3 already OK so just download bestaudio.
    """
    out_base = str(uuid.uuid4())
    out_tmpl = os.path.join(DOWNLOAD_DIR, out_base + ".%(ext)s")

    ydl_opts = {
        "format": format_expr,              # e.g. bestaudio[ext=m4a]/bestaudio
        "outtmpl": out_tmpl,
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)

    # path = downloads/<uuid>.m4a (or .webm / .opus etc)
    filename = os.path.basename(path)
    return filename


def download_video_h264(url: str, format_id: str) -> str:
    """
    Video download + FFmpeg re-encode to H.264 + AAC (iPhone/Safari-safe mp4).
    """
    # temp raw path (youtube vp9/av1 etc)
    base = str(uuid.uuid4())
    temp_path = os.path.join(DOWNLOAD_DIR, base + "_raw.%(ext)s")
    final_path = os.path.join(DOWNLOAD_DIR, base + ".mp4")

    # first: download chosen video format + best audio
    ydl_opts = {
        "format": f"{format_id}+bestaudio/best",
        "outtmpl": temp_path,
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "merge_output_format": "mp4",
    }

    # Download
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # merged output path (mp4)
        raw_path = ydl.prepare_filename(info)

    # now raw_path -> re-encode to H.264 + AAC (always mp4)
    # iOS / Safari playable settings
    cmd = [
        "ffmpeg",
        "-y",
        "-i", raw_path,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        final_path,
    ]

    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # remove raw file
    try:
        os.remove(raw_path)
    except Exception:
        pass

    return os.path.basename(final_path)


# ------------------------------------------------------------
#  DOWNLOAD ENDPOINT
# ------------------------------------------------------------
@app.get("/download")
def download(url: str, format_id: str):
    if not url or not format_id:
        raise HTTPException(status_code=400, detail="Missing url or format_id")

    try:
        # Audio-only option from frontend
        if format_id == SPECIAL_AUDIO_FORMAT or format_id.startswith("bestaudio"):
            filename = download_audio(url, format_id)
        else:
            filename = download_video_h264(url, format_id)

        return {
            "download_url": f"/file/{filename}",
            "filename": filename,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------
#  SERVE FILE
# ------------------------------------------------------------
@app.get("/file/{filename}")
def get_file(filename: str):
    path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    lower = filename.lower()
    # simple mime detection
    if lower.endswith(".mp3") or lower.endswith(".m4a") or lower.endswith(".aac") \
       or lower.endswith(".opus") or lower.endswith(".webm"):
        media_type = "audio/mpeg"
    else:
        media_type = "video/mp4"

    return FileResponse(path, media_type=media_type, filename=filename)

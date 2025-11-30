from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import yt_dlp
import os

app = FastAPI()

# ---------------------- CORS ----------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app.mount("/files", StaticFiles(directory=DOWNLOAD_DIR), name="files")


@app.get("/")
def root():
    return {"status": "ok", "message": "ThuYaAungZaw Video Downloader API"}


# ---------------------- FORMATS ----------------------
@app.get("/formats")
def get_formats(url: str):
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    # YouTube progressive safe mode (no DASH, no HLS)
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "nocheckcertificate": True,
        "extractor_args": {
            "youtube": {
                "skip": ["dash", "hls"],
                "player_client": ["web"],
            }
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = []
        for f in info.get("formats", []):
            if f.get("vcodec") == "none":
                continue
            if f.get("ext") != "mp4":
                continue

            height = f.get("height")
            fps = f.get("fps")
            label = ""
            if height:
                label += f"{height}p"
            if fps:
                label += f" {fps}fps"

            formats.append({
                "format_id": f.get("format_id"),
                "label": label if label else f.get("format_id")
            })

        # Sort high → low
        formats.sort(
            key=lambda x: int(x["label"].split("p")[0]) if "p" in x["label"] else 0,
            reverse=True
        )

        if not formats:
            raise HTTPException(status_code=404, detail="No formats found")

        return {"formats": formats}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------- DOWNLOAD ----------------------
def download_with_ytdlp(url: str, format_id: str) -> str:
    ydl_opts = {
        "format": format_id,
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "extractor_args": {
            "youtube": {
                "skip": ["dash", "hls"],
                "player_client": ["web"],
            }
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return os.path.basename(ydl.prepare_filename(info))


@app.get("/download")
def download(url: str, format_id: str):
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    if not format_id:
        raise HTTPException(status_code=400, detail="format_id is required")

    try:
        filename = download_with_ytdlp(url, format_id)
        return {"download_url": f"/file/{filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------- SERVE FILE ----------------------
@app.get("/file/{filename}")
def get_file(filename: str):
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path, media_type="video/mp4", filename=filename)

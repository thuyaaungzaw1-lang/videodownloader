from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import yt_dlp
import os

app = FastAPI()

# CORS allow all
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Folder for saving downloads
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Serve files
app.mount("/files", StaticFiles(directory=DOWNLOAD_DIR), name="files")


@app.get("/")
def root():
    return {"status": "ok", "message": "ThuYaAungZaw Video Downloader API"}


# ---------- FORMATS ENDPOINT ----------
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

        results = []
        for f in info.get("formats", []):
            # Skip unusable formats
            if f.get("vcodec") == "none":
                continue
            if f.get("acodec") == "none":
                continue
            if f.get("ext") != "mp4":
                continue

            height = f.get("height")
            if not height:
                res = f.get("resolution")
                if res and "x" in res:
                    try:
                        height = int(res.split("x")[1])
                    except:
                        height = None

            # Guess resolution for Facebook "sd / hd"
            note = (f.get("format_note") or "").lower()
            if not height:
                if "1080" in note:
                    height = 1080
                elif "720" in note or "hd" in note:
                    height = 720
                elif "480" in note or "sd" in note:
                    height = 480

            # Create clean label
            if height:
                label = f"{height}p"
            else:
                label = f.get("format_note") or f.get("format_id")

            results.append({
                "format_id": f.get("format_id"),
                "label": label,
                "height": height or 0
            })

        results.sort(key=lambda x: x["height"], reverse=True)
        for r in results:
            r.pop("height", None)

        return {"formats": results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------- DOWNLOAD FUNCTION ----------
def download_with_ytdlp(url: str, format_id: str) -> str:

    # YouTube ALWAYS needs merge (video-only problem fix)
    if "youtube" in url or "youtu.be" in url:
        real_format = f"{format_id}+bestaudio/best"
    else:
        real_format = format_id

    ydl_opts = {
        "format": real_format,
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "merge_output_format": "mp4"
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return os.path.basename(filename)


# ---------- DOWNLOAD ENDPOINT ----------
@app.get("/download")
def download(url: str, format_id: str):
    if not url or not format_id:
        raise HTTPException(status_code=400, detail="Missing url or format_id")

    try:
        filename = download_with_ytdlp(url, format_id)
        return {
            "download_url": f"/file/{filename}",
            "filename": filename,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------- FILE SERVE ----------
@app.get("/file/{filename}")
def get_file(filename: str):
    path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    if filename.endswith(".mp3") or filename.endswith(".m4a"):
        mime = "audio/mpeg"
    else:
        mime = "video/mp4"

    return FileResponse(path, media_type=mime, filename=filename)
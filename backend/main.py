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


# 1) Get formats
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

        fmts = []
        for f in info.get("formats", []):
            if f.get("vcodec") == "none":
                continue
            if f.get("ext") != "mp4":
                continue

            height = f.get("height")
            fps = f.get("fps")
            label_parts = []
            if height:
                label_parts.append(f"{height}p")
            if fps:
                label_parts.append(f"{fps}fps")

            fmts.append({
                "format_id": f.get("format_id"),
                "label": " ".join(label_parts) if label_parts else f.get("format_id")
            })

        fmts.sort(key=lambda x: int(x["label"].split("p")[0]) if "p" in x["label"] else 0, reverse=True)

        return {"formats": fmts}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 2) Download with yt-dlp
def download_with_ytdlp(url: str, format_id: str) -> str:
    ydl_opts = {
        "format": format_id,
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return os.path.basename(filename)


# 3) Download endpoint
@app.get("/download")
def download(url: str, format_id: str):
    if not url or not format_id:
        raise HTTPException(status_code=400, detail="Missing url or format_id")

    try:
        filename = download_with_ytdlp(url, format_id)

        return {
            "download_url": f"/file/{filename}",
            "filename": filename
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 4) Serve file
@app.get("/file/{filename}")
def get_file(filename: str):
    path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path, media_type="video/mp4", filename=filename)

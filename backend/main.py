from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import yt_dlp
import os

app = FastAPI()

# CORS – frontend 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# optional: direct file serve 
app.mount("/files", StaticFiles(directory=DOWNLOAD_DIR), name="files")


@app.get("/")
def root():
    return {"status": "ok", "message": "ThuYaAungZaw Video Downloader API"}


# ---------- 1) Formats list (720p / 1080p) ----------

@app.get("/formats")
def get_formats(url: str):
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "nocheckcertificate": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = []
        for f in info.get("formats", []):
          
            if f.get("vcodec") == "none":
                continue
            if f.get("acodec") == "none":
                continue
            if f.get("ext") != "mp4":
                continue

            height = f.get("height")
            fps = f.get("fps")
            filesize = f.get("filesize") or f.get("filesize_approx")

            label_parts = []
            if height:
                label_parts.append(f"{height}p")
            if fps:
                label_parts.append(f"{fps}fps")

            label = " ".join(label_parts) or f.get("format_note") or f.get("format_id")

            formats.append(
                {
                    "format_id": f.get("format_id"),
                    "label": label,
                    "filesize": filesize,
                }
            )

        def sort_key(x):
            text = x["label"]
            if "p" in text:
                try:
                    return int(text.split("p")[0])
                except ValueError:
                    return 0
            return 0

        formats.sort(key=sort_key, reverse=True)

        if not formats:
            raise HTTPException(status_code=404, detail="No downloadable formats found")

        return {"formats": formats}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------- 2) download chosen format ----------

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


# ---------- 3) Serve file as download ----------

@app.get("/file/{filename}")
def get_file(filename: str):
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        file_path,
        media_type="video/mp4",
        filename=filename,
    )

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import yt_dlp
import os

app = FastAPI()

# ✅ CORS – allow frontend (GitHub Pages) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Static files (downloaded videos)
app.mount("/files", StaticFiles(directory=DOWNLOAD_DIR), name="files")


def download_with_ytdlp(url: str) -> str:
    """
    URL ပေးရင် video ကို downloads/ helper function
    return က file basename (e.g. 'abc123.mp4')
    """
    ydl_opts = {
        "format": "mp4/best/bestvideo+bestaudio",
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "quiet": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)  # downloads/abc123.mp4 
        return os.path.basename(filename)


@app.get("/download")
def download(url: str):
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    try:
        filename = download_with_ytdlp(url)
        # frontend မှာ API_BASE + /files/{filename} 
        return {"download_url": f"/files/{filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

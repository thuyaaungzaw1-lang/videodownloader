from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import yt_dlp
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # production မှာ domain ထည့်သင့်ပေမဲ့ demo အတွက် *
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# static mount (လိုချင်ရင်ချန်ထားရင်ရ) – direct link ကြိုက္ရင်သုံးလို့ရသေးတယ်
app.mount("/files", StaticFiles(directory=DOWNLOAD_DIR), name="files")


def download_with_ytdlp(url: str) -> str:
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
        # frontend မှာ /file/xxx.mp4 ကိုသုံးမယ်
        return {"download_url": f"/file/{filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/file/{filename}")
def get_file(filename: str):
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Content-Disposition: attachment => browser ကို download လုပ်ခိုင်းခြင်း
    return FileResponse(
        file_path,
        media_type="video/mp4",
        filename=filename,
    )

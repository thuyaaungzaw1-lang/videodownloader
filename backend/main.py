from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import yt_dlp
import os

app = FastAPI()

# --------- CORS (frontend GitHub Pages က ခေါ်ရအောင်) ----------
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


# --------- 1) formats endpoint ----------
@app.get("/formats")
def get_formats(url: str):
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    # yt-dlp ကို default web client နဲ့ပဲ သုံးမယ်
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
            # video မပါတဲ့ format တွေကျော်
            if f.get("vcodec") == "none":
                continue

            # mp4 format လိုချင်လို့ mp4 ပဲထားမယ်
            if f.get("ext") != "mp4":
                continue

            height = f.get("height")
            fps = f.get("fps")

            parts = []
            if height:
                parts.append(f"{height}p")
            if fps:
                parts.append(f"{fps}fps")

            label = " ".join(parts) if parts else f.get("format_id")

            fmts.append(
                {
                    "format_id": f.get("format_id"),
                    "label": label,
                }
            )

        # resolution အမြင့်အနိမ့် 排序
        def sort_key(x):
            text = x["label"]
            if "p" in text:
                try:
                    return int(text.split("p")[0])
                except ValueError:
                    return 0
            return 0

        fmts.sort(key=sort_key, reverse=True)

        if not fmts:
            raise HTTPException(status_code=404, detail="No downloadable formats found")

        return {"formats": fmts}

    except yt_dlp.utils.DownloadError as e:
        # YouTube မှာ protection ကြောင့်မရတဲ့ case တွေ – စာအကြောင်းရှင်းရှင်းပြန်ပေးမယ်
        raise HTTPException(status_code=500, detail=f"Extractor error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --------- 2) url + format_id နဲ့ ဖိုင်ကို download ဆွဲမယ် ----------
def download_with_ytdlp(url: str, format_id: str) -> str:
    ydl_opts = {
        # frontend ကပို့လာတဲ့ format_id ကို တိတိအသုံးပြုမယ်
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
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=500, detail=f"Download error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --------- 3) ဖိုင်ကို client ကို serve ပြန်ပေးမယ် ----------
@app.get("/file/{filename}")
def get_file(filename: str):
    path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path, media_type="video/mp4", filename=filename)

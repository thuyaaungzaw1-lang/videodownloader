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


# 1) Get formats (for resolution dropdown)
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
            # audio / video မပါတဲ့ format တွေ filter
            if f.get("vcodec") == "none":
                continue
            if f.get("acodec") == "none":
                continue
            if f.get("ext") != "mp4":
                continue

            # ---------- height ကို ထုတ်ယူ/ခန့်မှန်း ----------
            height = f.get("height")

            # 1) resolution field ထဲကနေ (eg: "1280x720")
            if not height:
                res = f.get("resolution")
                if res and "x" in res:
                    try:
                        height = int(res.split("x")[1])
                    except Exception:
                        height = None

            # 2) format_note ထဲက “hd”, “sd”, “720”, “1080” စတာကနေ ခန့်မှန်း
            if not height:
                note = (f.get("format_note") or "").lower()
                if "1080" in note or "full hd" in note:
                    height = 1080
                elif "720" in note or note == "hd":
                    height = 720
                elif "480" in note or note == "sd":
                    height = 480

            # label တည်ဆောက်
            label_parts = []
            if height:
                label_parts.append(f"{height}p")

            fps = f.get("fps")
            if fps:
                label_parts.append(f"{fps}fps")

            if label_parts:
                label = " ".join(label_parts)
            else:
                # fallback: "HD", "SD" သဘောမျိုး
                label = (f.get("format_note") or f.get("format_id") or "").upper() or "MP4"

            fmts.append(
                {
                    "format_id": f.get("format_id"),
                    "label": label,
                    "height": height or 0,  # sorting အတွက်သာ သုံးမယ်
                }
            )

        # height အမြင့်ဆုံးက အပေါ်ဆုံးပေါ်အောင် sort
        fmts.sort(key=lambda x: x["height"], reverse=True)

        # frontend ကို height field မလိုရင်တော့ ပြန်မပို့ချင်လို့ pop လုပ်ထား
        for f in fmts:
            f.pop("height", None)

        return {"formats": fmts}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 2) Download with yt-dlp
def download_with_ytdlp(url: str, format_id: str) -> str:
    """
    format_id = frontend ကရွေးလိုက်တဲ့ resolution (mp4 format_id)
    """
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
            "filename": filename,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 4) Serve file
@app.get("/file/{filename}")
def get_file(filename: str):
    path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    # mp3 / mp4 မျိုးအတွက် mime-type ခွဲပေးထားရင်ကောင်းမယ်
    lower = filename.lower()
    if lower.endswith(".mp3") or lower.endswith(".m4a"):
        media_type = "audio/mpeg"
    else:
        media_type = "video/mp4"

    return FileResponse(path, media_type=media_type, filename=filename)

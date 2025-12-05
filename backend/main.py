from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import yt_dlp
import os

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

app.mount("/files", StaticFiles(directory=DOWNLOAD_DIR), name="files")


@app.get("/")
def root():
    return {"status": "ok", "message": "ThuYaAungZaw Video Downloader API"}


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
            acodec = (f.get("acodec") or "").lower()
            ext = (f.get("ext") or "").lower()

            # audio-only / video-only တွေစလုံး ဖျက်ထုတ်
            if vcodec == "none":
                continue
            if acodec == "none":
                continue

            # mp4 မဟုတ်ရင် (webm စတာ) မပို့တော့
            if ext != "mp4":
                continue

            # YouTube ဖြစ်ရင် H.264 (avc1 / h264) ကိုပဲ ခွင့်ပြု
            if "youtube" in extractor:
                if not (vcodec.startswith("avc1") or "h264" in vcodec):
                    continue

            height = f.get("height")
            fps = f.get("fps")

            # label
            label_parts = []
            if height:
                label_parts.append(f"{height}p")
            if fps:
                label_parts.append(f"{fps}fps")

            if label_parts:
                label = " ".join(label_parts)
            else:
                # fallback label (SD / HD ...)
                label = (f.get("format_note") or f.get("format_id") or "MP4").upper()

            fmts.append(
                {
                    "format_id": f.get("format_id"),
                    "label": label,
                    "height": height or 0,
                }
            )

        # resolution အမြင့်ဆုံးနဲ့ အပေါ်ဆုံးတန်းပေါ်အောင် sort
        fmts.sort(key=lambda x: x["height"], reverse=True)
        for f in fmts:
            f.pop("height", None)

        return {"formats": fmts}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def download_with_ytdlp(url: str, format_id: str) -> str:
    """
    format_id = frontend ထဲကရွေးထားတဲ့ mp4 format id
    (audio ပါပြီးသား progressive mp4 ကိုပဲ /formats မှာ filter လုပ်ထားပြီ)
    """
    ydl_opts = {
      "format": format_id,
      "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
      "quiet": True,
      "noplaylist": True,
      "nocheckcertificate": True,
      "merge_output_format": "mp4",  # final output mp4 သတ်မှတ်
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return os.path.basename(filename)


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


@app.get("/file/{filename}")
def get_file(filename: str):
    path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    lower = filename.lower()
    if lower.endswith(".mp3") or lower.endswith(".m4a"):
        media_type = "audio/mpeg"
    else:
        media_type = "video/mp4"

    return FileResponse(path, media_type=media_type, filename=filename)
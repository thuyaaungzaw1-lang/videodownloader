import os
import uuid

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

app.mount("/files", StaticFiles(directory=DOWNLOAD_DIR), name="files")

# frontend ကြိမ်ကြိမ်သုံးထားတဲ့ audio-only format id
SPECIAL_AUDIO_FORMAT = "bestaudio[ext=m4a]/bestaudio"


@app.get("/")
def root():
    return {"status": "ok", "message": "ThuYaAungZaw Downloader (no-ffmpeg, H264 only)"}


# ------------------------------------------------------------
# FORMATS
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

        fmts = []

        for f in info.get("formats", []):
            vcodec = (f.get("vcodec") or "").lower()
            acodec = (f.get("acodec") or "").lower()
            ext = (f.get("ext") or "").lower()

            # audio-only / video-only မလိုပါ -> progressive mp4 ပဲ လိုတယ်
            if vcodec == "none":
                continue
            if acodec == "none":
                continue

            # mp4 မဟုတ်ရင် မထည့်
            if ext != "mp4":
                continue

            # H.264 / avc1 ဖြစ်ရမယ် (Safari / iPhone playable)
            if not (vcodec.startswith("avc1") or "h264" in vcodec):
                continue

            height = f.get("height") or 0
            fps = f.get("fps")

            label_parts = []
            if height:
                label_parts.append(f"{height}p")
            if fps:
                label_parts.append(f"{fps}fps")
            label = " ".join(label_parts) if label_parts else (
                f.get("format_note") or f.get("format_id") or "MP4"
            )

            fmts.append(
                {
                    "format_id": f.get("format_id"),
                    "label": label,
                    "height": height,
                }
            )

        # resolution မြင့်順နဲ့ ပြမယ်
        fmts.sort(key=lambda x: x["height"], reverse=True)
        for f in fmts:
            f.pop("height", None)

        return {"formats": fmts}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------
# INTERNAL DOWNLOAD HELPERS
# ------------------------------------------------------------
def download_audio_only(url: str) -> str:
    """
    Audio only (MP3/M4A). Safari အတွက် m4aပဲ အလိုအလျောက် ရနိုင်အောင် format expr သတ်မှတ်ထားတယ်။
    """
    uid = str(uuid.uuid4())
    out_tmpl = os.path.join(DOWNLOAD_DIR, uid + ".%(ext)s")

    ydl_opts = {
        "format": SPECIAL_AUDIO_FORMAT,  # bestaudio[ext=m4a]/bestaudio
        "outtmpl": out_tmpl,
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

    return os.path.basename(filename)


def download_video_progressive(url: str, format_id: str) -> str:
    """
    Video + audio ပေါင်းပြီးသား progressive mp4 (H.264) ကိုပဲ
    formats() မှာ filter ထုတ်ထားပြီးသား, ဒီမှာတော့ တန်း download လုပ်ရုံပါ။
    """
    out_tmpl = os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s")

    ydl_opts = {
        "format": format_id,
        "outtmpl": out_tmpl,
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

    return os.path.basename(filename)


# ------------------------------------------------------------
# DOWNLOAD ENDPOINT
# ------------------------------------------------------------
@app.get("/download")
def download(url: str, format_id: str):
    if not url or not format_id:
        raise HTTPException(status_code=400, detail="Missing url or format_id")

    try:
        # frontend က MP3 / Audio only ကို ဒီ format_id နဲ့ပဲ လှမ်းပို့လာမယ်
        if format_id == SPECIAL_AUDIO_FORMAT:
            filename = download_audio_only(url)
        else:
            filename = download_video_progressive(url, format_id)

        return {
            "download_url": f"/file/{filename}",
            "filename": filename,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------
# SERVE FILE
# ------------------------------------------------------------
@app.get("/file/{filename}")
def get_file(filename: str):
    path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    lower = filename.lower()
    if lower.endswith(".mp3") or lower.endswith(".m4a") or lower.endswith(".aac"):
        media_type = "audio/mpeg"
    else:
        media_type = "video/mp4"

    return FileResponse(path, media_type=media_type, filename=filename)

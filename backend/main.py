import os
import uuid
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import yt_dlp

app = FastAPI()

# ------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------
# VPS ပေါ်မှာ Path မမှားအောင် လက်ရှိဖိုင်ရှိတဲ့နေရာကို အခြေခံပြီး ယူမယ်
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")

# Download folder မရှိရင် ဆောက်မယ်
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Frontend က MP3 only လို့ပို့ရင် Backend ကသိဖို့
SPECIAL_AUDIO_FORMAT = "bestaudio[ext=m4a]/bestaudio"

# ------------------------------------------------------------
# CORS (Domain အားလုံးကို လက်ခံပေးထားပါတယ်)
# ------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Video Downloader is Running on VPS",
    }

# ------------------------------------------------------------
# FORMATS API
# ------------------------------------------------------------
@app.get("/formats")
def get_formats(url: str):
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    # UI အတွက် Format များ
    formats = [
        {"format_id": "q720", "label": "720p"},
        {"format_id": "q480", "label": "480p"},
        {"format_id": "q360", "label": "360p"},
    ]
    return {"formats": formats}


# ------------------------------------------------------------
# INTERNAL HELPERS (Download Logic)
# ------------------------------------------------------------
def download_audio_only(url: str) -> str:
    """Audio only – MP3 / M4A"""
    uid = str(uuid.uuid4())
    # Absolute path ကိုသုံးထားပါတယ်
    out_tmpl = os.path.join(DOWNLOAD_DIR, uid + ".%(ext)s")

    ydl_opts = {
        "format": SPECIAL_AUDIO_FORMAT,
        "outtmpl": out_tmpl,
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)

    return os.path.basename(path)


def _choose_best_format(info, quality_tag: str):
    extractor = (info.get("extractor") or "").lower()
    formats = info.get("formats", []) or []

    # --- 1) TIKTOK ---
    if "tiktok" in extractor:
        clean = [
            f for f in formats
            if (f.get("ext") == "mp4") and not ("watermark" in (f.get("format_note") or "").lower())
        ]
        if not clean:
            clean = [f for f in formats if f.get("ext") == "mp4"]

        if quality_tag == "q720":
            preferred_max = 1080 
        elif quality_tag == "q480":
            preferred_max = 480
        else:
            preferred_max = 360

        ok = [f for f in clean if (f.get("height") or 0) <= preferred_max]
        if ok:
            return sorted(ok, key=lambda x: x.get("height") or 0, reverse=True)[0]
        
        if clean:
            if quality_tag == "q720":
                return sorted(clean, key=lambda x: x.get("height") or 0, reverse=True)[0]
            else:
                return sorted(clean, key=lambda x: x.get("height") or 0)[0]
        return None

    # --- 2) YOUTUBE ---
    def find_by_id(fid):
        return next((f for f in formats if f.get("format_id") == fid), None)

    if "youtube" in extractor:
        if quality_tag == "q720":
            for fid in ["37", "22", "18"]:
                f = find_by_id(fid)
                if f: return f
        elif quality_tag == "q480":
            for fid in ["22", "18"]:
                f = find_by_id(fid)
                if f: return f
        else:
            for fid in ["18", "22", "37"]:
                f = find_by_id(fid)
                if f: return f

    # --- 3) GENERIC SITES ---
    if quality_tag == "q720": preferred_max = 720
    elif quality_tag == "q480": preferred_max = 480
    else: preferred_max = 360

    prog = [
        f for f in formats
        if (f.get("vcodec") or "").lower() != "none"
        and (f.get("acodec") or "").lower() != "none"
        and (f.get("ext") or "").lower() == "mp4"
    ]

    h264 = [
        f for f in prog
        if (f.get("vcodec") or "").lower().startswith("avc1")
        or "h264" in (f.get("vcodec") or "").lower()
    ]

    def best_under(cands, max_h):
        ok = [f for f in cands if (f.get("height") or 0) <= max_h]
        if ok:
            return sorted(ok, key=lambda x: x.get("height") or 0, reverse=True)[0]
        if cands:
            return sorted(cands, key=lambda x: x.get("height") or 0, reverse=True)[0]
        return None

    f = best_under(h264, preferred_max)
    if f: return f
    return best_under(prog, preferred_max)


def download_video_stable(url: str, quality_tag: str) -> str:
    base_opts = {
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True,
    }

    with yt_dlp.YoutubeDL({**base_opts, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)

    chosen = _choose_best_format(info, quality_tag)
    if not chosen:
        raise RuntimeError("No suitable progressive MP4 format found")

    fmt_id = chosen.get("format_id")
    # Absolute path သုံးထားသည်
    out_tmpl = os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s")

    ydl_opts = {
        **base_opts,
        "format": fmt_id,
        "outtmpl": out_tmpl,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info2 = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info2)

    return os.path.basename(path)


# ------------------------------------------------------------
# DOWNLOAD API
# ------------------------------------------------------------
@app.get("/download")
def download(url: str, format_id: str):
    if not url or not format_id:
        raise HTTPException(status_code=400, detail="Missing url or format_id")

    try:
        if format_id == SPECIAL_AUDIO_FORMAT:
            filename = download_audio_only(url)
        else:
            filename = download_video_stable(url, format_id)

        return {
            "download_url": f"/file/{filename}",
            "filename": filename,
        }
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Download error: {str(e)}")


# ------------------------------------------------------------
# SERVE FILE API
# ------------------------------------------------------------
@app.get("/file/{filename}")
def get_file(filename: str):
    path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    lower = filename.lower()
    media_type = "audio/mpeg" if lower.endswith((".mp3", ".m4a", ".aac")) else "video/mp4"

    return FileResponse(path, media_type=media_type, filename=filename)

# python main.py နဲ့ Run ရင် အလုပ်လုပ်အောင် ထည့်ပေးထားသည်
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

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

# frontend မှာသုံးထားတဲ့ audio-only format id နဲ့ကိုက်စေဖို့
SPECIAL_AUDIO_FORMAT = "bestaudio[ext=m4a]/bestaudio"


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "ThuYaAungZaw Downloader (Dynamic resolutions H.264 progressive MP4)",
    }


# ------------------------------------------------------------
# FORMATS – URL ပေါ်မူတည်ပြီး dynamic resolutions
# ------------------------------------------------------------
@app.get("/formats")
def get_formats(url: str):
    """
    URL ကိုစစ်ပြီး
    - YouTube: Safari-playable H.264 progressive MP4 (<=1080p)
    - TikTok: no-watermark MP4 (<=1080p)
    - Facebook: progressive MP4 (<=720p)
    - Others: progressive MP4 (<=1080p)
    ဆိုပြီး available resolutions တွေကို low -> high အစီအစဉ်နဲ့ပို့ပေးမယ်
    (frontend က MP3 option ကိုထပ်ထည့်သုံးလိမ့်မယ်)
    """
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    base_opts = {
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "skip_download": True,
    }

    try:
        with yt_dlp.YoutubeDL(base_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch formats: {e}")

    extractor = (info.get("extractor") or "").lower()
    all_formats = info.get("formats", []) or []

    def is_progressive_mp4(f):
        v = (f.get("vcodec") or "").lower()
        a = (f.get("acodec") or "").lower()
        ext = (f.get("ext") or "").lower()
        return v != "none" and a != "none" and ext == "mp4"

    def is_progressive_h264_mp4(f):
        v = (f.get("vcodec") or "").lower()
        a = (f.get("acodec") or "").lower()
        ext = (f.get("ext") or "").lower()
        return (
            v != "none"
            and a != "none"
            and ext == "mp4"
            and ("avc1" in v or "h264" in v or v.startswith("h264"))
        )

    # --------------------------------------------------------
    # TikTok – no-watermark mp4 only (<=1080p)
    # --------------------------------------------------------
    if "tiktok" in extractor:
        candidates = [
            f
            for f in all_formats
            if (f.get("ext") or "").lower() == "mp4"
            and "watermark" not in (f.get("format_note") or "").lower()
        ]
        if not candidates:
            candidates = [
                f for f in all_formats if (f.get("ext") or "").lower() == "mp4"
            ]
        max_height = 1080

    # --------------------------------------------------------
    # YouTube – Safari playable H.264 progressive MP4 (<=1080p)
    # --------------------------------------------------------
    elif "youtube" in extractor:
        candidates = [f for f in all_formats if is_progressive_h264_mp4(f)]
        max_height = 1080

    # --------------------------------------------------------
    # Facebook – progressive MP4 (<=720p)
    # --------------------------------------------------------
    elif "facebook" in extractor:
        candidates = [f for f in all_formats if is_progressive_mp4(f)]
        max_height = 720

    # --------------------------------------------------------
    # Others – generic progressive MP4 (<=1080p)
    # --------------------------------------------------------
    else:
        candidates = [f for f in all_formats if is_progressive_mp4(f)]
        max_height = 1080

    # height တစ်ခုချင်းစီအတွက် best bitrate format ရွေးမယ်
    by_height = {}
    for f in candidates:
        h = f.get("height") or 0
        if not h or h > max_height:
            continue
        prev = by_height.get(h)
        if (not prev) or ((f.get("tbr") or 0) > (prev.get("tbr") or 0)):
            by_height[h] = f

    # ဘာမှမတွေ့ရင်တော့ အရင် static behaviour ကို fallback
    if not by_height:
        formats = [
            {"format_id": "q720", "label": "720p"},
            {"format_id": "q480", "label": "480p"},
            {"format_id": "q360", "label": "360p"},
        ]
        return {"formats": formats}

    # height အနည်းဆုံး → အမြင့်ဆုံး
    out = []
    for h in sorted(by_height.keys()):
        out.append(
            {
                # q{height} ဆိုတဲ့ virtual id ပို့မယ် (ဥပမာ q720, q1080 ...)
                "format_id": f"q{h}",
                "label": f"{h}p",
            }
        )

    return {"formats": out}


# ------------------------------------------------------------
# INTERNAL HELPERS
# ------------------------------------------------------------
def download_audio_only(url: str) -> str:
    """Audio only – MP3 / M4A (Frontend က MP3 / Audio only)."""
    uid = str(uuid.uuid4())
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


def _choose_by_max_height(info, target_height: int):
    """
    info = yt-dlp extract_info(..., download=False)
    target_height = 1080 / 720 / 480 / 360 / ...

    Site type ပေါ်မူတည်ပြီး progressive MP4 + audio format ကို
    height <= target_height ထဲက အမြင့်ဆုံးအနေနဲ့ရွေးပေးမယ်။
    """
    extractor = (info.get("extractor") or "").lower()
    formats = info.get("formats", []) or []

    def is_progressive_mp4(f):
        v = (f.get("vcodec") or "").lower()
        a = (f.get("acodec") or "").lower()
        ext = (f.get("ext") or "").lower()
        return v != "none" and a != "none" and ext == "mp4"

    def is_progressive_h264_mp4(f):
        v = (f.get("vcodec") or "").lower()
        a = (f.get("acodec") or "").lower()
        ext = (f.get("ext") or "").lower()
        return (
            v != "none"
            and a != "none"
            and ext == "mp4"
            and ("avc1" in v or "h264" in v or v.startswith("h264"))
        )

    # TikTok
    if "tiktok" in extractor:
        clean = [
            f
            for f in formats
            if (f.get("ext") == "mp4")
            and "watermark" not in (f.get("format_note") or "").lower()
        ]
        if not clean:
            clean = [f for f in formats if f.get("ext") == "mp4"]
        candidates = clean
        max_allowed = min(target_height, 1080)

    # YouTube – H.264 progressive only
    elif "youtube" in extractor:
        candidates = [f for f in formats if is_progressive_h264_mp4(f)]
        max_allowed = min(target_height, 1080)

    # Facebook – progressive MP4 only
    elif "facebook" in extractor:
        candidates = [f for f in formats if is_progressive_mp4(f)]
        max_allowed = min(target_height, 720)

    # Others – generic progressive MP4
    else:
        candidates = [f for f in formats if is_progressive_mp4(f)]
        max_allowed = min(target_height, 1080)

    def best_under(cands, max_h):
        ok = [f for f in cands if (f.get("height") or 0) <= max_h]
        if ok:
            return sorted(ok, key=lambda x: x.get("height") or 0, reverse=True)[0]
        if cands:
            # အောက်မရှိရင်တော့ အထက်ကနေလည်း အနည်းဆုံးတစ်ခုယူပေးမယ်
            return sorted(cands, key=lambda x: x.get("height") or 0)[0]
        return None

    chosen = best_under(candidates, max_allowed)
    return chosen


def download_video_stable(url: str, quality_tag: str) -> str:
    """
    URL + quality_tag
    - quality_tag = "q{height}" (q720/q480/q360/q1080/...)
      => target_height ကိုစိတ်ကြိုက်ရွေးပြီး progressive MP4 ကိုယူမယ်
    """
    base_opts = {
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True,
    }

    # quality_tag က q দিয়েစတွေ့ရင် height extract
    if quality_tag.startswith("q"):
        try:
            target_height = int(quality_tag[1:])
        except ValueError:
            raise RuntimeError(f"Invalid quality tag: {quality_tag}")
    else:
        # လက်ရှိ frontend မသုံးသင့်ပေမယ့် backward compatible အနေနဲ့
        # q720/q480/q360 အတွင်းဘာမဟုတ်ရင် 720p သတ်မှတ်ထားမယ်
        target_height = 720

    # info only
    with yt_dlp.YoutubeDL({**base_opts, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)

    chosen = _choose_by_max_height(info, target_height)
    if not chosen:
        raise RuntimeError("No suitable progressive MP4 format found")

    fmt_id = chosen.get("format_id")
    out_tmpl = os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s")

    # actual download
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
# DOWNLOAD ENDPOINT
# ------------------------------------------------------------
@app.get("/download")
def download(url: str, format_id: str):
    if not url or not format_id:
        raise HTTPException(status_code=400, detail="Missing url or format_id")

    try:
        if format_id == SPECIAL_AUDIO_FORMAT:
            filename = download_audio_only(url)
        else:
            # format_id = q{height} (q720/q360/q1080/...)
            filename = download_video_stable(url, format_id)

        return {
            "download_url": f"/file/{filename}",
            "filename": filename,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download error: {e}")


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

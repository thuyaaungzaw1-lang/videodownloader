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

# frontendမှာသုံးထားတဲ့ audio-only format id နဲ့ အတူတူပဲထားရမယ်
SPECIAL_AUDIO_FORMAT = "bestaudio[ext=m4a]/bestaudio"


@app.get("/")
def root():
    return {"status": "ok", "message": "ThuYaAungZaw Downloader (stable up to 720p)"}


# ------------------------------------------------------------
# FORMATS – frontend ကိုပြအတွက်ပဲ
# ------------------------------------------------------------
@app.get("/formats")
def get_formats(url: str):
    """
    URL ကို check လိုက်မှပေမယ့်, အခု version မှာ
    frontend ကို အောက်က generic resolution 3 မျိုးပဲ ပြန်ပေးမယ်:
    720p, 480p, 360p
    Real quality ကိုတော့ /download မှာ expression နဲ့ handle လုပ်မယ်။
    """
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    formats = [
        {"format_id": "q720", "label": "720p"},
        {"format_id": "q480", "label": "480p"},
        {"format_id": "q360", "label": "360p"},
    ]
    return {"formats": formats}


# ------------------------------------------------------------
# INTERNAL DOWNLOAD HELPERS
# ------------------------------------------------------------
def download_audio_only(url: str) -> str:
    """
    Audio only – bestaudio (m4a/whatever).
    Frontend က "MP3 / Audio only" လို့ ပြမယ်။
    """
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


def download_video_stable(url: str, format_id: str) -> str:
    """
    Stable mp4 video (audio+video together, progressive mp4).
    q720 / q480 / q360 အလိုက် height limit ချပြီး download မယ်။
    """

    # pseudo id အလိုက် target height
    if format_id == "q720":
        max_h = 720
    elif format_id == "q480":
        max_h = 480
    else:
        max_h = 360

    # Progressive mp4 only: audio + video ပါရမယ်
    # height<=max_h ကြိုးစားမယ်, မရရင် fallback အနေနဲ့ best progressive mp4
    fmt_expr = (
        f"best[ext=mp4][vcodec!=none][acodec!=none][height<={max_h}]"
        f"/best[ext=mp4][vcodec!=none][acodec!=none]"
    )

    out_tmpl = os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s")

    ydl_opts = {
        "format": fmt_expr,
        "outtmpl": out_tmpl,
        "quiet": True,
        "noplaylist": True,
        "nocheckcertificate": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)

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
            # MP3 / Audio only
            filename = download_audio_only(url)
        else:
            # q720 / q480 / q360 → video
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

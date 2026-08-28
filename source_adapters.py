"""Source adapters for public/authorized media only.

This module deliberately does not bypass login, DRM, bot checks, CAPTCHAs, or
other access controls. It gives the app one interface for direct media URLs and
yt-dlp-supported public pages, with structured errors and a safe upload fallback.
"""
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
import re
import shutil
import subprocess
import requests

MAX_BYTES = 1024 * 1024 * 1024

@dataclass
class SourceResult:
    path: Path
    kind: str
    host: str

class SourceAccessError(RuntimeError):
    pass

def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()

def is_http_url(url: str) -> bool:
    return bool(re.match(r"^https?://", (url or "").strip(), re.I))

def ffmpeg_path():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

def _direct_download(url: str, out: Path) -> bool:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        "Accept": "video/*,*/*;q=0.8",
    }
    try:
        with requests.get(url, stream=True, timeout=90, allow_redirects=True, headers=headers) as r:
            r.raise_for_status()
            ctype = (r.headers.get("content-type") or "").lower()
            if "text/html" in ctype or "application/json" in ctype:
                return False
            total = 0
            with out.open("wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise SourceAccessError("Video က 1GB ကျော်နေပါတယ်။")
                    f.write(chunk)
        return out.exists() and out.stat().st_size > 0
    except SourceAccessError:
        raise
    except requests.RequestException:
        return False

def fetch_public_or_authorized(url: str, out: Path) -> SourceResult:
    """Try direct media first, then yt-dlp public extractors.

    If a service returns 401/403, CAPTCHA, bot verification, login-required or
    DRM errors, the exception is surfaced rather than attempting to circumvent it.
    """
    url = (url or "").strip()
    if not is_http_url(url):
        raise SourceAccessError("HTTP/HTTPS link ထည့်ပါ။")
    host = host_of(url)
    if _direct_download(url, out):
        return SourceResult(out, "direct", host)

    try:
        import yt_dlp
        ff = ffmpeg_path()
        if not ff:
            raise SourceAccessError("FFmpeg မတွေ့ပါ။")
        stem = out.with_suffix("")
        opts = {
            "outtmpl": str(stem) + ".%(ext)s",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "retries": 5,
            "fragment_retries": 5,
            "file_access_retries": 3,
            "socket_timeout": 30,
            "ffmpeg_location": ff,
            "merge_output_format": "mp4",
            "format": "best[ext=mp4][vcodec!=none][acodec!=none]/best[vcodec!=none][acodec!=none]/b",
            "http_headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"},
        }
        if "youtube." in host or host.endswith("youtu.be"):
            opts["extractor_args"] = {"youtube": {"player_client": ["web_safari", "web"]}}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            prepared = Path(ydl.prepare_filename(info))
        candidates = [prepared, prepared.with_suffix(".mp4"), prepared.with_suffix(".mkv"), prepared.with_suffix(".webm"), stem.with_suffix(".mp4")]
        found = next((p for p in candidates if p.exists() and p.stat().st_size > 0), None)
        if not found:
            raise SourceAccessError("Video file မရပါ။")
        if found != out:
            if out.exists():
                out.unlink()
            found.replace(out)
        if out.stat().st_size > MAX_BYTES:
            out.unlink(missing_ok=True)
            raise SourceAccessError("Video က 1GB ကျော်နေပါတယ်။")
        return SourceResult(out, "extractor", host)
    except SourceAccessError:
        raise
    except Exception as exc:
        msg = str(exc)
        lower = msg.lower()
        if any(x in lower for x in ("403", "forbidden", "sign in", "not a bot", "captcha", "drm", "login required", "authentication")):
            raise SourceAccessError(f"Source access restriction: {msg}") from exc
        raise SourceAccessError(f"Supported public/authorized source မဟုတ်ပါ: {msg}") from exc

import asyncio
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests
import streamlit as st

st.set_page_config(page_title="Movie Recap AI", page_icon="🎬", layout="wide")
MAX_BYTES = 1024 * 1024 * 1024
TARGET_RECAP_CHARS = 7000
VOICES = {"🇲🇲 Myanmar Male": "my-MM-ThihaNeural", "🇲🇲 Myanmar Female": "my-MM-NilarNeural"}


def ffmpeg_exe():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        raise RuntimeError("FFmpeg မတွေ့ပါ။") from e


def ffmpeg(args, check=True):
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", *map(str, args)], capture_output=True, text=True)
    if check and p.returncode:
        raise RuntimeError((p.stderr or p.stdout or "FFmpeg failed").strip()[-4000:])
    return p


def duration(path):
    p = ffmpeg(["-i", str(path)], False)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", p.stderr or "")
    if not m:
        raise RuntimeError("Media duration မဖတ်နိုင်ပါ။")
    return int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))


def youtube_id(url):
    m = re.search(r"(?:v=|youtu\.be/|youtube\.com/shorts/|youtube\.com/embed/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else None


def youtube_transcript(url):
    vid = youtube_id(url)
    if not vid:
        return None
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        try:
            fetched = api.fetch(vid, languages=["my", "en", "zh-Hans", "zh-Hant", "ja", "ko"])
        except Exception:
            fetched = api.fetch(vid)
        texts = []
        for item in fetched:
            text = getattr(item, "text", None)
            if text is None and isinstance(item, dict):
                text = item.get("text")
            if text:
                texts.append(str(text).strip())
        return " ".join(x for x in texts if x)
    except Exception:
        return None


def _move_result(stem, out, prepared):
    candidates = [out, prepared, prepared.with_suffix(".mp4"), prepared.with_suffix(".mkv"), prepared.with_suffix(".webm"), stem.with_suffix(".mp4"), stem.with_suffix(".mkv"), stem.with_suffix(".webm")]
    found = next((p for p in candidates if p.exists() and p.stat().st_size > 0), None)
    if not found:
        return False
    if found != out:
        if out.exists(): out.unlink()
        found.replace(out)
    return True


def download_video(url, out):
    """Download only media that the source makes available to the client."""
    import yt_dlp
    url = (url or "").strip()
    if not re.match(r"^https?://", url, re.I):
        raise RuntimeError("HTTP/HTTPS video link ထည့်ပါ။")
    ff = ffmpeg_exe()
    stem = out.with_suffix("")
    host = (urlparse(url).hostname or "").lower()
    errors = []
    formats = [
        "best[ext=mp4][vcodec!=none][acodec!=none]",
        "best[vcodec!=none][acodec!=none]",
        "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
    ]
    common = {
        "outtmpl": str(stem) + ".%(ext)s",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 5,
        "fragment_retries": 5,
        "file_access_retries": 3,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 1,
        "ffmpeg_location": ff,
        "merge_output_format": "mp4",
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
    }
    if "youtube." in host or host.endswith("youtu.be"):
        common["extractor_args"] = {"youtube": {"player_client": ["web_safari", "web"]}}
    for fmt in formats:
        try:
            opts = dict(common)
            opts["format"] = fmt
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                prepared = Path(ydl.prepare_filename(info))
            if _move_result(stem, out, prepared):
                return
        except Exception as e:
            errors.append(str(e))
    try:
        headers = {
            "User-Agent": common["http_headers"]["User-Agent"],
            "Accept": "video/*,*/*;q=0.8",
        }
        r = requests.get(url, stream=True, timeout=90, allow_redirects=True, headers=headers)
        r.raise_for_status()
        ctype = (r.headers.get("content-type") or "").lower()
        if "text/html" in ctype or "application/json" in ctype:
            raise RuntimeError("ဒီ link က webpage ဖြစ်ပြီး direct video file မဟုတ်ပါ။")
        total = 0
        with out.open("wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_BYTES:
                    raise RuntimeError("Video က 1GB ကျော်နေပါတယ်။")
                f.write(chunk)
        if out.stat().st_size == 0:
            raise RuntimeError("Empty media response")
    except Exception as e:
        last = errors[-1] if errors else str(e)
        raise RuntimeError(f"Video ကို ရယူမရပါ။ Source က media access ခွင့်ပြုရမယ်။\n{last}") from e
    if out.stat().st_size > MAX_BYTES:
        out.unlink(missing_ok=True)
        raise RuntimeError("Video က 1GB ကျော်နေပါတယ်။")


def split_text(text, limit=220):
    parts = re.split(r"(?<=[.!?။])\s+|(?<=၊)\s+", (text or "").strip())
    result = []
    for part in parts:
        part = part.strip()
        while len(part) > limit:
            cut = part.rfind(" ", 0, limit + 1)
            if cut < limit // 2:
                cut = limit
            result.append(part[:cut].strip())
            part = part[cut:].strip()
        if part:
            result.append(part)
    return result


def translate_mm(text):
    if not text.strip():
        return ""
    mm = sum("\u1000" <= c <= "\u109f" for c in text)
    letters = sum(c.isalpha() for c in text)
    if letters and mm / letters > .35:
        return text
    from deep_translator import GoogleTranslator
    tr = GoogleTranslator(source="auto", target="my")
    chunks, cur = [], ""
    for word in text.split():
        if cur and len(cur) + len(word) + 1 > 2800:
            chunks.append(cur)
            cur = word
        else:
            cur += (" " if cur else "") + word
    if cur:
        chunks.append(cur)
    return " ".join(tr.translate(x) for x in chunks)


def recap_text(text, target_chars=TARGET_RECAP_CHARS):
    """Keep the full story arc while fitting the narration to about ten minutes."""
    parts = split_text(text, 220)
    if not parts:
        return ""
    full = " ".join(parts)
    if len(full) <= target_chars:
        return full

    # Preserve beginning, middle and ending instead of taking only the first N sentences.
    selected = []
    used = 0
    n = len(parts)
    # Walk through the whole movie transcript with a roughly uniform stride.
    stride = max(1, n / max(1, target_chars / 70))
    pos = 0.0
    seen = set()
    while int(pos) < n and used < target_chars:
        idx = min(n - 1, int(pos))
        if idx not in seen:
            piece = parts[idx]
            remaining = target_chars - used
            if len(piece) <= remaining:
                selected.append(piece)
                used += len(piece) + 1
            elif remaining > 80:
                selected.append(piece[:remaining].rsplit(" ", 1)[0].strip())
                break
            seen.add(idx)
        pos += stride

    # Guarantee the climax/ending is represented when the sampled stride misses it.
    tail = parts[-1]
    if tail and tail not in selected:
        room = target_chars - sum(len(x) + 1 for x in selected)
        if room > 100:
            selected.append(tail if len(tail) <= room else tail[:room].rsplit(" ", 1)[0].strip())
    return " ".join(selected)


def transcribe(path):
    from faster_whisper import WhisperModel
    model = WhisperModel("tiny", device="cpu", compute_type="int8", cpu_threads=2, num_workers=1)
    segs, _ = model.transcribe(str(path), beam_size=1, vad_filter=True, condition_on_previous_text=False)
    return " ".join(s.text.strip() for s in segs if s.text.strip())


def make_tts(text, voice, out):
    import edge_tts
    async def go():
        await edge_tts.Communicate(text, voice).save(str(out))
    asyncio.run(go())


def make_srt(text, seconds, out):
    lines = split_text(text, 150)
    if not lines:
        raise RuntimeError("Subtitle စာသားမရှိပါ။")
    weights = [max(1, len(x.replace(" ", ""))) for x in lines]
    total = sum(weights)
    cur = 0.0
    rows = []
    def ts(v):
        ms = int(round((v % 1) * 1000))
        n = int(v)
        h, rem = divmod(n, 3600)
        m, s = divmod(rem, 60)
        if ms == 1000:
            ms = 0
            s += 1
        return f"{h:02}:{m:02}:{s:02},{ms:03}"
    for i, line in enumerate(lines, 1):
        end = seconds if i == len(lines) else cur + seconds * weights[i - 1] / total
        rows.append(f"{i}\n{ts(cur)} --> {ts(end)}\n{line}\n")
        cur = end
    out.write_text("\n".join(rows), encoding="utf-8-sig")


def sub_filter(path):
    p = str(path).replace("\\", "/").replace("'", "\\'").replace(":", r"\:").replace("[", r"\[").replace("]", r"\]")
    return f"subtitles='{p}':force_style='FontSize=24,Outline=2,Alignment=2,MarginV=40'"


def render(video, voice, sub, out, vertical):
    size = "720:1280" if vertical else "1280:720"
    vf = f"scale={size}:force_original_aspect_ratio=increase,crop={size},{sub_filter(sub)}"
    ffmpeg([
        "-y", "-stream_loop", "-1", "-i", str(video), "-i", str(voice),
        "-t", f"{duration(voice):.3f}", "-map", "0:v:0", "-map", "1:a:0",
        "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "27",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", str(out)
    ])


st.title("🎬 Movie Recap AI")
st.caption("Full movie → approximately 10-minute Myanmar recap → Voice + Subtitle → MP4")
with st.sidebar:
    vertical = st.selectbox("📱 Video Format", ["9:16", "16:9"]) == "9:16"
    voice = st.selectbox("🎙️ Myanmar Voice", list(VOICES))
url = st.text_input("🔗 Movie / Video Link", placeholder="YouTube / TikTok / public video page / direct video URL")
upload = st.file_uploader("🎞️ Video Upload (max 1GB)", type=["mp4", "mkv", "mov", "avi", "webm"])

if st.button("🚀 Generate 10-Minute Myanmar Movie Recap", type="primary", use_container_width=True):
    if not upload and not url.strip():
        st.error("Video upload လုပ်ပါ သို့မဟုတ် link ထည့်ပါ။")
        st.stop()
    try:
        with tempfile.TemporaryDirectory(prefix="movie_recap_") as td:
            w = Path(td)
            video = w / "source.mp4"
            wav = w / "audio.wav"
            speech = w / "voice.mp3"
            sub = w / "mm.srt"
            out = w / "movie_recap_mm.mp4"
            transcript = None
            transcript_source = False

            if upload:
                if upload.size > MAX_BYTES:
                    raise RuntimeError("Video က 1GB ကျော်နေပါတယ်။")
                video.write_bytes(upload.getbuffer())
            else:
                if youtube_id(url.strip()):
                    with st.spinner("📝 YouTube transcript ရှာနေပါတယ်..."):
                        transcript = youtube_transcript(url.strip())
                    if transcript:
                        transcript_source = True
                        st.info("ℹ️ YouTube video download မလိုဘဲ available transcript နဲ့ recap လုပ်နေပါတယ်။")
                if not transcript:
                    with st.spinner("🔗 Video ကို ရယူနေပါတယ်..."):
                        download_video(url.strip(), video)

            if not transcript_source:
                with st.spinner("🎙️ Audio ထုတ်နေပါတယ်..."):
                    ffmpeg(["-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])
                with st.spinner("📝 Speech-to-text လုပ်နေပါတယ်..."):
                    transcript = transcribe(wav)
            if not transcript or not transcript.strip():
                raise RuntimeError("Video/Transcript ထဲက speech မရပါ။")

            with st.spinner("🧠 ဇာတ်လမ်းတစ်ကားလုံးကို 10 မိနစ်စာ recap အဖြစ်ချုံ့နေပါတယ်..."):
                script = recap_text(translate_mm(transcript), TARGET_RECAP_CHARS)
            if not script:
                raise RuntimeError("Recap စာသားမရပါ။")
            st.caption(f"📝 Recap script: {len(script):,} characters (target ≈ {TARGET_RECAP_CHARS:,})")

            with st.spinner("🎙️ Myanmar voice ထုတ်နေပါတယ်..."):
                make_tts(script, VOICES[voice], speech)

            if not video.exists():
                run_seconds = max(1.0, duration(speech))
                ffmpeg(["-y", "-f", "lavfi", "-i", "color=c=black:s=1280x720:r=24", "-t", f"{run_seconds:.3f}", "-an", str(video)])

            make_srt(script, duration(speech), sub)
            with st.spinner("🎬 Final MP4 render လုပ်နေပါတယ်..."):
                render(video, speech, sub, out, vertical)
            if not out.exists() or out.stat().st_size == 0:
                raise RuntimeError("Output MP4 မထွက်ပါ။")
            final_minutes = duration(out) / 60
            st.success(f"✅ Myanmar Movie Recap MP4 ပြီးပါပြီ — {final_minutes:.1f} minutes")
            st.video(str(out))
            st.download_button("⬇️ Download MP4", out.read_bytes(), "movie_recap_10min_mm.mp4", "video/mp4")
    except Exception as e:
        st.error(f"❌ Generate Error: {e}")
        if not upload and url.strip():
            st.warning("💡 ဒီ source က server-side download ကိုပိတ်ထားနိုင်ပါတယ်။ Video file ကို upload လုပ်ပြီး Generate ပြန်နှိပ်ရင် recap pipeline ဆက်လုပ်နိုင်ပါတယ်။")

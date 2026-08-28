import asyncio
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import requests
import streamlit as st


st.set_page_config(page_title="Movie Recap AI", page_icon="🎬", layout="wide")

MAX_MB = 1024
VOICES = {
    "🇲🇲 Myanmar Male": "my-MM-ThihaNeural",
    "🇲🇲 Myanmar Female": "my-MM-NilarNeural",
}


def ffmpeg_exe():
    """Return a usable ffmpeg executable, including Streamlit/cloud installs."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError(
            "FFmpeg မတွေ့ပါ။ requirements.txt ထဲမှာ imageio-ffmpeg ထည့်ထားကြောင်း စစ်ပါ။"
        ) from exc


def run_ffmpeg(args):
    """Run ffmpeg and expose a useful error instead of hiding stderr."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", *map(str, args)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Unknown FFmpeg error").strip()
        raise RuntimeError(f"FFmpeg error:\n{detail[-5000:]}")
    return result


def chunks(text, limit=220):
    text = (text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?။])\s+|(?<=၊)\s+", text)
    result = []
    for part in parts:
        part = part.strip()
        while len(part) > limit:
            cut = part.rfind(" ", 0, limit + 1)
            if cut < max(40, limit // 2):
                cut = limit
            result.append(part[:cut].strip())
            part = part[cut:].strip()
        if part:
            result.append(part)
    return result


def translate_mm(text):
    text = (text or "").strip()
    if not text:
        return text
    letters = sum(ch.isalpha() for ch in text)
    mm = sum(1 for ch in text if "\u1000" <= ch <= "\u109f")
    if letters and mm / max(1, letters) > 0.35:
        return text

    from deep_translator import GoogleTranslator

    translator = GoogleTranslator(source="auto", target="my")
    pieces = []
    current = ""
    for word in text.split():
        if current and len(current) + len(word) + 1 > 3000:
            pieces.append(current)
            current = word
        else:
            current += (" " if current else "") + word
    if current:
        pieces.append(current)
    return " ".join(translator.translate(piece) for piece in pieces)


def recap10(text):
    sentences = chunks(text, 220)
    if not sentences:
        return ""
    target = min(150, len(sentences))
    if len(sentences) <= target:
        return " ".join(sentences)
    if target == 1:
        return sentences[0]
    ids = sorted({round(i * (len(sentences) - 1) / (target - 1)) for i in range(target)})
    return " ".join(sentences[i] for i in ids)


def transcribe(path):
    from faster_whisper import WhisperModel

    model = WhisperModel(
        "tiny",
        device="cpu",
        compute_type="int8",
        cpu_threads=2,
        num_workers=1,
    )
    segments, _ = model.transcribe(
        str(path),
        beam_size=1,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    return " ".join(seg.text.strip() for seg in segments if seg.text.strip())


def tts(text, voice, output):
    import edge_tts

    async def generate():
        await edge_tts.Communicate(text, voice).save(str(output))

    try:
        asyncio.run(generate())
    except RuntimeError as exc:
        if "asyncio.run() cannot be called" not in str(exc):
            raise
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(generate())
        finally:
            loop.close()


def media_duration(path):
    result = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr or "")
    if not match:
        raise RuntimeError("Media duration မဖတ်နိုင်ပါ။")
    return int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])


def make_srt(text, seconds, output):
    lines = chunks(text, 160)
    if not lines:
        raise RuntimeError("Subtitle စာသားမရှိပါ။")
    weights = [max(1, len(line.replace(" ", ""))) for line in lines]
    total = sum(weights)
    current = 0.0
    rows = []

    def timestamp(value):
        millis = int(round((value % 1) * 1000))
        whole = int(value)
        hours, rem = divmod(whole, 3600)
        minutes, secs = divmod(rem, 60)
        if millis == 1000:
            millis = 0
            secs += 1
        return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

    for index, line in enumerate(lines, 1):
        end = seconds if index == len(lines) else current + seconds * weights[index - 1] / total
        rows.append(f"{index}\n{timestamp(current)} --> {timestamp(end)}\n{line}\n")
        current = end
    output.write_text("\n".join(rows), encoding="utf-8-sig")


def escape_subtitle_path(path):
    """Escape a filesystem path for FFmpeg's subtitles filter."""
    value = str(path).replace("\\", "/")
    value = value.replace("'", "\\'")
    value = value.replace(":", r"\:")
    value = value.replace("[", r"\[").replace("]", r"\]")
    return value


def render(video, audio, subtitle, output, vertical):
    duration = media_duration(audio)
    size = "720:1280" if vertical else "1280:720"
    subtitle_path = escape_subtitle_path(subtitle)
    vf = (
        f"scale={size}:force_original_aspect_ratio=increase," 
        f"crop={size},"
        f"subtitles='{subtitle_path}':"
        "force_style='FontSize=24,Outline=2,Alignment=2,MarginV=40'"
    )

    run_ffmpeg([
        "-y",
        "-stream_loop", "-1",
        "-i", video,
        "-i", audio,
        "-t", f"{duration:.3f}",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "27",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        output,
    ])


def download_video(url, output):
    """Download with yt-dlp first, then use a direct HTTP fallback."""
    first_error = None
    try:
        import yt_dlp

        ffmpeg = ffmpeg_exe()
        options = {
            "outtmpl": str(output.with_suffix(".%(ext)s")),
            "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "ffmpeg_location": str(Path(ffmpeg).parent),
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            prepared = Path(ydl.prepare_filename(info))
            candidates = [output, prepared, prepared.with_suffix(".mp4")]
            for candidate in candidates:
                if candidate.exists() and candidate.stat().st_size:
                    if candidate != output:
                        if output.exists():
                            output.unlink()
                        candidate.replace(output)
                    break
            else:
                raise RuntimeError("yt-dlp download ပြီးပေမယ့် output file မတွေ့ပါ။")
    except Exception as exc:
        first_error = exc

    if output.exists() and output.stat().st_size:
        if output.stat().st_size > MAX_MB * 1024 * 1024:
            output.unlink(missing_ok=True)
            raise ValueError("Video က 1GB ကျော်နေပါတယ်။")
        return

    try:
        response = requests.get(
            url,
            stream=True,
            timeout=90,
            headers={"User-Agent": "Mozilla/5.0 MovieRecapAI"},
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" in content_type:
            raise RuntimeError(str(first_error or "URL သည် direct video မဟုတ်ပါ။"))

        size = 0
        with output.open("wb") as handle:
            for block in response.iter_content(1024 * 1024):
                if not block:
                    continue
                size += len(block)
                if size > MAX_MB * 1024 * 1024:
                    raise ValueError("Video က 1GB ကျော်နေပါတယ်။")
                handle.write(block)
    except Exception as second:
        raise RuntimeError(f"Video link ကို ရယူလို့မရပါ: {second}") from second


def youtube_search(query, token="", limit=20):
    key = st.secrets.get("YOUTUBE_API_KEY", "")
    if not key:
        raise RuntimeError("YOUTUBE_API_KEY ကို Streamlit Secrets ထဲထည့်ပါ။")
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "videoLicense": "creativeCommon",
        "maxResults": limit,
        "key": key,
    }
    if token:
        params["pageToken"] = token
    response = requests.get("https://www.googleapis.com/youtube/v3/search", params=params, timeout=20)
    data = response.json()
    if response.status_code != 200:
        raise RuntimeError(data.get("error", {}).get("message", f"YouTube API HTTP {response.status_code}"))
    items = []
    for item in data.get("items", []):
        video_id = item.get("id", {}).get("videoId")
        if video_id:
            snippet = item.get("snippet", {})
            items.append({
                "title": snippet.get("title", ""),
                "channel": snippet.get("channelTitle", ""),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            })
    return items, data.get("nextPageToken", "")


st.title("🎬 Movie Recap AI")
st.caption("🎞️ Upload • 🔗 Link • 🔎 YouTube reusable videos → 🚀 Generate → 🇲🇲 Recap MP4")

with st.sidebar:
    vertical = st.selectbox("📱 Video Format", ["9:16", "16:9"]) == "9:16"
    voice = st.selectbox("🎙️ Myanmar Voice", list(VOICES))
    st.info("🎯 Target: ဇာတ်လမ်းကို ~10 မိနစ်အတွင်း အကျဉ်းချုပ်")

if "yt_results" not in st.session_state:
    st.session_state.yt_results = []
if "yt_token" not in st.session_state:
    st.session_state.yt_token = ""
if "selected_url" not in st.session_state:
    st.session_state.selected_url = ""

st.subheader("🔎 YouTube မှာ ပြန်လည်အသုံးပြုခွင့် သတ်မှတ်ထားတဲ့ Video ရှာရန်")
query = st.text_input("Search", value="Chinese drama Creative Commons", placeholder="ဥပမာ — Chinese short film, Chinese drama")
col_a, col_b = st.columns(2)

with col_a:
    if st.button("🔎 Search YouTube", use_container_width=True):
        try:
            st.session_state.yt_results, st.session_state.yt_token = youtube_search(query.strip() or "Chinese drama")
        except Exception as exc:
            st.error(f"YouTube Search Error: {exc}")

with col_b:
    if st.button("➕ Load More", use_container_width=True) and st.session_state.yt_token:
        try:
            more, token = youtube_search(query.strip() or "Chinese drama", st.session_state.yt_token)
            st.session_state.yt_results.extend(more)
            st.session_state.yt_token = token
        except Exception as exc:
            st.error(f"Load More Error: {exc}")

for index, item in enumerate(st.session_state.yt_results):
    c1, c2 = st.columns([5, 1])
    c1.markdown(f"**{index + 1}. {item['title']}**  \n`{item['channel']}`")
    if c2.button("သုံးမယ်", key=f"yt_{index}"):
        st.session_state.selected_url = item["url"]
        st.rerun()

if st.session_state.selected_url:
    st.success("✅ YouTube link ရွေးပြီးပါပြီ")

url = st.text_input("🔗 Movie Video Link", value=st.session_state.selected_url, placeholder="YouTube / supported video page / direct video URL")
upload = st.file_uploader("🎞️ Movie Video (max 1 GB)", type=["mp4", "mkv", "mov", "avi", "webm"])

if st.button("🚀 Generate Myanmar Movie Recap", type="primary", use_container_width=True):
    if not upload and not url.strip():
        st.error("❌ Video Upload လုပ်ပါ သို့မဟုတ် Video Link ထည့်ပါ။")
        st.stop()

    try:
        with tempfile.TemporaryDirectory(prefix="movie_recap_") as temp_dir:
            work = Path(temp_dir)
            video = work / "movie.mp4"
            audio = work / "audio.wav"
            voice_file = work / "voice.mp3"
            subtitle = work / "mm.srt"
            output = work / "movie_recap_mm.mp4"

            if upload:
                if upload.size > MAX_MB * 1024 * 1024:
                    raise ValueError("Video က 1GB ကျော်နေပါတယ်။")
                with st.spinner("📥 Uploaded movie ကိုဖတ်နေပါတယ်..."):
                    video.write_bytes(upload.getbuffer())
            else:
                with st.spinner("🔗 Video ကို ရယူနေပါတယ်..."):
                    download_video(url.strip(), video)

            with st.spinner("🎧 Movie အသံကို စာသားပြောင်းနေပါတယ်..."):
                run_ffmpeg([
                    "-y", "-i", video, "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", audio,
                ])
                text = transcribe(audio)

            if not text.strip():
                raise RuntimeError("Movie dialogue မတွေ့ပါ။")

            with st.spinner("🌍 မြန်မာလို Recap Script ပြုလုပ်နေပါတယ်..."):
                script = recap10(translate_mm(text))

            if not script.strip():
                raise RuntimeError("Recap script မထွက်လာပါ။")

            with st.spinner("🎙️ မြန်မာအသံဖန်တီးနေပါတယ်..."):
                tts(script, VOICES[voice], voice_file)

            with st.spinner("📝 Subtitle ပြုလုပ်နေပါတယ်..."):
                make_srt(script, media_duration(voice_file), subtitle)

            with st.spinner("🎬 Movie Scene + Myanmar Voice + Subtitle ပေါင်းနေပါတယ်..."):
                render(video, voice_file, subtitle, output, vertical)

            if not output.exists() or output.stat().st_size == 0:
                raise RuntimeError("Output MP4 မထွက်လာပါ။")

            st.success("✅ Myanmar Movie Recap MP4 ပြီးပါပြီ!")
            st.video(str(output))
            st.download_button(
                "⬇️ Download Recap MP4",
                data=output.read_bytes(),
                file_name="movie_recap_mm.mp4",
                mime="video/mp4",
                use_container_width=True,
            )
            with st.expander("📜 Recap Script"):
                st.write(script)

    except Exception as exc:
        st.error(f"❌ Generate Error: {exc}")

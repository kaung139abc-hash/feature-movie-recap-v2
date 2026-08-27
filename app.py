import asyncio
import re
import subprocess
import tempfile
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Movie Recap AI", page_icon="🎬", layout="wide")

MAX_UPLOAD_MB = 1024
MAX_RECAP_MINUTES = 10
FREE_DAILY_LIMIT = 5
PREMIUM_DAILY_LIMIT = 20

VOICE_OPTIONS = {
    "🇲🇲 Myanmar Male": "my-MM-ThihaNeural",
    "🇲🇲 Myanmar Female": "my-MM-NilarNeural",
    "🇺🇸 Young-style Male": "en-US-GuyNeural",
    "🇺🇸 Young-style Female": "en-US-JennyNeural",
    "🇺🇸 Cinematic Male": "en-US-EricNeural",
    "🇺🇸 Cinematic Female": "en-US-AriaNeural",
}


def run_cmd(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-5000:])


def extract_audio(video_path, audio_path):
    run_cmd(["ffmpeg", "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio_path)])


def split_text(text, limit=2200):
    words = text.split()
    chunks, current, size = [], [], 0
    for word in words:
        if current and size + len(word) + 1 > limit:
            chunks.append(" ".join(current)); current, size = [], 0
        current.append(word); size += len(word) + 1
    if current: chunks.append(" ".join(current))
    return chunks


def sentence_chunks(text, max_chars=180):
    pieces = re.split(r"(?<=[.!?။!?])\s+|(?<=၊)\s+", text.strip())
    pieces = [p.strip() for p in pieces if p.strip()]
    out = []
    for piece in pieces:
        if len(piece) <= max_chars:
            out.append(piece); continue
        words = piece.split(); cur = ""
        for word in words:
            if cur and len(cur) + len(word) + 1 > max_chars:
                out.append(cur); cur = ""
            cur += (" " if cur else "") + word
        if cur: out.append(cur)
    return out


@st.cache_resource
def load_whisper():
    from transformers import pipeline
    import torch
    return pipeline("automatic-speech-recognition", model="openai/whisper-small", device=0 if torch.cuda.is_available() else -1, chunk_length_s=30)


@st.cache_resource
def load_recap_model():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch
    model_id = "Qwen/Qwen2.5-1.5B-Instruct"
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=dtype)
    if torch.cuda.is_available(): model = model.to("cuda")
    return tokenizer, model


def generate_recap(transcript, language):
    import torch
    tokenizer, model = load_recap_model()
    notes = []
    parts = split_text(transcript)
    for i, part in enumerate(parts):
        st.write(f"🧠 Story analysis {i + 1}/{len(parts)}...")
        messages = [
            {"role": "system", "content": "You write accurate, engaging movie recaps. Never add facts not supported by the transcript."},
            {"role": "user", "content": f"Analyze this movie transcript. Preserve important plot events, characters, motivations, conflict, twists and ending. Write a concise narration-ready recap in {language}, chronological and natural. Do not invent events.\n\nTranscript:\n{part}"},
        ]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt")
        if torch.cuda.is_available():
            inputs = {k: v.to("cuda") for k, v in inputs.items()}
        output = model.generate(**inputs, max_new_tokens=500, do_sample=False, repetition_penalty=1.08)
        generated = output[0][inputs["input_ids"].shape[1]:]
        notes.append(tokenizer.decode(generated, skip_special_tokens=True).strip())
    return "\n\n".join(notes)


def make_srt(text, duration_seconds, srt_path):
    units = sentence_chunks(text)
    if not units:
        raise ValueError("Recap script မှာ subtitle ပြုလုပ်စရာစာသားမရှိပါ။")
    weights = [max(1, len(u.replace(" ", ""))) for u in units]
    total = sum(weights); current = 0.0; lines = []
    def stamp(seconds):
        ms = int(round((seconds - int(seconds)) * 1000)); whole = int(seconds)
        h, rem = divmod(whole, 3600); m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    for i, unit in enumerate(units, 1):
        end = duration_seconds if i == len(units) else current + duration_seconds * weights[i - 1] / total
        lines.append(f"{i}\n{stamp(current)} --> {stamp(end)}\n{unit}\n")
        current = end
    srt_path.write_text("\n".join(lines), encoding="utf-8")


def tts_to_mp3(text, voice, output):
    import edge_tts
    async def convert():
        await edge_tts.Communicate(text, voice).save(str(output))
    asyncio.run(convert())


def audio_duration(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return float(result.stdout.strip())


def render_video(source_video, narration_audio, srt_path, output_path, aspect):
    duration = audio_duration(narration_audio)
    if duration > MAX_RECAP_MINUTES * 60 + 2:
        raise ValueError("Recap အသံက 10 မိနစ်ကျော်နေပါတယ်။")
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" if aspect == "9:16" else "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
    subtitle_file = str(srt_path).replace("\\", "/").replace(":", "\\:")
    vf += f",subtitles='{subtitle_file}':force_style='FontName=Noto Sans Myanmar,FontSize=28,Outline=2,Shadow=1,Alignment=2,MarginV=55'"
    run_cmd(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(source_video), "-i", str(narration_audio), "-t", f"{duration:.3f}", "-vf", vf, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "160k", "-shortest", str(output_path)])


with st.sidebar:
    st.header("🎛️ Recap Settings")
    language = st.selectbox("Recap Language", ["မြန်မာဘာသာ", "English"])
    voice_name = st.selectbox("🎙️ Voice", list(VOICE_OPTIONS.keys()))
    aspect = st.selectbox("📱 Video Format", ["9:16", "16:9"])
    plan = st.radio("Plan (prototype)", ["Free", "Premium"])
    limit = FREE_DAILY_LIMIT if plan == "Free" else PREMIUM_DAILY_LIMIT
    st.info(f"{plan}: {limit} recaps/day\nMaximum output: {MAX_RECAP_MINUTES} minutes")
    st.caption("Quota/payment is not connected yet.")
    st.caption("⚠️ Process and publish only videos you own or have permission to transform.")

st.title("🎬 Movie Recap AI")
st.caption("Upload a video or provide an authorized direct video URL.")

video = st.file_uploader("🎞️ Movie Video ထည့်ပါ (အများဆုံး 1 GB)", type=["mp4", "mkv", "mov", "avi", "webm"])
url = st.text_input("🔗 Authorized direct video URL", placeholder="https://example.com/video.mp4")

if video and video.size > MAX_UPLOAD_MB * 1024 * 1024:
    st.error("❌ Video file က 1 GB ထက်ကြီးနေပါတယ်။ 1 GB အောက် file သုံးပါ။")
    video = None

if video or url:
    if video:
        st.video(video)
    if st.button("🚀 Generate Full Recap MP4", type="primary", use_container_width=True):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                source = tmp / "movie.mp4"; audio = tmp / "movie.wav"; narration = tmp / "narration.mp3"; srt = tmp / "subtitles.srt"; output = tmp / "movie_recap.mp4"
                if video:
                    source.write_bytes(video.getbuffer())
                else:
                    import requests
                    if not url.lower().startswith(("http://", "https://")):
                        raise ValueError("Valid http/https video URL ထည့်ပါ။")
                    with st.spinner("🔗 Video link ကို fetch လုပ်နေပါတယ်..."):
                        r = requests.get(url, stream=True, timeout=60, headers={"User-Agent": "MovieRecapAI/1.0"}); r.raise_for_status()
                        total = 0
                        with open(source, "wb") as f:
                            for chunk in r.iter_content(1024 * 1024):
                                if chunk:
                                    total += len(chunk)
                                    if total > MAX_UPLOAD_MB * 1024 * 1024:
                                        raise ValueError("Video link က 1 GB ထက်ကျော်နေပါတယ်။")
                                    f.write(chunk)
                with st.spinner("🎧 Audio extracting..."):
                    extract_audio(source, audio)
                with st.spinner("🗣️ Movie dialogue ကို transcript ပြောင်းနေပါတယ်..."):
                    transcript = load_whisper()(str(audio))["text"].strip()
                if not transcript:
                    st.error("❌ Speech/dialogue မတွေ့ပါ။"); st.stop()
                with st.expander("📜 Transcript", expanded=False):
                    st.text_area("Movie transcript", transcript, height=220)
                st.subheader("✍️ AI Recap Script")
                recap = generate_recap(transcript, language)
                st.text_area("Recap", recap, height=320)
                with st.spinner("🎙️ AI narration အသံထုတ်နေပါတယ်..."):
                    tts_to_mp3(recap, VOICE_OPTIONS[voice_name], narration)
                duration = audio_duration(narration)
                if duration > MAX_RECAP_MINUTES * 60:
                    st.error("❌ Narration က 10 မိနစ်ကျော်သွားပါတယ်။"); st.stop()
                make_srt(recap, duration, srt)
                with st.spinner("🎞️ Subtitle + narration + video ကို MP4 render လုပ်နေပါတယ်..."):
                    render_video(source, narration, srt, output, aspect)
                st.success(f"✅ Recap MP4 ပြီးပါပြီ — {duration / 60:.1f} minutes")
                st.video(str(output))
                st.download_button("⬇️ Download MP4", output.read_bytes(), "movie_recap.mp4", "video/mp4")
                st.download_button("⬇️ Download Script", recap, "movie_recap.txt", "text/plain")
                st.download_button("⬇️ Download Subtitle", srt.read_text(encoding="utf-8"), "subtitles.srt", "application/x-subrip")
        except Exception as exc:
            st.error(f"❌ Error: {exc}")
else:
    st.info("Video upload လုပ်ပါ သို့မဟုတ် ခွင့်ပြုထားတဲ့ direct video URL ထည့်ပါ။")

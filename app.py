import asyncio
import re
import subprocess
import tempfile
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Movie Recap AI", page_icon="🎬", layout="wide")

APP_DIR = Path("movie_recap_data")
APP_DIR.mkdir(exist_ok=True)
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
            chunks.append(" ".join(current))
            current, size = [], 0
        current.append(word)
        size += len(word) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def sentence_chunks(text, max_chars=180):
    # Keep punctuation-based units for subtitle timing.
    pieces = re.split(r"(?<=[.!?။!?])\s+|(?<=၊)\s+", text.strip())
    pieces = [p.strip() for p in pieces if p.strip()]
    out = []
    for piece in pieces:
        if len(piece) <= max_chars:
            out.append(piece)
        else:
            words = piece.split()
            cur = ""
            for word in words:
                if cur and len(cur) + len(word) + 1 > max_chars:
                    out.append(cur)
                    cur = ""
                cur += (" " if cur else "") + word
            if cur:
                out.append(cur)
    return out


@st.cache_resource

def load_whisper():
    from transformers import pipeline
    import torch
    return pipeline(
        "automatic-speech-recognition",
        model="openai/whisper-small",
        device=0 if torch.cuda.is_available() else -1,
        chunk_length_s=30,
    )


@st.cache_resource

def load_recap_model():
    # Multilingual instruction model: supports Burmese better than an English-only summarizer.
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch

    model_id = "Qwen/Qwen2.5-1.5B-Instruct"
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=dtype)
    if torch.cuda.is_available():
        model = model.to("cuda")
    return tokenizer, model


def generate_recap(transcript, language):
    tokenizer, model = load_recap_model()
    parts = split_text(transcript)
    notes = []

    for i, part in enumerate(parts):
        st.write(f"🧠 Story analysis {i + 1}/{len(parts)}...")
        prompt = f"""You are a professional movie recap writer.
Analyze the following movie transcript and preserve the important plot events, characters, motivations, conflict, twists and ending. Do not invent events.
Write a concise narration-ready recap in {language}. Use natural spoken language and clear chronological order.
Transcript:
{part}"""
        messages = [
            {"role": "system", "content": "You write accurate, engaging movie recaps. Never add facts not supported by the transcript."},
            {"role": "user", "content": prompt},
        ]
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(text, return_tensors="pt")
        if torch.cuda.is_available():
            inputs = {k: v.to("cuda") for k, v in inputs.items()}
        output = model.generate(**inputs, max_new_tokens=500, do_sample=False, repetition_penalty=1.08)
        generated = output[0][inputs["input_ids"].shape[1]:]
        notes.append(tokenizer.decode(generated, skip_special_tokens=True).strip())

    combined = "\n\n".join(notes)
    # Final editorial pass to keep the narration within the 10-minute target.
    target_words = 1250
    if len(combined.split()) > target_words:
        messages = [
            {"role": "system", "content": "Edit movie recap scripts without changing facts. Keep the most important plot points, twists and ending."},
            {"role": "user", "content": f"Rewrite this as one coherent narration in {language}, around {target_words} words maximum:\n\n{combined}"},
        ]
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(text, return_tensors="pt")
        if torch.cuda.is_available():
            inputs = {k: v.to("cuda") for k, v in inputs.items()}
        output = model.generate(**inputs, max_new_tokens=1500, do_sample=False, repetition_penalty=1.08)
        generated = output[0][inputs["input_ids"].shape[1]:]
        combined = tokenizer.decode(generated, skip_special_tokens=True).strip()

    return combined


def make_srt(text, duration_seconds, srt_path):
    units = sentence_chunks(text)
    if not units:
        raise ValueError("Recap script မှာ subtitle ပြုလုပ်စရာစာသားမရှိပါ။")

    # Proportional timing gives every spoken unit a stable subtitle window.
    weights = [max(1, len(u.replace(" ", ""))) for u in units]
    total = sum(weights)
    current = 0.0
    lines = []

    def stamp(seconds):
        ms = int(round((seconds - int(seconds)) * 1000))
        whole = int(seconds)
        h, rem = divmod(whole, 3600)
        m, s = divmod(rem, 60)
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
        raise ValueError("Recap အသံက 10 မိနစ်ကျော်နေပါတယ်။ Script ကို ပိုတိုအောင် ပြန်ထုတ်ပါ။")

    if aspect == "9:16":
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    else:
        vf = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"

    # The source movie is used only as a visual background; its original audio is removed.
    # Users should only process videos they own or have permission to transform.
    cmd = [
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(source_video), "-i", str(narration_audio),
        "-t", f"{duration:.3f}", "-vf", f"{vf},subtitles={str(srt_path).replace(':', '\\:')}:force_style='FontName=Noto Sans Myanmar,FontSize=28,Outline=2,Shadow=1,Alignment=2,MarginV=55'",
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "160k", "-shortest", str(output_path)
    ]
    run_cmd(cmd)


with st.sidebar:
    st.header("🎛️ Recap Settings")
    language = st.selectbox("Recap Language", ["မြန်မာဘာသာ", "English"])
    voice_name = st.selectbox("🎙️ Voice", list(VOICE_OPTIONS.keys()))
    aspect = st.selectbox("📱 Video Format", ["9:16", "16:9"])
    plan = st.radio("Plan", ["Free", "Premium"])
    limit = FREE_DAILY_LIMIT if plan == "Free" else PREMIUM_DAILY_LIMIT
    st.info(f"{plan}: {limit} recaps/day\nMaximum output: {MAX_RECAP_MINUTES} minutes")
    st.caption("⚠️ Upload only movies/videos you own or are authorized to transform and publish.")

video = st.file_uploader("🎞️ Movie Video ထည့်ပါ", type=["mp4", "mkv", "mov", "avi", "webm"])

if video:
    st.video(video)
    if st.button("🚀 Generate Full Recap MP4", type="primary", use_container_width=True):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                source = tmp / "movie.mp4"
                audio = tmp / "movie.wav"
                narration = tmp / "narration.mp3"
                srt = tmp / "subtitles.srt"
                output = tmp / "movie_recap.mp4"
                source.write_bytes(video.getbuffer())

                with st.spinner("🎧 Audio extracting..."):
                    extract_audio(source, audio)

                with st.spinner("🗣️ Movie dialogue ကို transcript ပြောင်းနေပါတယ်..."):
                    transcript = load_whisper()(str(audio))["text"].strip()
                if not transcript:
                    st.error("❌ Speech/dialogue မတွေ့ပါ။")
                    st.stop()

                st.subheader("✍️ AI Recap Script")
                recap = generate_recap(transcript, language)
                st.text_area("Recap", recap, height=320)

                voice = VOICE_OPTIONS[voice_name]
                with st.spinner("🎙️ AI narration အသံထုတ်နေပါတယ်..."):
                    tts_to_mp3(recap, voice, narration)
                duration = audio_duration(narration)
                if duration > MAX_RECAP_MINUTES * 60:
                    st.error("❌ Narration က 10 မိနစ်ကျော်သွားပါတယ်။")
                    st.stop()

                make_srt(recap, duration, srt)

                with st.spinner("🎞️ Subtitle + narration + video ကို MP4 အဖြစ် render လုပ်နေပါတယ်..."):
                    render_video(source, narration, srt, output, aspect)

                st.success(f"✅ Recap MP4 ပြီးပါပြီ — {duration / 60:.1f} minutes")
                st.video(str(output))
                st.download_button("⬇️ Download MP4", output.read_bytes(), "movie_recap.mp4", "video/mp4")
                st.download_button("⬇️ Download Script", recap, "movie_recap.txt", "text/plain")
                st.download_button("⬇️ Download Subtitle", srt.read_text(encoding="utf-8"), "subtitles.srt", "application/x-subrip")

        except Exception as exc:
            st.error(f"❌ Error: {exc}")
            st.exception(exc)
else:
    st.info("Movie video တစ်ခု upload လုပ်ပြီး Generate Full Recap MP4 ကိုနှိပ်ပါ။")

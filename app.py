import os
import subprocess
import tempfile
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Movie Recap AI", page_icon="🎬", layout="wide")

st.title("🎬 Movie Recap AI")
st.caption("Video → Transcript → Recap Script")

MAX_RECAP_MINUTES = 10
FREE_DAILY_LIMIT = 5
PREMIUM_DAILY_LIMIT = 20


def extract_audio(video_path: str, audio_path: str) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "wav", audio_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-4000:])


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

def load_summarizer():
    from transformers import pipeline
    import torch
    return pipeline(
        "summarization",
        model="facebook/bart-large-cnn",
        device=0 if torch.cuda.is_available() else -1,
    )


def chunks(text: str, limit: int = 2400):
    words = text.split()
    out, cur, size = [], [], 0
    for word in words:
        if cur and size + len(word) + 1 > limit:
            out.append(" ".join(cur))
            cur, size = [], 0
        cur.append(word)
        size += len(word) + 1
    if cur:
        out.append(" ".join(cur))
    return out


def create_recap(transcript: str) -> str:
    summarizer = load_summarizer()
    summaries = []
    parts = chunks(transcript)
    for i, part in enumerate(parts):
        st.write(f"🧠 Analyzing part {i + 1}/{len(parts)}...")
        result = summarizer(part, max_length=220, min_length=60, do_sample=False)
        summaries.append(result[0]["summary_text"])
    return " ".join(summaries)


with st.sidebar:
    st.header("⚙️ Plan")
    st.info("Free: 5 recaps/day\n\nPremium: 20 recaps/day\n\nRecap: max 10 minutes")
    st.caption("V1: Upload → Transcript → Recap. Voice, synced subtitles and MP4 rendering are next.")

video = st.file_uploader("🎞️ Movie video ထည့်ပါ", type=["mp4", "mkv", "mov", "avi", "webm"])

if video:
    st.video(video)
    if st.button("🚀 Create Recap", type="primary", use_container_width=True):
        try:
            with tempfile.TemporaryDirectory() as tmp:
                video_path = str(Path(tmp) / "movie.mp4")
                audio_path = str(Path(tmp) / "audio.wav")
                Path(video_path).write_bytes(video.getbuffer())

                with st.spinner("🎧 Audio ထုတ်နေပါတယ်..."):
                    extract_audio(video_path, audio_path)

                with st.spinner("🗣️ Dialogue ကို transcript ပြောင်းနေပါတယ်..."):
                    result = load_whisper()(audio_path)
                transcript = result["text"].strip()

                if not transcript:
                    st.error("❌ Speech/dialogue မတွေ့ပါ။")
                    st.stop()

                st.subheader("📜 Transcript")
                st.text_area("Movie transcript", transcript, height=220)

                st.subheader("✍️ AI Recap")
                recap = create_recap(transcript)
                st.text_area("Recap script", recap, height=320)

                st.success("✅ V1 Recap Script အောင်မြင်ပါပြီ!")
                st.download_button("⬇️ Download Script", recap, "movie_recap.txt", "text/plain")
        except FileNotFoundError:
            st.error("❌ FFmpeg မတွေ့ပါ။ Hosting environment မှာ FFmpeg ထည့်ပါ။")
        except Exception as exc:
            st.error(f"❌ Error: {exc}")
else:
    st.info("Movie video တစ်ခု upload လုပ်ပြီး Create Recap ကိုနှိပ်ပါ။")

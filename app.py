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
    "🇺🇸 Young Male": "en-US-GuyNeural",
    "🇺🇸 Young Female": "en-US-JennyNeural",
    "🇺🇸 Cinematic Male": "en-US-EricNeural",
    "🇺🇸 Cinematic Female": "en-US-AriaNeural",
}

def run_cmd(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr[-4000:])

def extract_audio(video, audio):
    run_cmd(["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio)])

@st.cache_resource(show_spinner=False)
def load_whisper():
    from faster_whisper import WhisperModel
    # CPU int8 keeps Streamlit memory usage much lower than the old Torch pipeline.
    return WhisperModel("tiny", device="cpu", compute_type="int8", cpu_threads=2, num_workers=1)

def transcribe(audio):
    model = load_whisper()
    segments, _ = model.transcribe(str(audio), beam_size=1, vad_filter=True, condition_on_previous_text=False)
    return " ".join(s.text.strip() for s in segments if s.text.strip())

def sentence_chunks(text, max_chars=180):
    pieces = re.split(r"(?<=[.!?။!?])\s+|(?<=၊)\s+", text.strip())
    out=[]
    for p in (x.strip() for x in pieces if x.strip()):
        if len(p)<=max_chars: out.append(p); continue
        cur=""
        for w in p.split():
            if cur and len(cur)+len(w)+1>max_chars: out.append(cur); cur=""
            cur += (" " if cur else "")+w
        if cur: out.append(cur)
    return out

def generate_recap(transcript, language):
    # Lightweight chronological compression; no second LLM is loaded on the free server.
    s = sentence_chunks(transcript, 220)
    if not s: return ""
    target=min(45,max(8,len(s)))
    if len(s)>target:
        ids=sorted(set(round(i*(len(s)-1)/(target-1)) for i in range(target)))
        s=[s[i] for i in ids]
    if language=="မြန်မာဘာသာ":
        return "ဇာတ်လမ်းကို အစမှအဆုံး အဓိကဖြစ်ရပ်များအတိုင်း ပြောပြပါမယ်။ " + " ".join(s)
    return "Here is the story in chronological order. " + " ".join(s)

def tts(text, voice, out):
    import edge_tts
    async def go(): await edge_tts.Communicate(text, voice).save(str(out))
    asyncio.run(go())

def duration(path):
    r=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)],capture_output=True,text=True)
    if r.returncode: raise RuntimeError(r.stderr)
    return float(r.stdout.strip())

def make_srt(text, seconds, path):
    units=sentence_chunks(text)
    if not units: raise ValueError("Subtitle စာသားမရှိပါ။")
    weights=[max(1,len(x.replace(" ",""))) for x in units]; total=sum(weights); cur=0; rows=[]
    def stamp(x):
        ms=int(round((x-int(x))*1000)); whole=int(x); h,rem=divmod(whole,3600); m,s=divmod(rem,60)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    for i,u in enumerate(units,1):
        end=seconds if i==len(units) else cur+seconds*weights[i-1]/total
        rows.append(f"{i}\n{stamp(cur)} --> {stamp(end)}\n{u}\n"); cur=end
    path.write_text("\n".join(rows),encoding="utf-8")

def render(source, narration, srt, output, aspect):
    d=duration(narration)
    if d>MAX_RECAP_MINUTES*60+2: raise ValueError("Recap အသံက 10 မိနစ်ကျော်နေပါတယ်။")
    vf=("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" if aspect=="9:16" else "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080")
    sf=str(srt).replace("\\","/").replace(":","\\:")
    vf+=f",subtitles='{sf}':force_style='FontSize=28,Outline=2,Shadow=1,Alignment=2,MarginV=55'"
    run_cmd(["ffmpeg","-y","-stream_loop","-1","-i",str(source),"-i",str(narration),"-t",f"{d:.3f}","-vf",vf,"-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset","veryfast","-crf","25","-c:a","aac","-b:a","128k","-shortest",str(output)])

with st.sidebar:
    st.header("🎛️ Settings")
    language=st.selectbox("Recap Language",["မြန်မာဘာသာ","English"])
    voice_name=st.selectbox("🎙️ Voice",list(VOICE_OPTIONS))
    aspect=st.selectbox("📱 Format",["9:16","16:9"])
    plan=st.radio("Plan (prototype)",["Free","Premium"])
    st.info(f"{plan}: {FREE_DAILY_LIMIT if plan=='Free' else PREMIUM_DAILY_LIMIT} recaps/day\nMax: 10 minutes")

st.title("🎬 Movie Recap AI")
st.caption("Fast / low-memory mode — use videos you own or have permission to transform.")
video=st.file_uploader("🎞️ Video (max 1 GB)",type=["mp4","mkv","mov","avi","webm"])
url=st.text_input("🔗 Authorized direct video URL",placeholder="https://example.com/video.mp4")
if video and video.size>MAX_UPLOAD_MB*1024*1024:
    st.error("❌ Video သည် 1 GB ထက်ကြီးပါတယ်။"); video=None

if video or url:
    if video: st.video(video)
    if st.button("🚀 Generate Recap MP4",type="primary",use_container_width=True):
        try:
            with tempfile.TemporaryDirectory() as td:
                td=Path(td); source=td/"movie.mp4"; audio=td/"audio.wav"; narration=td/"voice.mp3"; srt=td/"subs.srt"; out=td/"recap.mp4"
                if video: source.write_bytes(video.getbuffer())
                else:
                    import requests
                    if not url.startswith(("http://","https://")): raise ValueError("http/https direct video URL ထည့်ပါ။")
                    with st.spinner("🔗 Downloading video..."):
                        r=requests.get(url,stream=True,timeout=60,headers={"User-Agent":"MovieRecapAI/1.0"}); r.raise_for_status(); total=0
                        with open(source,"wb") as f:
                            for chunk in r.iter_content(1024*1024):
                                if chunk:
                                    total+=len(chunk)
                                    if total>MAX_UPLOAD_MB*1024*1024: raise ValueError("Video link သည် 1 GB ထက်ကြီးပါတယ်။")
                                    f.write(chunk)
                with st.spinner("🎧 Extracting audio..."): extract_audio(source,audio)
                with st.spinner("🗣️ Fast transcription..."): transcript=transcribe(audio)
                if not transcript: raise ValueError("Speech/dialogue မတွေ့ပါ။")
                st.subheader("✍️ Recap Script")
                recap=generate_recap(transcript,language); st.text_area("Recap",recap,height=280)
                with st.spinner("🎙️ Generating voice..."): tts(recap,VOICE_OPTIONS[voice_name],narration)
                d=duration(narration)
                if d>MAX_RECAP_MINUTES*60: raise ValueError("Narration က 10 မိနစ်ကျော်နေပါတယ်။")
                make_srt(recap,d,srt)
                with st.spinner("🎞️ Fast MP4 render..."): render(source,narration,srt,out,aspect)
                data=out.read_bytes()
                st.success(f"✅ Done — {d/60:.1f} minutes")
                st.video(data)
                st.download_button("⬇️ Download MP4",data,"movie_recap.mp4","video/mp4")
                st.download_button("⬇️ Download Subtitle",srt.read_text(encoding="utf-8"),"subtitles.srt","application/x-subrip")
        except Exception as e: st.error(f"❌ Error: {e}")
else:
    st.info("Video upload သို့မဟုတ် authorized direct video URL ထည့်ပါ။")

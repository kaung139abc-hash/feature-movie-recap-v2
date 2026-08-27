import asyncio
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Movie Recap AI", page_icon="🎬", layout="wide")
MAX_UPLOAD_MB = 1024
MAX_RECAP_MINUTES = 10
VOICE_OPTIONS = {
    "🇲🇲 Myanmar Male": "my-MM-ThihaNeural", "🇲🇲 Myanmar Female": "my-MM-NilarNeural",
    "🇺🇸 Young Male": "en-US-GuyNeural", "🇺🇸 Young Female": "en-US-JennyNeural",
    "🇺🇸 Cinematic Male": "en-US-EricNeural", "🇺🇸 Cinematic Female": "en-US-AriaNeural",
}

def binpath(name):
    p = shutil.which(name)
    if p: return p
    try:
        import imageio_ffmpeg
        if name in ("ffmpeg", "ffprobe"):
            return imageio_ffmpeg.get_ffmpeg_exe() if name == "ffmpeg" else None
    except Exception:
        pass
    return None

def run_cmd(cmd):
    exe = binpath(cmd[0]) if cmd else None
    if not exe: raise RuntimeError(f"{cmd[0]} executable မတွေ့ပါ။")
    r = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr[-4000:])

def extract_audio(video, audio):
    run_cmd(["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio)])

@st.cache_resource(show_spinner=False)
def load_whisper():
    from faster_whisper import WhisperModel
    return WhisperModel("tiny", device="cpu", compute_type="int8", cpu_threads=2, num_workers=1)

def transcribe(audio):
    segments, _ = load_whisper().transcribe(str(audio), beam_size=1, vad_filter=True, condition_on_previous_text=False)
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
    s=sentence_chunks(transcript,220)
    if not s: return ""
    target=min(45,max(8,len(s)))
    if len(s)>target:
        ids=sorted(set(round(i*(len(s)-1)/(target-1)) for i in range(target))); s=[s[i] for i in ids]
    prefix="ဇာတ်လမ်းကို အစမှအဆုံး အဓိကဖြစ်ရပ်များအတိုင်း ပြောပြပါမယ်။ " if language=="မြန်မာဘာသာ" else "Here is the story in chronological order. "
    return prefix+" ".join(s)

def tts(text, voice, out):
    import edge_tts
    async def go(): await edge_tts.Communicate(text, voice).save(str(out))
    asyncio.run(go())

def ffprobe_duration(path):
    ff = binpath("ffmpeg")
    if not ff: raise RuntimeError("FFmpeg မတွေ့ပါ။")
    r=subprocess.run([ff,"-i",str(path)],capture_output=True,text=True)
    m=re.search(r"Duration:\s+(\d+):(\d+):(\d+(?:\.\d+)?)",r.stderr)
    if not m: raise RuntimeError("Video duration မဖတ်နိုင်ပါ။")
    return int(m.group(1))*3600+int(m.group(2))*60+float(m.group(3))

def make_srt(text, seconds, path):
    units=sentence_chunks(text)
    if not units: raise ValueError("Subtitle စာသားမရှိပါ။")
    weights=[max(1,len(x.replace(" ",""))) for x in units]; total=sum(weights); cur=0; rows=[]
    def stamp(x):
        ms=int(round((x-int(x))*1000)); whole=int(x); h,rem=divmod(whole,3600); m,s=divmod(rem,60); return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    for i,u in enumerate(units,1):
        end=seconds if i==len(units) else cur+seconds*weights[i-1]/total
        rows.append(f"{i}\n{stamp(cur)} --> {stamp(end)}\n{u}\n"); cur=end
    path.write_text("\n".join(rows),encoding="utf-8")

def render(source,narration,srt,out,aspect):
    sec=ffprobe_duration(narration)
    if sec>MAX_RECAP_MINUTES*60+2: raise ValueError("Recap အသံက 10 မိနစ်ကျော်နေပါတယ်။")
    vf=("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" if aspect=="9:16" else "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080")
    sf=str(srt).replace("\\","/").replace(":","\\:")
    vf+=f",subtitles='{sf}':force_style='FontName=Noto Sans,FontSize=28,Outline=2,Shadow=1,Alignment=2,MarginV=55'"
    run_cmd(["ffmpeg","-y","-stream_loop","-1","-i",str(source),"-i",str(narration),"-t",f"{sec:.3f}","-vf",vf,"-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset","veryfast","-crf","25","-c:a","aac","-b:a","128k","-shortest",str(out)])

def download_youtube(url, out_dir):
    from yt_dlp import YoutubeDL
    template = str(Path(out_dir) / "source.%(ext)s")
    opts = {
        "outtmpl": template,
        "format": "best[ext=mp4][height<=720]/best[height<=720]/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "retries": 2,
        "socket_timeout": 30,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloaded = Path(ydl.prepare_filename(info))
        if not downloaded.exists():
            candidates = list(Path(out_dir).glob("source.*"))
            if not candidates: raise RuntimeError("YouTube video download ပြီးတဲ့ဖိုင် မတွေ့ပါ။")
            downloaded = candidates[0]
    return downloaded

st.title("🎬 Movie Recap AI")
st.caption("Upload a video or use an authorized direct video/YouTube URL.")
with st.sidebar:
    language=st.selectbox("Recap Language",["မြန်မာဘာသာ","English"])
    voice_name=st.selectbox("🎙️ Voice",list(VOICE_OPTIONS))
    aspect=st.selectbox("📱 Video Format",["9:16","16:9"])
    st.info("Free: 5 recaps/day • Maximum output: 10 minutes")
    st.caption("⚠️ Use videos you own or have permission to transform/publish.")

video=st.file_uploader("🎞️ Video (max 1 GB)",type=["mp4","mkv","mov","avi","webm"])
url=st.text_input("🔗 Video / YouTube URL",placeholder="https://youtu.be/... or https://example.com/video.mp4")
if video and video.size>MAX_UPLOAD_MB*1024*1024: st.error("❌ Video က 1 GB ထက်ကြီးနေပါတယ်။"); video=None

if st.button("🚀 Generate Recap MP4",type="primary",use_container_width=True):
    if not video and not url: st.warning("Video upload သို့မဟုတ် URL ထည့်ပါ။"); st.stop()
    try:
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); audio=td/"audio.wav"; narration=td/"voice.mp3"; srt=td/"subtitles.srt"; out=td/"movie_recap.mp4"
            if video:
                source=td/"movie.mp4"; source.write_bytes(video.getbuffer())
            else:
                if not url.startswith(("http://","https://")): raise ValueError("Valid http/https URL ထည့်ပါ။")
                is_youtube = any(x in url.lower() for x in ("youtube.com/watch", "youtu.be/", "youtube.com/shorts/"))
                with st.spinner("🔗 Video ကို fetch လုပ်နေပါတယ်..."):
                    if is_youtube:
                        source=download_youtube(url, td)
                    else:
                        import requests
                        source=td/"movie.mp4"
                        r=requests.get(url,stream=True,timeout=60,headers={"User-Agent":"MovieRecapAI/1.0"}); r.raise_for_status(); total=0
                        with open(source,"wb") as f:
                            for chunk in r.iter_content(1024*1024):
                                if chunk:
                                    total+=len(chunk)
                                    if total>MAX_UPLOAD_MB*1024*1024: raise ValueError("Video link က 1 GB ထက်ကျော်နေပါတယ်။")
                                    f.write(chunk)
            with st.spinner("🎧 Extracting audio..."): extract_audio(source,audio)
            with st.spinner("🗣️ Transcribing with low-memory Whisper..."): transcript=transcribe(audio)
            if not transcript: raise ValueError("Speech/dialogue မတွေ့ပါ။")
            st.subheader("✍️ Recap Script"); recap=generate_recap(transcript,language); st.text_area("Recap",recap,height=280)
            with st.spinner("🎙️ Generating AI voice..."): tts(recap,VOICE_OPTIONS[voice_name],narration)
            sec=ffprobe_duration(narration)
            if sec>MAX_RECAP_MINUTES*60: raise ValueError("Narration က 10 မိနစ်ကျော်သွားပါတယ်။")
            make_srt(recap,sec,srt)
            with st.spinner("🎬 Rendering MP4..."): render(source,narration,srt,out,aspect)
            data=out.read_bytes(); st.success(f"✅ Finished — {sec/60:.1f} minutes"); st.video(data)
            st.download_button("⬇️ Download MP4",data,"movie_recap.mp4","video/mp4")
    except Exception as e: st.error(f"❌ Error: {e}")

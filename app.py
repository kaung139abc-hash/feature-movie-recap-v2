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
VOICES = {"🇲🇲 Myanmar Male": "my-MM-ThihaNeural", "🇲🇲 Myanmar Female": "my-MM-NilarNeural"}

def ffmpeg_exe():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError("FFmpeg မတွေ့ပါ။ requirements.txt ထဲမှာ imageio-ffmpeg ထည့်ထားကြောင်း စစ်ပါ။") from exc

def run_ffmpeg(args):
    result = subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", *map(str, args)], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"FFmpeg error:\n{(result.stderr or result.stdout or 'Unknown FFmpeg error').strip()[-5000:]}")
    return result

def chunks(text, limit=220):
    text = (text or "").strip()
    if not text: return []
    parts = re.split(r"(?<=[.!?။])\s+|(?<=၊)\s+", text)
    out = []
    for part in parts:
        part = part.strip()
        while len(part) > limit:
            cut = part.rfind(" ", 0, limit + 1)
            if cut < max(40, limit // 2): cut = limit
            out.append(part[:cut].strip()); part = part[cut:].strip()
        if part: out.append(part)
    return out

def translate_mm(text):
    text = (text or "").strip()
    if not text: return text
    letters = sum(c.isalpha() for c in text); mm = sum(1 for c in text if "\u1000" <= c <= "\u109f")
    if letters and mm / max(1, letters) > .35: return text
    from deep_translator import GoogleTranslator
    tr = GoogleTranslator(source="auto", target="my")
    pieces=[]; cur=""
    for word in text.split():
        if cur and len(cur)+len(word)+1 > 3000: pieces.append(cur); cur=word
        else: cur += (" " if cur else "") + word
    if cur: pieces.append(cur)
    return " ".join(tr.translate(x) for x in pieces)

def recap10(text):
    s=chunks(text,220)
    if not s: return ""
    target=min(150,len(s))
    if len(s)<=target: return " ".join(s)
    if target==1: return s[0]
    ids=sorted({round(i*(len(s)-1)/(target-1)) for i in range(target)})
    return " ".join(s[i] for i in ids)

def transcribe(path):
    from faster_whisper import WhisperModel
    model=WhisperModel("tiny",device="cpu",compute_type="int8",cpu_threads=2,num_workers=1)
    segments,_=model.transcribe(str(path),beam_size=1,vad_filter=True,condition_on_previous_text=False)
    return " ".join(x.text.strip() for x in segments if x.text.strip())

def tts(text,voice,output):
    import edge_tts
    async def generate(): await edge_tts.Communicate(text,voice).save(str(output))
    try: asyncio.run(generate())
    except RuntimeError as exc:
        if "asyncio.run() cannot be called" not in str(exc): raise
        loop=asyncio.new_event_loop()
        try: loop.run_until_complete(generate())
        finally: loop.close()

def media_duration(path):
    result=subprocess.run([ffmpeg_exe(),"-hide_banner","-i",str(path)],capture_output=True,text=True)
    m=re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",result.stderr or "")
    if not m: raise RuntimeError("Media duration မဖတ်နိုင်ပါ။")
    return int(m[1])*3600+int(m[2])*60+float(m[3])

def make_srt(text,seconds,output):
    lines=chunks(text,160)
    if not lines: raise RuntimeError("Subtitle စာသားမရှိပါ။")
    weights=[max(1,len(x.replace(" ",""))) for x in lines]; total=sum(weights); current=0.; rows=[]
    def timestamp(v):
        ms=int(round((v%1)*1000)); whole=int(v); h,rem=divmod(whole,3600); m,s=divmod(rem,60)
        if ms==1000: ms=0; s+=1
        return f"{h:02}:{m:02}:{s:02},{ms:03}"
    for i,line in enumerate(lines,1):
        end=seconds if i==len(lines) else current+seconds*weights[i-1]/total
        rows.append(f"{i}\n{timestamp(current)} --> {timestamp(end)}\n{line}\n"); current=end
    output.write_text("\n".join(rows),encoding="utf-8-sig")

def escape_subtitle_path(path):
    return str(path).replace("\\","/").replace("'","\\'").replace(":",r"\:").replace("[",r"\[").replace("]",r"\]")

def render(video,audio,subtitle,output,vertical):
    duration=media_duration(audio); size="720:1280" if vertical else "1280:720"
    vf=f"scale={size}:force_original_aspect_ratio=increase,crop={size},subtitles='{escape_subtitle_path(subtitle)}':force_style='FontSize=24,Outline=2,Alignment=2,MarginV=40'"
    run_ffmpeg(["-y","-stream_loop","-1","-i",video,"-i",audio,"-t",f"{duration:.3f}","-map","0:v:0","-map","1:a:0","-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","27","-pix_fmt","yuv420p","-c:a","aac","-b:a","128k","-shortest",output])

def download_video(url,output):
    """Prefer a single-file MP4 so yt-dlp never needs to merge formats with ffmpeg."""
    first_error=None
    try:
        import yt_dlp
        opts={"outtmpl":str(output.with_suffix(".%(ext)s")),"format":"b[ext=mp4]/b","noplaylist":True,"quiet":True,"no_warnings":True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info=ydl.extract_info(url,download=True); prepared=Path(ydl.prepare_filename(info))
            candidates=[output,prepared,prepared.with_suffix(".mp4")]
            for candidate in candidates:
                if candidate.exists() and candidate.stat().st_size:
                    if candidate!=output:
                        if output.exists(): output.unlink()
                        candidate.replace(output)
                    break
            else: raise RuntimeError("yt-dlp download ပြီးပေမယ့် output file မတွေ့ပါ။")
    except Exception as exc: first_error=exc
    if output.exists() and output.stat().st_size:
        if output.stat().st_size>MAX_MB*1024*1024: output.unlink(missing_ok=True); raise ValueError("Video က 1GB ကျော်နေပါတယ်။")
        return
    try:
        response=requests.get(url,stream=True,timeout=90,headers={"User-Agent":"Mozilla/5.0 MovieRecapAI"}); response.raise_for_status()
        if "text/html" in response.headers.get("content-type","").lower(): raise RuntimeError(str(first_error or "URL သည် direct video မဟုတ်ပါ။"))
        size=0
        with output.open("wb") as handle:
            for block in response.iter_content(1024*1024):
                if not block: continue
                size+=len(block)
                if size>MAX_MB*1024*1024: raise ValueError("Video က 1GB ကျော်နေပါတယ်။")
                handle.write(block)
    except Exception as second: raise RuntimeError(f"Video link ကို ရယူလို့မရပါ: {second}") from second

def youtube_search(query,token="",limit=20):
    key=st.secrets.get("YOUTUBE_API_KEY","")
    if not key: raise RuntimeError("YOUTUBE_API_KEY ကို Streamlit Secrets ထဲထည့်ပါ။")
    params={"part":"snippet","q":query,"type":"video","videoLicense":"creativeCommon","maxResults":limit,"key":key}
    if token: params["pageToken"]=token
    r=requests.get("https://www.googleapis.com/youtube/v3/search",params=params,timeout=20); data=r.json()
    if r.status_code!=200: raise RuntimeError(data.get("error",{}).get("message",f"YouTube API HTTP {r.status_code}"))
    items=[]
    for x in data.get("items",[]):
        vid=x.get("id",{}).get("videoId")
        if vid:
            s=x.get("snippet",{}); items.append({"title":s.get("title",""),"channel":s.get("channelTitle",""),"url":f"https://www.youtube.com/watch?v={vid}"})
    return items,data.get("nextPageToken","")

st.title("🎬 Movie Recap AI")
st.caption("🎞️ Upload • 🔗 Link • 🔎 YouTube reusable videos → 🚀 Generate → 🇲🇲 Recap MP4")
with st.sidebar:
    vertical=st.selectbox("📱 Video Format",["9:16","16:9"])=="9:16"
    voice=st.selectbox("🎙️ Myanmar Voice",list(VOICES)); st.info("🎯 Target: ဇာတ်လမ်းကို ~10 မိနစ်အတွင်း အကျဉ်းချုပ်")
if "yt_results" not in st.session_state: st.session_state.yt_results=[]
if "yt_token" not in st.session_state: st.session_state.yt_token=""
if "selected_url" not in st.session_state: st.session_state.selected_url=""
st.subheader("🔎 YouTube မှာ ပြန်လည်အသုံးပြုခွင့် သတ်မှတ်ထားတဲ့ Video ရှာရန်")
query=st.text_input("Search",value="Chinese drama Creative Commons",placeholder="ဥပမာ — Chinese short film, Chinese drama")
a,b=st.columns(2)
with a:
    if st.button("🔎 Search YouTube",use_container_width=True):
        try: st.session_state.yt_results,st.session_state.yt_token=youtube_search(query.strip() or "Chinese drama")
        except Exception as exc: st.error(f"YouTube Search Error: {exc}")
with b:
    if st.button("➕ Load More",use_container_width=True) and st.session_state.yt_token:
        try:
            more,token=youtube_search(query.strip() or "Chinese drama",st.session_state.yt_token); st.session_state.yt_results.extend(more); st.session_state.yt_token=token
        except Exception as exc: st.error(f"Load More Error: {exc}")
for i,item in enumerate(st.session_state.yt_results):
    c1,c2=st.columns([5,1]); c1.markdown(f"**{i+1}. {item['title']}**  \n`{item['channel']}`")
    if c2.button("သုံးမယ်",key=f"yt_{i}"): st.session_state.selected_url=item["url"]; st.rerun()
if st.session_state.selected_url: st.success("✅ YouTube link ရွေးပြီးပါပြီ")
url=st.text_input("🔗 Movie Video Link",value=st.session_state.selected_url,placeholder="YouTube / supported video page / direct video URL")
upload=st.file_uploader("🎞️ Movie Video (max 1 GB)",type=["mp4","mkv","mov","avi","webm"])
if st.button("🚀 Generate Myanmar Movie Recap",type="primary",use_container_width=True):
    if not upload and not url.strip(): st.error("❌ Video Upload လုပ်ပါ သို့မဟုတ် Video Link ထည့်ပါ။"); st.stop()
    try:
        with tempfile.TemporaryDirectory(prefix="movie_recap_") as td:
            work=Path(td); video=work/"movie.mp4"; audio=work/"audio.wav"; voice_file=work/"voice.mp3"; subtitle=work/"mm.srt"; output=work/"movie_recap_mm.mp4"
            if upload:
                if upload.size>MAX_MB*1024*1024: raise ValueError("Video က 1GB ကျော်နေပါတယ်။")
                with st.spinner("📥 Uploaded movie ကိုဖတ်နေပါတယ်..."): video.write_bytes(upload.getbuffer())
            else:
                with st.spinner("🔗 Video ကို ရယူနေပါတယ်..."): download_video(url.strip(),video)
            if not video.exists() or video.stat().st_size==0: raise RuntimeError("Video file မရပါ။")
            with st.spinner("🎙️ Audio ကိုထုတ်နေပါတယ်..."): run_ffmpeg(["-y","-i",video,"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",audio])
            with st.spinner("📝 Movie ကိုနားထောင်ပြီး စာသားပြောင်းနေပါတယ်..."): text=transcribe(audio)
            if not text.strip(): raise RuntimeError("Movie ထဲက အသံစာသားမရပါ။")
            with st.spinner("🇲🇲 မြန်မာလို ဘာသာပြန်/အကျဉ်းချုပ်နေပါတယ်..."): script=recap10(translate_mm(text))
            if not script.strip(): raise RuntimeError("Recap စာသားမရပါ။")
            with st.spinner("🎙️ Myanmar voice ထုတ်နေပါတယ်..."): tts(script,VOICES[voice],voice_file)
            make_srt(script,media_duration(voice_file),subtitle)
            with st.spinner("🎬 Movie Scene + Myanmar Voice + Subtitle ပေါင်းနေပါတယ်..."): render(video,voice_file,subtitle,output,vertical)
            if output.exists():
                st.success("✅ Myanmar Movie Recap MP4 ပြီးပါပြီ!")
                st.video(str(output)); st.download_button("⬇️ Download MP4",output.read_bytes(),file_name="movie_recap_mm.mp4",mime="video/mp4")
            else: raise RuntimeError("Output MP4 မထွက်ပါ။")
    except Exception as exc: st.error(f"❌ Generate Error: {exc}")

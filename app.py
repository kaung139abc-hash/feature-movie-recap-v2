import asyncio
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="Movie Recap AI", page_icon="🎬", layout="wide")
MAX_UPLOAD_MB=1024; MAX_RECAP_MINUTES=10
VOICE_OPTIONS={"🇲🇲 Myanmar Male":"my-MM-ThihaNeural","🇲🇲 Myanmar Female":"my-MM-NilarNeural","🇺🇸 Young Male":"en-US-GuyNeural","🇺🇸 Young Female":"en-US-JennyNeural","🇺🇸 Cinematic Male":"en-US-EricNeural","🇺🇸 Cinematic Female":"en-US-AriaNeural"}
def binpath(name):
 p=shutil.which(name)
 if p:return p
 if name=="ffmpeg":
  try:
   import imageio_ffmpeg; return imageio_ffmpeg.get_ffmpeg_exe()
  except Exception:pass
 return None
def run_cmd(cmd):
 exe=binpath(cmd[0])
 if not exe:raise RuntimeError(f"{cmd[0]} executable မတွေ့ပါ။")
 r=subprocess.run([exe,*cmd[1:]],capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stderr[-4000:])
def extract_audio(video,audio):run_cmd(["ffmpeg","-y","-i",str(video),"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(audio)])
@st.cache_resource(show_spinner=False)
def load_whisper():
 from faster_whisper import WhisperModel
 return WhisperModel("tiny",device="cpu",compute_type="int8",cpu_threads=2,num_workers=1)
def transcribe(audio):
 segs,_=load_whisper().transcribe(str(audio),beam_size=1,vad_filter=True,condition_on_previous_text=False)
 return " ".join(s.text.strip() for s in segs if s.text.strip())
def sentence_chunks(text,max_chars=180):
 pieces=re.split(r"(?<=[.!?။!?])\s+|(?<=၊)\s+",text.strip());out=[]
 for p in (x.strip() for x in pieces if x.strip()):
  if len(p)<=max_chars:out.append(p);continue
  cur=""
  for w in p.split():
   if cur and len(cur)+len(w)+1>max_chars:out.append(cur);cur=""
   cur+=(" " if cur else "")+w
  if cur:out.append(cur)
 return out
def generate_recap(transcript,language):
 s=sentence_chunks(transcript,220)
 if not s:return ""
 target=min(45,max(8,len(s)))
 if len(s)>target:
  ids=sorted(set(round(i*(len(s)-1)/(target-1)) for i in range(target)));s=[s[i] for i in ids]
 prefix="ဇာတ်လမ်းကို အစမှအဆုံး အဓိကဖြစ်ရပ်များအတိုင်း ပြောပြပါမယ်။ " if language=="မြန်မာဘာသာ" else "Here is the story in chronological order. "
 return prefix+" ".join(s)
def tts(text,voice,out):
 import edge_tts
 async def go():await edge_tts.Communicate(text,voice).save(str(out))
 asyncio.run(go())
def duration(path):
 probe=shutil.which("ffprobe")
 if probe:
  r=subprocess.run([probe,"-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)],capture_output=True,text=True)
  if r.returncode==0:return float(r.stdout.strip())
 ff=binpath("ffmpeg")
 if not ff:raise RuntimeError("FFmpeg မတွေ့ပါ။")
 r=subprocess.run([ff,"-i",str(path)],capture_output=True,text=True);m=re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",r.stderr)
 if not m:raise RuntimeError("Media duration ကိုဖတ်မရပါ။")
 return int(m.group(1))*3600+int(m.group(2))*60+float(m.group(3))
def make_srt(text,seconds,path):
 units=sentence_chunks(text)
 if not units:raise ValueError("Subtitle စာသားမရှိပါ။")
 weights=[max(1,len(x.replace(" ",""))) for x in units];total=sum(weights);cur=0;rows=[]
 def stamp(x):
  ms=int(round((x-int(x))*1000));whole=int(x);h,rem=divmod(whole,3600);m,s=divmod(rem,60);return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
 for i,u in enumerate(units,1):
  end=seconds if i==len(units) else cur+seconds*weights[i-1]/total;rows.append(f"{i}\n{stamp(cur)} --> {stamp(end)}\n{u}\n");cur=end
 path.write_text("\n".join(rows),encoding="utf-8")
def render(source,narration,srt,out,aspect):
 sec=duration(narration)
 if sec>MAX_RECAP_MINUTES*60+2:raise ValueError("Recap အသံက 10 မိနစ်ကျော်နေပါတယ်။")
 vf=("scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" if aspect=="9:16" else "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080")
 sf=str(srt).replace("\\","/").replace(":","\\:");vf+=f",subtitles='{sf}':force_style='FontName=Noto Sans,FontSize=28,Outline=2,Shadow=1,Alignment=2,MarginV=55'"
 run_cmd(["ffmpeg","-y","-stream_loop","-1","-i",str(source),"-i",str(narration),"-t",f"{sec:.3f}","-vf",vf,"-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset","veryfast","-crf","25","-c:a","aac","-b:a","128k","-shortest",str(out)])
def download_youtube(url,folder):
 from yt_dlp import YoutubeDL
 # Prefer a single-file MP4 first; this avoids yt-dlp needing to merge formats.
 opts={"outtmpl":str(Path(folder)/"youtube_source.%(ext)s"),"format":"best[ext=mp4]/best","noplaylist":True,"quiet":True,"no_warnings":True,"retries":2,"fragment_retries":2,"socket_timeout":30}
 with YoutubeDL(opts) as ydl:
  info=ydl.extract_info(url,download=True);prepared=Path(ydl.prepare_filename(info))
 for p in [prepared,prepared.with_suffix(".mp4"),Path(folder)/"youtube_source.mp4"]:
  if p.exists() and p.stat().st_size:return p
 matches=list(Path(folder).glob("youtube_source.*"))
 if matches:return matches[0]
 raise RuntimeError("YouTube video download ပြီးပေမယ့် video file မတွေ့ပါ။")
st.title("🎬 Movie Recap AI");st.caption("Upload a video or use an authorized direct video URL.")
with st.sidebar:
 language=st.selectbox("Recap Language",["မြန်မာဘာသာ","English"]);voice_name=st.selectbox("🎙️ Voice",list(VOICE_OPTIONS));aspect=st.selectbox("📱 Video Format",["9:16","16:9"]);st.info("Free: 5 recaps/day • Maximum output: 10 minutes");st.caption("⚠️ Use videos you own or have permission to transform/publish.")
video=st.file_uploader("🎞️ Video (max 1 GB)",type=["mp4","mkv","mov","avi","webm"]);url=st.text_input("🔗 YouTube or direct video URL",placeholder="https://youtu.be/... or https://example.com/video.mp4")
if video and video.size>MAX_UPLOAD_MB*1024*1024:st.error("❌ Video က 1 GB ထက်ကြီးနေပါတယ်။");video=None
if st.button("🚀 Generate Recap MP4",type="primary",use_container_width=True):
 if not video and not url:st.warning("Video upload သို့မဟုတ် video URL ထည့်ပါ။");st.stop()
 try:
  with tempfile.TemporaryDirectory() as td:
   td=Path(td);source=td/"movie.mp4";audio=td/"audio.wav";narration=td/"voice.mp3";srt=td/"subtitles.srt";out=td/"movie_recap.mp4"
   if video:
    with st.spinner("📥 Saving uploaded video..."):source.write_bytes(video.getbuffer())
   else:
    if not url.startswith(("http://","https://")):raise ValueError("Valid http/https URL ထည့်ပါ။")
    if re.search(r"(?:youtube\.com/watch|youtu\.be/|youtube\.com/shorts/|youtube\.com/live/)",url,re.I):
     with st.spinner("🔗 Downloading a compatible YouTube format..."):source=download_youtube(url,td)
    else:
     import requests
     with st.spinner("🔗 Downloading direct video..."):
      r=requests.get(url,stream=True,timeout=60,headers={"User-Agent":"MovieRecapAI/1.0"});r.raise_for_status();total=0
      with open(source,"wb") as f:
       for chunk in r.iter_content(1024*1024):
        if chunk:
         total+=len(chunk)
         if total>MAX_UPLOAD_MB*1024*1024:raise ValueError("Video link က 1 GB ထက်ကျော်နေပါတယ်။")
         f.write(chunk)
   if not source.exists() or not source.stat().st_size:raise ValueError("Video file မရပါ။")
   with st.spinner("🎧 Extracting audio..."):extract_audio(source,audio)
   with st.spinner("🗣️ Transcribing with low-memory Whisper..."):transcript=transcribe(audio)
   if not transcript:raise ValueError("Speech/dialogue မတွေ့ပါ။")
   st.subheader("✍️ Recap Script");recap=generate_recap(transcript,language);st.text_area("Recap",recap,height=280)
   with st.spinner("🎙️ Generating AI voice..."):tts(recap,VOICE_OPTIONS[voice_name],narration)
   sec=duration(narration)
   if sec>MAX_RECAP_MINUTES*60:raise ValueError("Narration က 10 မိနစ်ကျော်သွားပါတယ်။")
   make_srt(recap,sec,srt)
   with st.spinner("🎬 Rendering MP4..."):render(source,narration,srt,out,aspect)
   data=out.read_bytes();st.success(f"✅ Finished — {sec/60:.1f} minutes");st.video(data);st.download_button("⬇️ Download MP4",data,"movie_recap.mp4","video/mp4")
 except Exception as e:st.error(f"❌ Error: {e}")

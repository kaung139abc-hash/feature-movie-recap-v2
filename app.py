import asyncio,re,shutil,subprocess,tempfile,json
from pathlib import Path
import streamlit as st
st.set_page_config(page_title="Movie Recap AI",page_icon="🎬",layout="wide")
MAX_UPLOAD_MB=1024
VOICES={"🇲🇲 Myanmar Male":"my-MM-ThihaNeural","🇲🇲 Myanmar Female":"my-MM-NilarNeural"}
def ffmpeg():
 p=shutil.which("ffmpeg")
 if p:return p
 import imageio_ffmpeg;return imageio_ffmpeg.get_ffmpeg_exe()
def cmd(args):
 r=subprocess.run([ffmpeg(),*args],capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stderr[-3500:])
def duration(p):
 r=subprocess.run([ffmpeg(),"-i",str(p)],capture_output=True,text=True);m=re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",r.stderr)
 if not m:raise RuntimeError("Media duration မဖတ်နိုင်ပါ။")
 return int(m[1])*3600+int(m[2])*60+float(m[3])
def chunks(text,n=240):
 parts=re.split(r"(?<=[.!?။])\s+|(?<=၊)\s+",(text or "").strip());out=[]
 for p in parts:
  p=p.strip()
  while len(p)>n:out.append(p[:n]);p=p[n:]
  if p:out.append(p)
 return out
def recap(text):
 s=chunks(text,240)
 if len(s)<=240:return " ".join(s)
 ids=sorted(set(round(i*(len(s)-1)/239) for i in range(240)))
 return " ".join(s[i] for i in ids)
def tts(text,voice,out):
 import edge_tts
 async def go():await edge_tts.Communicate(text,voice).save(str(out))
 asyncio.run(go())
def make_srt(text,secs,out):
 a=chunks(text,180);weights=[max(1,len(x.replace(" ",""))) for x in a];tot=sum(weights);cur=0;rows=[]
 def ts(x):
  ms=int((x%1)*1000);z=int(x);h,z=divmod(z,3600);m,s=divmod(z,60);return f"{h:02}:{m:02}:{s:02},{ms:03}"
 for i,x in enumerate(a,1):
  end=secs if i==len(a) else cur+secs*weights[i-1]/tot;rows.append(f"{i}\n{ts(cur)} --> {ts(end)}\n{x}\n");cur=end
 out.write_text("\n".join(rows),encoding="utf-8")
def render(source,voice,sub,out,vertical):
 sec=duration(voice);vf="scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280" if vertical else "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720"
 sp=str(sub).replace("\\","/").replace(":","\\:");vf+=f",subtitles='{sp}':force_style='FontName=Noto Sans,FontSize=24,Outline=2,Alignment=2,MarginV=40'"
 cmd(["-y","-stream_loop","-1","-i",str(source),"-i",str(voice),"-t",f"{sec:.2f}","-vf",vf,"-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset","veryfast","-crf","27","-c:a","aac","-b:a","128k","-shortest",str(out)])
def youtube_transcript(url):
 from youtube_transcript_api import YouTubeTranscriptApi
 m=re.search(r"(?:v=|youtu\.be/|shorts/|live/)([A-Za-z0-9_-]{11})",url)
 if not m:raise ValueError("YouTube URL မမှန်ပါ။")
 api=YouTubeTranscriptApi();vid=m.group(1)
 try:tr=api.fetch(vid,languages=["my","en","th","lo"])
 except Exception:
  try:tr=api.fetch(vid)
  except Exception as e:raise RuntimeError("ဒီ YouTube video မှာ အသုံးပြုလို့ရတဲ့ transcript/captions မတွေ့ပါ။") from e
 return " ".join(x.text for x in tr)
def direct_download(url,out):
 import requests
 r=requests.get(url,stream=True,timeout=60,headers={"User-Agent":"MovieRecapAI/1.0"});r.raise_for_status();size=0
 with open(out,"wb") as f:
  for b in r.iter_content(1024*1024):
   if b:
    size+=len(b)
    if size>MAX_UPLOAD_MB*1024*1024:raise ValueError("Video က 1GB ကျော်နေပါတယ်။")
    f.write(b)
def transcribe(path):
 from faster_whisper import WhisperModel
 model=WhisperModel("tiny",device="cpu",compute_type="int8",cpu_threads=2,num_workers=1);segs,_=model.transcribe(str(path),beam_size=1,vad_filter=True,condition_on_previous_text=False)
 return " ".join(x.text.strip() for x in segs if x.text.strip())
def public_movies():
 p=Path("public_domain_movies.json")
 if not p.exists():return []
 try:return json.loads(p.read_text(encoding="utf-8"))
 except:return []
st.title("🎬 Movie Recap AI");st.caption("Public-domain movie library + Movie upload → Burmese recap → Burmese voice → Subtitle → MP4")
with st.sidebar:
 vertical=st.selectbox("📱 Format",["9:16","16:9"])=="9:16";voice=st.selectbox("🎙️ Myanmar Voice",list(VOICES));st.info("Recap length is automatic");st.caption("Use content you own, have permission to transform, or public-domain content.")
movies=public_movies()
if movies:
 st.subheader("🎞️ Public-domain Movie Library")
 labels=[m["title"] for m in movies];pick=st.selectbox("Movie ရွေးပါ",["— မရွေးသေး —"]+labels)
 if pick!="— မရွေးသေး —":st.caption(next(m["url"] for m in movies if m["title"]==pick))
up=st.file_uploader("🎞️ Movie (max 1 GB)",type=["mp4","mkv","mov","avi","webm"]);url=st.text_input("🔗 YouTube or direct video URL")
if st.button("🚀 Generate Recap MP4",type="primary",use_container_width=True):
 if not up and not url and pick=="— မရွေးသေး —":st.warning("Movie ရွေးပါ၊ Movie upload လုပ်ပါ၊ သို့မဟုတ် URL ထည့်ပါ။");st.stop()
 try:
  with tempfile.TemporaryDirectory() as td:
   td=Path(td);src=td/"source.mp4";wav=td/"audio.wav";vo=td/"voice.mp3";sub=td/"sub.srt";out=td/"movie_recap.mp4"
   if up:
    if up.size>MAX_UPLOAD_MB*1024*1024:raise ValueError("Movie က 1GB ကျော်နေပါတယ်။")
    with st.spinner("📥 Saving movie..."):src.write_bytes(up.getbuffer())
    with st.spinner("🎧 Reading movie dialogue..."):cmd(["-y","-i",str(src),"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(wav)]);text=transcribe(wav)
   elif url and re.search(r"(?:youtube\.com|youtu\.be)",url,re.I):
    with st.spinner("🔗 Reading YouTube transcript..."):text=youtube_transcript(url)
    raise RuntimeError("YouTube transcript ကို recap လုပ်နိုင်ပေမယ့် movie scene/video ကို YouTube မှာ အလိုအလျောက် download မလုပ်ပါ။ Video Scene ပါတဲ့ MP4 အတွက် public-domain movie ကို library မှာရွေးပါ သို့မဟုတ် ကိုယ်ပိုင် video upload လုပ်ပါ။")
   elif url:
    with st.spinner("🔗 Downloading direct video..."):direct_download(url,src)
    with st.spinner("🎧 Reading movie dialogue..."):cmd(["-y","-i",str(src),"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(wav)]);text=transcribe(wav)
   else:
    movie=next(m for m in movies if m["title"]==pick)
    with st.spinner("🔗 Opening public-domain movie source..."):direct_download(movie["url"],src)
    with st.spinner("🎧 Reading movie dialogue..."):cmd(["-y","-i",str(src),"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(wav)]);text=transcribe(wav)
   if not text.strip():raise ValueError("အသံ/Transcript မတွေ့ပါ။")
   script=recap(text);st.text_area("✍️ Recap",script,height=260)
   with st.spinner("🎙️ Creating Myanmar voice..."):tts(script,VOICES[voice],vo)
   d=duration(vo);make_srt(script,d,sub)
   with st.spinner("🎬 Rendering MP4 with movie scenes..."):render(src,vo,sub,out,vertical)
   data=out.read_bytes();st.success(f"✅ Done — {d/60:.1f} minutes");st.video(data);st.download_button("⬇️ Download MP4",data,"movie_recap.mp4","video/mp4")
 except Exception as e:st.error(f"❌ Error: {e}")

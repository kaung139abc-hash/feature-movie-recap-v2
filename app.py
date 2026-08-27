import asyncio,re,shutil,subprocess,tempfile,os,json
from pathlib import Path
import streamlit as st
st.set_page_config(page_title="Movie Recap AI",page_icon="🎬",layout="wide")
MAX_MB=1024
VOICES={"🇲🇲 Myanmar Male":"my-MM-ThihaNeural","🇲🇲 Myanmar Female":"my-MM-NilarNeural"}
def ffmpeg():
 p=shutil.which("ffmpeg")
 if p:return p
 import imageio_ffmpeg
 return imageio_ffmpeg.get_ffmpeg_exe()
def cmd(a):
 r=subprocess.run([ffmpeg(),*a],capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stderr[-3000:])
def chunks(t,n=220):
 parts=re.split(r"(?<=[.!?။])\s+|(?<=၊)\s+",(t or "").strip());out=[]
 for p in parts:
  p=p.strip()
  while len(p)>n:out.append(p[:n]);p=p[n:]
  if p:out.append(p)
 return out
def translate_mm(t):
 if not t.strip():return t
 letters=sum(c.isalpha() for c in t);mm=sum(1 for c in t if '\u1000'<=c<='\u109f')
 if letters and mm/max(1,letters)>.35:return t
 from deep_translator import GoogleTranslator
 tr=GoogleTranslator(source="auto",target="my");parts=[];cur=""
 for w in t.split():
  if cur and len(cur)+len(w)+1>3000:parts.append(cur);cur=w
  else:cur+=(" " if cur else "")+w
 if cur:parts.append(cur)
 return " ".join(tr.translate(p) for p in parts if p)
def recap10(t):
 s=chunks(t,220)
 if not s:return ""
 target=150 if len(s)>150 else len(s)
 if len(s)<=target:return " ".join(s)
 ids=sorted(set(round(i*(len(s)-1)/(target-1)) for i in range(target)))
 return " ".join(s[i] for i in ids)
def transcribe(p):
 from faster_whisper import WhisperModel
 m=WhisperModel("tiny",device="cpu",compute_type="int8",cpu_threads=2,num_workers=1)
 segs,_=m.transcribe(str(p),beam_size=1,vad_filter=True,condition_on_previous_text=False)
 return " ".join(s.text.strip() for s in segs if s.text.strip())
def tts(t,v,o):
 import edge_tts
 async def go():await edge_tts.Communicate(t,v).save(str(o))
 asyncio.run(go())
def dur(p):
 r=subprocess.run([ffmpeg(),"-i",str(p)],capture_output=True,text=True);m=re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",r.stderr)
 if not m:raise RuntimeError("Media duration မဖတ်နိုင်ပါ။")
 return int(m[1])*3600+int(m[2])*60+float(m[3])
def make_srt(t,sec,o):
 a=chunks(t,160);w=[max(1,len(x.replace(" ",""))) for x in a];tot=sum(w);cur=0;rows=[]
 def ts(x):
  ms=int((x%1)*1000);z=int(x);h,z=divmod(z,3600);m,s=divmod(z,60);return f"{h:02}:{m:02}:{s:02},{ms:03}"
 for i,x in enumerate(a,1):
  end=sec if i==len(a) else cur+sec*w[i-1]/tot;rows.append(f"{i}\n{ts(cur)} --> {ts(end)}\n{x}\n");cur=end
 o.write_text("\n".join(rows),encoding="utf-8")
def render(v,a,s,o,vertical):
 sec=dur(a);size="720:1280" if vertical else "1280:720";vf=f"scale={size}:force_original_aspect_ratio=increase,crop={size}"
 sp=str(s).replace("\\","/").replace(":","\\:");vf+=f",subtitles='{sp}':force_style='FontName=Noto Sans,FontSize=24,Outline=2,Alignment=2,MarginV=40'"
 cmd(["-y","-stream_loop","-1","-i",str(v),"-i",str(a),"-t",f"{sec:.2f}","-vf",vf,"-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset","veryfast","-crf","27","-c:a","aac","-b:a","128k","-shortest",str(o)])
def download_video(url,o):
 import requests
 try:
  import yt_dlp
  opts={"outtmpl":str(o.with_suffix(".%(ext)s")),"format":"bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b","merge_output_format":"mp4","noplaylist":True,"quiet":True,"no_warnings":True}
  with yt_dlp.YoutubeDL(opts) as ydl:
   info=ydl.extract_info(url,download=True);path=Path(ydl.prepare_filename(info))
   for c in [o,path,path.with_suffix(".mp4")]:
    if c.exists() and c.stat().st_size:
     if c!=o:c.rename(o)
     if o.stat().st_size>MAX_MB*1024*1024:raise ValueError("Video က 1GB ကျော်နေပါတယ်။")
     return
 except Exception as first:
  try:
   r=requests.get(url,stream=True,timeout=90,headers={"User-Agent":"Mozilla/5.0 MovieRecapAI"},allow_redirects=True);r.raise_for_status();ctype=r.headers.get("content-type","").lower()
   if "text/html" in ctype:raise RuntimeError(f"Video ကို ရယူလို့မရပါ: {first}")
   n=0
   with open(o,"wb") as f:
    for b in r.iter_content(1024*1024):
     if b:
      n+=len(b)
      if n>MAX_MB*1024*1024:raise ValueError("Video က 1GB ကျော်နေပါတယ်။")
      f.write(b)
  except Exception as second:raise RuntimeError(f"Video link ကို ရယူလို့မရပါ: {second}")
def ready_links(limit=8):
 """Find currently downloadable public-domain/CC video files from Internet Archive.
  This is a live source list, not a bundled movie library. It is refreshed when the button is pressed.
 """
 import requests
 q='mediatype:movies AND (format:"MPEG4" OR format:"h.264" OR format:"Matroska")'
 api="https://archive.org/advancedsearch.php"
 params={"q":q,"fl[]":["identifier","title"],"rows":limit,"page":1,"output":"json","sort[]":"downloads desc"}
 r=requests.get(api,params=params,timeout=20,headers={"User-Agent":"MovieRecapAI/1.0"});r.raise_for_status()
 docs=r.json().get("response",{}).get("docs",[]);out=[]
 for d in docs:
  ident=d.get("identifier")
  if ident:
   meta=requests.get(f"https://archive.org/metadata/{ident}",timeout=20).json()
   files=meta.get("files",[])
   candidates=[]
   for f in files:
    name=f.get("name","");fmt=str(f.get("format","")).lower()
    if re.search(r"\.(mp4|webm|mkv)$",name,re.I) or fmt in {"mpeg4","matroska","h.264"}:
     if not str(f.get("name","")).endswith("_files.xml"):candidates.append(name)
   if candidates:
    name=sorted(candidates,key=lambda x:(0 if x.lower().endswith(".mp4") else 1,len(x)))[0]
    from urllib.parse import quote
    url=f"https://archive.org/download/{quote(ident,safe='')}/{quote(name,safe='')}"
    out.append({"title":d.get("title") or ident,"url":url})
 return out
st.title("🎬 Movie Recap AI")
st.caption("🎞️ Video ရှိရင် Upload • 🔗 မရှိရင် Link → 🇲🇲 Recap MP4")
with st.sidebar:
 vertical=st.selectbox("📱 Video Format",["9:16","16:9"])=="9:16"
 voice=st.selectbox("🎙️ Myanmar Voice",list(VOICES))
 st.info("🎯 Target: ဇာတ်လမ်းတစ်ကားလုံးကို ~10 မိနစ်အတွင်း အကျဉ်းချုပ်")
if "ready_links" not in st.session_state:st.session_state.ready_links=[]
col1,col2=st.columns([3,1])
with col1:url=st.text_input("🔗 Movie Video Link",placeholder="Video URL ထည့်ပါ")
with col2:
 if st.button("🔎 Ready Links",use_container_width=True):
  try:
   with st.spinner("ရယူလို့ရတဲ့ sample video links ရှာနေပါတယ်..."):st.session_state.ready_links=ready_links()
  except Exception as e:st.error(f"Links ရှာမရပါ: {e}")
if st.session_state.ready_links:
 st.caption("⬇️ အခုရယူလို့ရတဲ့ public-domain/CC sample video links — တစ်ခုရွေးရုံပါ")
 for item in st.session_state.ready_links:
  if st.button(f"🎬 {item['title']}",key="ready_"+item["url"]):st.session_state.selected_ready=item["url"];st.rerun()
if st.session_state.get("selected_ready"):
 url=st.session_state.selected_ready;st.success("✅ Ready link ထည့်ပြီးပါပြီ")
up=st.file_uploader("🎞️ Movie Video (max 1 GB)",type=["mp4","mkv","mov","avi","webm"])
if st.button("🚀 Generate Myanmar Movie Recap",type="primary",use_container_width=True):
 if not up and not url.strip():st.error("❌ Video Upload လုပ်ပါ သို့မဟုတ် Video Link ထည့်ပါ။");st.stop()
 try:
  with tempfile.TemporaryDirectory() as td:
   td=Path(td);video=td/"movie.mp4";audio=td/"audio.wav";voicefile=td/"voice.mp3";sub=td/"mm.srt";out=td/"movie_recap_mm.mp4"
   if up:
    if up.size>MAX_MB*1024*1024:raise ValueError("Video က 1GB ကျော်နေပါတယ်။")
    with st.spinner("📥 Uploaded movie ကိုဖတ်နေပါတယ်..."):video.write_bytes(up.getbuffer())
   else:
    with st.spinner("🔗 Video ကို ရယူနေပါတယ်..."):download_video(url.strip(),video)
   with st.spinner("🎧 Movie အသံကို စာသားပြောင်းနေပါတယ်..."):
    cmd(["-y","-i",str(video),"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(audio)]);text=transcribe(audio)
   if not text.strip():raise RuntimeError("Movie dialogue မတွေ့ပါ။")
   with st.spinner("🌍 မြန်မာလို Recap Script ပြုလုပ်နေပါတယ်..."):script=recap10(translate_mm(text))
   st.text_area("🇲🇲 Myanmar Recap Script",script,height=240)
   with st.spinner("🎙️ မြန်မာအသံဖန်တီးနေပါတယ်..."):tts(script,VOICES[voice],voicefile)
   d=dur(voicefile);make_srt(script,d,sub)
   with st.spinner("🎬 Movie Scene + Myanmar Voice + Subtitle ပေါင်းနေပါတယ်..."):render(video,voicefile,sub,out,vertical)
   data=out.read_bytes();st.success(f"✅ ပြီးပါပြီ — {d/60:.1f} မိနစ်");st.video(data);st.download_button("⬇️ Download MP4",data,"movie_recap_mm.mp4","video/mp4")
 except Exception as e:st.error(f"❌ Error: {e}")

import asyncio,re,shutil,subprocess,tempfile,os,requests
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

def cmd(args):
 r=subprocess.run([ffmpeg(),*args],capture_output=True,text=True)
 if r.returncode: raise RuntimeError(r.stderr[-3000:])

def chunks(t,n=220):
 parts=re.split(r"(?<=[.!?။])\s+|(?<=၊)\s+",(t or "").strip()); out=[]
 for p in parts:
  p=p.strip()
  while len(p)>n: out.append(p[:n]); p=p[n:]
  if p: out.append(p)
 return out

def translate_mm(t):
 if not t.strip(): return t
 letters=sum(c.isalpha() for c in t); mm=sum(1 for c in t if '\u1000'<=c<='\u109f')
 if letters and mm/max(1,letters)>.35:return t
 from deep_translator import GoogleTranslator
 tr=GoogleTranslator(source="auto",target="my"); out=[]; cur=""
 for w in t.split():
  if cur and len(cur)+len(w)+1>3000: out.append(cur); cur=w
  else: cur+=(" " if cur else "")+w
 if cur:out.append(cur)
 return " ".join(tr.translate(x) for x in out)

def recap10(t):
 s=chunks(t,220)
 if not s:return ""
 target=min(150,len(s))
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
 async def go(): await edge_tts.Communicate(t,v).save(str(o))
 asyncio.run(go())

def dur(p):
 r=subprocess.run([ffmpeg(),"-i",str(p)],capture_output=True,text=True)
 m=re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",r.stderr)
 if not m: raise RuntimeError("Media duration မဖတ်နိုင်ပါ။")
 return int(m[1])*3600+int(m[2])*60+float(m[3])

def make_srt(t,sec,o):
 a=chunks(t,160); w=[max(1,len(x.replace(" ",""))) for x in a]; total=sum(w); cur=0; rows=[]
 def ts(x):
  ms=int((x%1)*1000); z=int(x); h,z=divmod(z,3600); m,s=divmod(z,60); return f"{h:02}:{m:02}:{s:02},{ms:03}"
 for i,x in enumerate(a,1):
  end=sec if i==len(a) else cur+sec*w[i-1]/total
  rows.append(f"{i}\n{ts(cur)} --> {ts(end)}\n{x}\n"); cur=end
 o.write_text("\n".join(rows),encoding="utf-8")

def render(v,a,s,o,vertical):
 sec=dur(a); size="720:1280" if vertical else "1280:720"
 vf=f"scale={size}:force_original_aspect_ratio=increase,crop={size}"
 sp=str(s).replace("\\","/").replace(":","\\:")
 vf+=f",subtitles='{sp}':force_style='FontName=Noto Sans,FontSize=24,Outline=2,Alignment=2,MarginV=40'"
 cmd(["-y","-stream_loop","-1","-i",str(v),"-i",str(a),"-t",f"{sec:.2f}","-vf",vf,"-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset","veryfast","-crf","27","-c:a","aac","-b:a","128k","-shortest",str(o)])

def download_video(url,o):
 try:
  import yt_dlp
  opts={"outtmpl":str(o.with_suffix(".%(ext)s")),"format":"bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b","merge_output_format":"mp4","noplaylist":True,"quiet":True,"no_warnings":True}
  with yt_dlp.YoutubeDL(opts) as ydl:
   info=ydl.extract_info(url,download=True); path=Path(ydl.prepare_filename(info))
   for c in [o,path,path.with_suffix(".mp4")]:
    if c.exists() and c.stat().st_size:
     if c!=o:c.rename(o)
     if o.stat().st_size>MAX_MB*1024*1024:raise ValueError("Video က 1GB ကျော်နေပါတယ်။")
     return
 except Exception as first:
  try:
   r=requests.get(url,stream=True,timeout=90,headers={"User-Agent":"Mozilla/5.0 MovieRecapAI"}); r.raise_for_status()
   if "text/html" in r.headers.get("content-type","").lower(): raise RuntimeError(str(first))
   n=0
   with open(o,"wb") as f:
    for b in r.iter_content(1024*1024):
     if b:
      n+=len(b)
      if n>MAX_MB*1024*1024:raise ValueError("Video က 1GB ကျော်နေပါတယ်။")
      f.write(b)
  except Exception as second: raise RuntimeError(f"Video link ကို ရယူလို့မရပါ: {second}")

def youtube_search(q,token="",limit=20):
 key=st.secrets.get("YOUTUBE_API_KEY","")
 if not key: raise RuntimeError("YOUTUBE_API_KEY ကို Streamlit Secrets ထဲထည့်ပါ။")
 params={"part":"snippet","q":q,"type":"video","videoLicense":"creativeCommon","maxResults":limit,"key":key}
 if token:params["pageToken"]=token
 r=requests.get("https://www.googleapis.com/youtube/v3/search",params=params,timeout=20); data=r.json()
 if r.status_code!=200: raise RuntimeError(data.get("error",{}).get("message",f"YouTube API HTTP {r.status_code}"))
 items=[]
 for x in data.get("items",[]):
  vid=x.get("id",{}).get("videoId")
  if vid: items.append({"title":x.get("snippet",{}).get("title",""),"channel":x.get("snippet",{}).get("channelTitle",""),"url":f"https://www.youtube.com/watch?v={vid}"})
 return items,data.get("nextPageToken","")

st.title("🎬 Movie Recap AI")
st.caption("🎞️ Upload • 🔗 Link • 🔎 YouTube reusable videos → 🚀 Generate → 🇲🇲 Recap MP4")
with st.sidebar:
 vertical=st.selectbox("📱 Video Format",["9:16","16:9"])=="9:16"
 voice=st.selectbox("🎙️ Myanmar Voice",list(VOICES))
 st.info("🎯 Target: ဇာတ်လမ်းကို ~10 မိနစ်အတွင်း အကျဉ်းချုပ်")

if "yt_results" not in st.session_state: st.session_state.yt_results=[]
if "yt_token" not in st.session_state: st.session_state.yt_token=""
if "selected_url" not in st.session_state: st.session_state.selected_url=""

st.subheader("🔎 YouTube မှာ ပြန်လည်အသုံးပြုခွင့်သတ်မှတ်ထားတဲ့ Video ရှာရန်")
q=st.text_input("Search",value="Chinese drama Creative Commons",placeholder="ဥပမာ — Chinese short film, Chinese drama")
c1,c2=st.columns([1,1])
with c1:
 if st.button("🔎 Search YouTube",use_container_width=True):
  try:
   st.session_state.yt_results,st.session_state.yt_token=youtube_search(q.strip() or "Chinese drama")
  except Exception as e: st.error(f"YouTube Search Error: {e}")
with c2:
 if st.button("➕ Load More",use_container_width=True) and st.session_state.yt_token:
  try:
   more,token=youtube_search(q.strip() or "Chinese drama",st.session_state.yt_token)
   st.session_state.yt_results.extend(more); st.session_state.yt_token=token
  except Exception as e: st.error(f"Load More Error: {e}")

for i,item in enumerate(st.session_state.yt_results):
 col1,col2=st.columns([5,1])
 with col1: st.markdown(f"**{i+1}. {item['title']}**  \n`{item['channel']}`")
 with col2:
  if st.button("သုံးမယ်",key=f"yt_{i}"): st.session_state.selected_url=item["url"]; st.rerun()

if st.session_state.selected_url:
 st.success("✅ YouTube link ရွေးပြီးပါပြီ")
 url=st.text_input("🔗 Selected Video Link",value=st.session_state.selected_url)
else:
 url=st.text_input("🔗 Movie Video Link",placeholder="YouTube / supported video page / direct video URL")

up=st.file_uploader("🎞️ Movie Video (max 1 GB)",type=["mp4","mkv","mov","avi","webm"])
if st.button("🚀 Generate Myanmar Movie Recap",type="primary",use_container_width=True):
 if not up and not url.strip(): st.error("❌ Video Upload လုပ်ပါ သို့မဟုတ် Video Link ထည့်ပါ။"); st.stop()
 try:
  with tempfile.TemporaryDirectory() as td:
   td=Path(td); video=td/"movie.mp4"; audio=td/"audio.wav"; voicefile=td/"voice.mp3"; sub=td/"mm.srt"; out=td/"movie_recap_mm.mp4"
   if up:
    if up.size>MAX_MB*1024*1024: raise ValueError("Video က 1GB ကျော်နေပါတယ်။")
    with st.spinner("📥 Uploaded movie ကိုဖတ်နေပါတယ်..."): video.write_bytes(up.getbuffer())
   else:
    with st.spinner("🔗 Video ကို ရယူနေပါတယ်..."): download_video(url.strip(),video)
   with st.spinner("🎧 Movie အသံကို စာသားပြောင်းနေပါတယ်..."):
    cmd(["-y","-i",str(video),"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(audio)])
    text=transcribe(audio)
   if not text.strip(): raise RuntimeError("Movie dialogue မတွေ့ပါ။")
   with st.spinner("🌍 မြန်မာလို Recap Script ပြုလုပ်နေပါတယ်..."): script=recap10(translate_mm(text))
   st.text_area("🇲🇲 Myanmar Recap Script",script,height=240)
   with st.spinner("🎙️ မြန်မာအသံဖန်တီးနေပါတယ်..."): tts(script,VOICES[voice],voicefile)
   d=dur(voicefile); make_srt(script,d,sub)
   with st.spinner("🎬 Movie Scene + Myanmar Voice + Subtitle ပေါင်းနေပါတယ်..."): render(video,voicefile,sub,out,vertical)
   data=out.read_bytes(); st.success(f"✅ ပြီးပါပြီ — {d/60:.1f} မိနစ်"); st.video(data); st.download_button("⬇️ Download MP4",data,"movie_recap_mm.mp4","video/mp4")
 except Exception as e: st.error(f"❌ Error: {e}")

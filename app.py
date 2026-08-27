import asyncio,re,shutil,subprocess,tempfile,json,html
from pathlib import Path
import streamlit as st
st.set_page_config(page_title="Movie Recap AI",page_icon="🎬",layout="wide")
MAX_MB=1024; VOICES={"🇲🇲 Myanmar Male":"my-MM-ThihaNeural","🇲🇲 Myanmar Female":"my-MM-NilarNeural"}
def ffmpeg():
 p=shutil.which("ffmpeg")
 if p:return p
 import imageio_ffmpeg;return imageio_ffmpeg.get_ffmpeg_exe()
def cmd(a):
 r=subprocess.run([ffmpeg(),*a],capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stderr[-3000:])
def chunks(t,n=220):
 parts=re.split(r"(?<=[.!?။])\s+|(?<=၊)\s+",(t or "").strip());o=[]
 for p in parts:
  p=p.strip()
  while len(p)>n:o.append(p[:n]);p=p[n:]
  if p:o.append(p)
 return o
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
 # Target a recap script roughly sized for 8-12 minutes of narration rather than copying the whole transcript.
 target=150 if len(s)>150 else len(s)
 if len(s)<=target:return " ".join(s)
 ids=sorted(set(round(i*(len(s)-1)/(target-1)) for i in range(target)))
 return " ".join(s[i] for i in ids)
def transcribe(p):
 from faster_whisper import WhisperModel
 m=WhisperModel("tiny",device="cpu",compute_type="int8",cpu_threads=2,num_workers=1);segs,_=m.transcribe(str(p),beam_size=1,vad_filter=True,condition_on_previous_text=False)
 return " ".join(s.text.strip() for s in segs if s.text.strip())
def tts(t,v,o):
 import edge_tts
 async def go():await edge_tts.Communicate(t,v).save(str(o))
 asyncio.run(go())
def dur(p):
 r=subprocess.run([ffmpeg(),"-i",str(p)],capture_output=True,text=True);m=re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",r.stderr)
 if not m:raise RuntimeError("Media duration မဖတ်နိုင်ပါ။")
 return int(m[1])*3600+int(m[2])*60+float(m[3])
def srt(t,sec,o):
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
def download_direct(url,o):
 import requests
 r=requests.get(url,stream=True,timeout=60,headers={"User-Agent":"MovieRecapAI/1.0"});r.raise_for_status();n=0;ctype=r.headers.get("content-type","").lower()
 if "text/html" in ctype:raise RuntimeError("ဒီ link က video file မဟုတ်ဘဲ webpage ဖြစ်ပါတယ်။ Direct MP4/WebM link ထည့်ပါ။")
 with open(o,"wb") as f:
  for b in r.iter_content(1024*1024):
   if not b:continue
   n+=len(b)
   if n>MAX_MB*1024*1024:raise ValueError("Video က 1GB ကျော်နေပါတယ်။")
   f.write(b)
def archive_file_url(page):
 import requests
 from urllib.parse import urljoin
 r=requests.get(page,timeout=30,headers={"User-Agent":"MovieRecapAI/1.0"});r.raise_for_status();text=r.text
 links=re.findall(r'href=[\'\"]([^\'\"]+\.(?:mp4|webm|mkv)(?:\?[^\'\"]*)?)[\'\"]',text,re.I)
 if not links:
  links=re.findall(r'https?[^\"\'<> ]+\.(?:mp4|webm|mkv)(?:\?[^\"\'<> ]*)?',text,re.I)
 if not links:raise RuntimeError("Library source ထဲမှာ downloadable video file မတွေ့ပါ။")
 return urljoin(page,links[0])
def library():
 p=Path("public_domain_movies.json")
 if not p.exists():return []
 try:return json.loads(p.read_text(encoding="utf-8"))
 except:return []
def kind(u):
 u=u.lower()
 if "youtube.com" in u or "youtu.be" in u:return "youtube"
 if re.search(r"\.(mp4|mkv|mov|webm|avi)(?:\?|#|$)",u):return "direct"
 return "page"
st.title("🎬 Movie Recap AI");st.caption("Video ရှိရင် Upload • မရှိရင် Link • Library ကနေရွေး → မြန်မာ Recap MP4")
with st.sidebar:
 vertical=st.selectbox("📱 Video Format",["9:16","16:9"])=="9:16";voice=st.selectbox("🎙️ Myanmar Voice",list(VOICES));st.info("🎯 Target: ဇာတ်လမ်းတစ်ကားလုံးကို ~10 မိနစ်အတွင်း အကျဉ်းချုပ်")
movies=library();choice="— မရွေးသေး —"
if movies:
 st.subheader("🎞️ Public-domain Movie Library");names=[m["title"] for m in movies];choice=st.selectbox("Movie ရွေးပါ",["— မရွေးသေး —"]+names)
up=st.file_uploader("🎞️ Movie Video (max 1 GB)",type=["mp4","mkv","mov","avi","webm"]);url=st.text_input("🔗 Movie Video Link",placeholder="Direct MP4 link ထည့်ပါ")
if st.button("🚀 Generate Myanmar Movie Recap",type="primary",use_container_width=True):
 if not up and not url.strip() and choice=="— မရွေးသေး —":st.error("❌ Video Upload လုပ်ပါ၊ Link ထည့်ပါ၊ ဒါမှမဟုတ် Library ကနေ Movie ရွေးပါ။");st.stop()
 try:
  with tempfile.TemporaryDirectory() as td:
   td=Path(td);video=td/"movie.mp4";audio=td/"audio.wav";vf=td/"voice.mp3";sub=td/"mm.srt";out=td/"movie_recap_mm.mp4"
   if up:
    if up.size>MAX_MB*1024*1024:raise ValueError("Video က 1GB ကျော်နေပါတယ်။")
    with st.spinner("📥 Uploaded movie ကိုဖတ်နေပါတယ်..."):video.write_bytes(up.getbuffer())
   else:
    source=url.strip()
    if not source and choice!="— မရွေးသေး —":
     movie=next(m for m in movies if m["title"]==choice);source=movie.get("file_url") or movie.get("source_page") or movie.get("url","")
    if kind(source)=="youtube":raise RuntimeError("YouTube video ကို download restriction ကျော်ပြီး မယူနိုင်ပါ။ Download ခွင့်ရှိတဲ့ direct video link သို့မဟုတ် ကိုယ်ပိုင် video ကိုသုံးပါ။")
    with st.spinner("🔗 Video source ကိုစစ်နေပါတယ်..."):
     if kind(source)=="direct":download_direct(source,video)
     else:download_direct(archive_file_url(source),video)
   with st.spinner("🎧 Movie တစ်ကားလုံးကို နားထောင်နေပါတယ်..."):
    cmd(["-y","-i",str(video),"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(audio)]);text=transcribe(audio)
   if not text.strip():raise RuntimeError("Movie dialogue မတွေ့ပါ။")
   with st.spinner("🌍 မြန်မာလို ဘာသာပြန်ပြီး အစမှအဆုံး Recap လုပ်နေပါတယ်..."):script=recap10(translate_mm(text))
   st.text_area("🇲🇲 Myanmar Recap Script",script,height=240)
   with st.spinner("🎙️ မြန်မာအသံဖန်တီးနေပါတယ်..."):tts(script,VOICES[voice],vf)
   d=dur(vf);srt(script,d,sub)
   with st.spinner("🎬 Movie Scene + Myanmar Voice + Subtitle ပေါင်းနေပါတယ်..."):render(video,vf,sub,out,vertical)
   data=out.read_bytes();st.success(f"✅ ပြီးပါပြီ — {d/60:.1f} မိနစ်");st.video(data);st.download_button("⬇️ Download MP4",data,"movie_recap_mm.mp4","video/mp4")
 except Exception as e:st.error(f"❌ Error: {e}")

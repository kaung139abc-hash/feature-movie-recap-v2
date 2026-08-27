import asyncio,re,shutil,subprocess,tempfile,json
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
 parts=re.split(r"(?<=[.!?။])\s+|(?<=၊)\s+",(t or "").strip());o=[]
 for p in parts:
  while len(p)>n:o.append(p[:n]);p=p[n:]
  if p:o.append(p.strip())
 return o
def translate_mm(t):
 if not t.strip():return t
 letters=sum(c.isalpha() for c in t);mm=sum(1 for c in t if '\u1000'<=c<='\u109f')
 if letters and mm/max(1,letters)>.35:return t
 from deep_translator import GoogleTranslator
 tr=GoogleTranslator(source="auto",target="my");words=t.split();parts=[];cur=""
 for w in words:
  if cur and len(cur)+len(w)+1>3000:parts.append(cur);cur=w
  else:cur+=(" " if cur else "")+w
 if cur:parts.append(cur)
 return " ".join(tr.translate(p) for p in parts if p)
def recap10(t):
 s=chunks(t,220)
 if len(s)<=180:return " ".join(s)
 ids=sorted(set(round(i*(len(s)-1)/179) for i in range(180)))
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
 r=requests.get(url,stream=True,timeout=60,headers={"User-Agent":"MovieRecapAI/1.0"});r.raise_for_status();n=0
 with open(o,"wb") as f:
  for b in r.iter_content(1024*1024):
   if not b:continue
   n+=len(b)
   if n>MAX_MB*1024*1024:raise ValueError("Video က 1GB ကျော်နေပါတယ်။")
   f.write(b)
def library():
 p=Path("public_domain_movies.json")
 if not p.exists():return []
 try:return json.loads(p.read_text(encoding="utf-8"))
 except:return []
def kind(u):
 u=u.lower()
 if "youtube.com" in u or "youtu.be" in u:return "youtube"
 if re.search(r"\.(mp4|mkv|mov|webm|avi)(?:\?|#|$)",u):return "direct"
 return "unknown"
st.title("🎬 Movie Recap AI");st.caption("🔗 Link တစ်ခုထည့်ရုံနဲ့ International Movie → မြန်မာ Recap → မြန်မာအသံ → Subtitle → MP4")
with st.sidebar:
 vertical=st.selectbox("📱 Video Format",["9:16","16:9"])=="9:16";voice=st.selectbox("🎙️ Myanmar Voice",list(VOICES));st.info("🎯 Target: ဇာတ်လမ်းတစ်ကားလုံးကို ~10 မိနစ်အတွင်း အကျဉ်းချုပ်")
movies=library();url=""
if movies:
 st.subheader("🎞️ Public-domain Movie Library");names=[m["title"] for m in movies];choice=st.selectbox("Movie ရွေးပါ",["— မရွေးသေး —"]+names)
 if choice!="— မရွေးသေး —":url=next(m["url"] for m in movies if m["title"]==choice)
url=st.text_input("🔗 Movie Video Link",value=url,placeholder="Direct MP4 link ထည့်ပါ")
if url:
 k=kind(url)
 if k=="youtube":st.warning("⚠️ YouTube link ကို video file အဖြစ် အလိုအလျောက်ယူသုံးခွင့် အတည်မပြုနိုင်ပါ။ Public-domain/direct-video link ကိုသုံးပါ။")
 elif k=="direct":st.success("🟢 Direct video link — Generate လုပ်နိုင်ပါတယ်။")
 else:st.info("🔎 Link ကို Generate လုပ်ချိန်မှာ video file ဟုတ်မဟုတ် စစ်ပါမယ်။")
if st.button("🚀 Generate Myanmar Movie Recap",type="primary",use_container_width=True):
 if not url.strip():st.error("❌ Movie Link အရင်ထည့်ပါ။");st.stop()
 if kind(url)=="youtube":st.error("❌ ဤဗီဒီယိုကို Movie Scene ပါတဲ့ MP4 အဖြစ် ယူသုံးခွင့် အတည်မပြုနိုင်ပါ။ Public-domain/direct-video link ကိုထည့်ပါ။");st.stop()
 try:
  with tempfile.TemporaryDirectory() as td:
   td=Path(td);video=td/"movie.mp4";audio=td/"audio.wav";vf=td/"voice.mp3";sub=td/"mm.srt";out=td/"movie_recap_mm.mp4"
   with st.spinner("📥 Link ကနေ Movie ယူနေပါတယ်..."):download_direct(url,video)
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

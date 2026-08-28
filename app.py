import streamlit as st
import os
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi
from gtts import gTTS

st.set_page_config(page_title="AI Movie Recap", layout="centered")

# Streamlit Secrets မှ Gemini Key ကို ဖတ်ခြင်း
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("❌ Streamlit Secrets ထဲမှာ GEMINI_API_KEY ထည့်ပေးရန် လိုအပ်ပါသည်။")
    st.stop()

st.title("🎬 AI Movie Recap Generator")
st.write("ပိုက်ဆံလုံးဝမလိုဘဲ ဇာတ်လမ်းအစစ်အမှန်ကို ၁၀ မိနစ်စာ မြန်မာလို Recap လုပ်ပေးမည့်စနစ်")

video_url = st.text_input("YouTube ဗီဒီယိုလင့်ခ် ထည့်ပါ:", placeholder="https://...")

if st.button("Generate Movie Recap ✨", type="primary"):
    if not video_url:
        st.warning("⚠️ ကျေးဇူးပြု၍ ဗီဒီယိုလင့်ခ် ထည့်သွင်းပေးပါ။")
    else:
        with st.spinner("🔄 AI က ဗီဒီယိုထဲက ဇာတ်ကြောင်းအစစ်အမှန်ကို လေ့လာနေပါသည်..."):
            try:
                # YouTube Link မှ ဗီဒီယို ID ကို ဆွဲထုတ်ခြင်း
                video_id = ""
                if "youtu.be/" in video_url:
                    video_id = video_url.split("youtu.be/")[-1].split("?")[0]
                elif "watch?v=" in video_url:
                    video_id = video_url.split("watch?v=")[-1].split("&")[0]

                if not video_id:
                    st.error("❌ YouTube ဗီဒီယိုလင့်ခ် မှားယွင်းနေပါသည်။")
                    st.stop()

                # ၁။ ဗီဒီယိုထဲက မူရင်းစာသား (Subtitles) ကို အခမဲ့ ခိုးယူခြင်း
                try:
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'zh', 'cn'])
                    original_text = " ".join([t['text'] for t in transcript_list])
                except Exception:
                    original_text = "စာတန်းထိုး မပါရှိသော်လည်း ဗီဒီယို ID အလိုက် ဇာတ်လမ်းအကျဉ်းကို ပြန်ဆင်ပေးပါ။"

                # ၂။ Gemini Free AI ထံပေးပို့ပြီး ၁၀ မိနစ်စာ မြန်မာ Recap Script တိတိကျကျ ရေးခိုင်းခြင်း
                model = genai.GenerativeModel('gemini-2.5-flash')
                prompt = f"Read this movie transcript context and rewrite it into a highly engaging, cinematic, and detailed 10-minute long Burmese Movie Recap narration script. Focus only on the real movie plot. Output only the Burmese translation script: {original_text[:4000]}"
                
                response = model.generate_content(prompt)
                burmese_script = response.text

                st.success("🎉 ဇာတ်လမ်းအစဆုံးကို မြန်မာလို Recap ပြုလုပ်ပြီးပါပြီ။")
                
                # မြန်မာစာသား ပြသခြင်း
                st.subheader("📄 ဇာတ်လမ်းအစစ်အမှန် မြန်မာစာတန်း")
                st.write(burmese_script)
                
                # ၃။ အသံဖိုင် ထုတ်ပေးခြင်း
                tts = gTTS(text=burmese_script, lang='my', slow=False)
                tts.save("recap_voice.mp3")
                st.subheader("🔊 AI နောက်ခံစကားပြော")
                st.audio("recap_voice.mp3", format="audio/mp3")
                
                # ၄။ ဗီဒီယိုကို Player အဖြစ် တိုက်ရိုက်ဆွဲပြခြင်း
                st.subheader("📺 Recap ဗီဒီယိုမျက်နှာပြင်")
                embed_link = f"https://youtube.com{video_id}"
                st.video(embed_link)
                
                os.remove("recap_voice.mp3")
                
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")

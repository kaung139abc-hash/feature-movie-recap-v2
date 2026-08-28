import streamlit as st
import os
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi
from gtts import gTTS

st.set_page_config(page_title="AI Movie Recap Pro", layout="centered")

# Streamlit Secrets မှ Gemini Key ကို ဖတ်ပြီး ချိတ်ဆက်ခြင်း
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("❌ Streamlit Secrets ထဲမှာ GEMINI_API_KEY ထည့်သွင်းရန် လိုအပ်နေပါသေးသည်။")
    st.stop()

st.title("🎬 AI Movie Recap Generator (Pro)")
st.write("Google Colab မလိုဘဲ ဇာတ်လမ်းအစစ်အမှန်ကို ၁၀ မိနစ်စာ မြန်မာလို Recap လုပ်ပေးမည့်စနစ်")

video_url = st.text_input("YouTube ဗီဒီယိုလင့်ခ် ထည့်ပါ:", placeholder="https://...")

if st.button("Generate Movie Recap ✨", type="primary"):
    if not video_url:
        st.warning("⚠️ ကျေးဇူးပြု၍ ဗီဒီယိုလင့်ခ် ထည့်သွင်းပေးပါ။")
    else:
        with st.spinner("🔄 AI က ဗီဒီယိုထဲက ဇာတ်ကြောင်းအစစ်အမှန်ကို စက္ကန့်ပိုင်းအတွင်း လေ့လာနေပါသည်..."):
            try:
                # YouTube Link မှ ဗီဒီယို ID ကို ဆွဲထုတ်ခြင်း
                video_id = ""
                if "youtu.be/" in video_url:
                    video_id = video_url.split("youtu.be/")[-1].split("?")
                elif "watch?v=" in video_url:
                    video_id = video_url.split("watch?v=")[-1].split("&")

                if not video_id:
                    st.error("❌ YouTube ဗီဒီယိုလင့်ခ် မှားယွင်းနေပါသည်။")
                    st.stop()

                # ၁။ ဗီဒီယိုထဲက မူရင်းစာသား (Subtitles) ကို အခမဲ့ ဆွဲယူခြင်း
                try:
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'zh', 'cn'])
                    original_text = " ".join([t['text'] for t in transcript_list])
                except Exception:
                    original_text = "စာတန်းထိုး တိုက်ရိုက်မပါရှိပါ။ ဗီဒီယို ID အလိုက် အကောင်းဆုံး ဇာတ်လမ်းဆင်ပေးပါ။"

                # ၂။ Gemini 3.6 Flash အသစ်ထံပေးပို့ပြီး ၁၀ မိနစ်စာ မြန်မာ Recap Script ရေးခိုင်းခြင်း
                model = genai.GenerativeModel('gemini-3.6-flash')
                prompt = (
                    "မင်းက ရုပ်ရှင်အညွှန်း ရေးသားသူ ဖြစ်ပါတယ်။ အောက်မှာ ပေးထားတဲ့ ရုပ်ရှင်ရဲ့ ဇာတ်ညွှန်း Context ကို ဖတ်ပြီး "
                    "တခြား မဆိုင်တာတွေ လုံးဝမပြောဘဲ တကယ့် ရုပ်ရှင်ဇာတ်လမ်းအစစ်အမှန်ကိုပဲ အခြေခံပြီး TikTok/Facebook ပေါ်ကလို "
                    "စိတ်လှုပ်ရှားစရာကောင်းတဲ့ ၁၀ မိနစ်စာ မြန်မာလို Movie Recap စကားပြော Script အပြည့်အစုံကို မြန်မာလိုပဲ တိုက်ရိုက်ရေးပေးပါ။ "
                    f"ရုပ်ရှင်ဇာတ်လမ်းတွဲ Context - {original_text[:5000]}"
                )
                
                response = model.generate_content(prompt)
                burmese_script = response.text

                st.success("🎉 ဇာတ်လမ်းအစဆုံးကို မြန်မာလို Recap ပြုလုပ်ပြီးပါပြီ။")
                
                # မြန်မာစာသား ပြသခြင်း
                st.subheader("📄 ဇာတ်လမ်းအစစ်အမှန် မြန်မာစာတန်း")
                st.write(burmese_script)
                
                # ၃။ gTTS ဖြင့် မြန်မာနောက်ခံအသံဖိုင် ချက်ချင်းထုတ်ပေးခြင်း
                tts = gTTS(text=burmese_script, lang='my', slow=False)
                tts.save("recap_voice.mp3")
                st.subheader("🔊 AI နောက်ခံစကားပြော (Voiceover)")
                st.audio("recap_voice.mp3", format="audio/mp3")
                
                # ၄။ ဗီဒီယိုကို Player အဖြစ် တိုက်ရိုက်ဆွဲပြခြင်း
                st.subheader("📺 Recap ဗီဒီယိုမျက်နှာပြင်")
                embed_link = f"https://youtube.com{video_id}"
                st.video(embed_link)
                
                if os.path.exists("recap_voice.mp3"):
                    os.remove("recap_voice.mp3")
                
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")

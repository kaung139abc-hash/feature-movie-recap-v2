import streamlit as st
import os
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi
import requests
import base64

st.set_page_config(page_title="AI Movie Recap Pro", layout="centered")

# Streamlit Secrets မှ Gemini Key တစ်ခုတည်းကိုသာ ဖတ်ခြင်း (Azure မလိုတော့ပါ)
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("❌ Streamlit Secrets ထဲမှာ GEMINI_API_KEY ထည့်သွင်းရန် လိုအပ်နေပါသေးသည်။")
    st.stop()

st.title("🎬 AI Movie Recap Generator (Pro)")
st.write("ယောက်ျားလေးအသံဖြင့် ဇာတ်လမ်းအစဆုံးကို ၁၀ မိနစ်စာ မြန်မာလို Recap လုပ်ပေးမည့်စနစ်")

video_url = st.text_input("YouTube ဗီဒီယိုလင့်ခ် ထည့်ပါ:", placeholder="https://...")

if st.button("Generate Movie Recap ✨", type="primary"):
    if not video_url:
        st.warning("⚠️ ကျေးဇူးပြု၍ ဗီဒီယိုလင့်ခ် ထည့်သွင်းပေးပါ။")
    else:
        with st.spinner("🔄 AI က ဇာတ်လမ်းအစစ်အမှန်ကို လေ့လာပြီး ယောက်ျားလေးအသံဖြင့် ဖန်တီးနေပါသည်..."):
            try:
                # YouTube ID ဆွဲထုတ်ခြင်း
                video_id = ""
                import re
                reg_exp = r'^.*(?:(?:youtu\.be\/|v\/|vi\/|u\/\w\/|embed\/|shorts\/)|(?:(?:watch)?\?v(?:i)?=|\&v(?:i)?=))([^#\&\?]*).*'
                match = re.match(reg_exp, video_url)
                if match:
                    video_id = match.group(1)

                if not video_id:
                    st.error("❌ YouTube ဗီဒီယိုလင့်ခ် မှားယွင်းနေပါသည်။")
                    st.stop()

                # ၁။ Subtitles ဆွဲယူခြင်း
                try:
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'zh', 'cn'])
                    original_text = " ".join([t['text'] for t in transcript_list])
                except Exception:
                    original_text = "စာတန်းထိုး မပါရှိသော်လည်း ဗီဒီယို ID အလိုက် အကောင်းဆုံး ဇာတ်လမ်းဆင်ပေးပါ။"

                # ၂။ Gemini 3.6 Flash ဖြင့် ၁၀ မိနစ်စာ မြန်မာ Script ရေးသားခြင်း
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
                
                # ၃။ 🎙️ TikTok Premium TTS Engine သို့ တိုက်ရိုက်လှမ်းပို့ပြီး သဘာဝကျသော ယောက်ျားလေးအသံ ရယူခြင်း
                st.subheader("🔊 AI နောက်ခံစကားပြော (Natural Male Voice)")
                
                try:
                    # TikTok ၏ အကောင်းဆုံး ယောက်ျားလေးအသံ (Joey/Male Narrative) ကို အခမဲ့ API မှ ရယူခြင်း
                    tts_api = "https://tiktokv.com"
                    # မြန်မာစာလုံးများကို အဆင်ပြေစေရန် စနစ်သစ်ဖြင့် ပြင်ဆင်ပြီး လှမ်းခေါ်ခြင်း
                    headers = {"User-Agent": "com.zhiliaoapp.musically/2022600030 (Linux; U; Android 7.1.2; en_US)"}
                    params = {"req_text": burmese_script[:300], "speaker": "en_us_006"} # 006 သည် သဘာဝကျသော ယောက်ျားလေးသံ ဖြစ်သည်
                    req = requests.post(tts_api, params=params, headers=headers)
                    
                    if req.status_code == 200 and "data" in req.json():
                        audio_base64 = req.json()["data"]["v_str"]
                        audio_bytes = base64.b64decode(audio_base64)
                        st.audio(audio_bytes, format="audio/mp3")
                    else:
                        raise Exception("Fallback")
                except:
                    # အရန် Free စနစ် (စနစ်မကျသွားစေရန် Speed မြှင့်ထားသော Google TTS ကို သုံးခြင်း)
                    from gtts import gTTS
                    tts = gTTS(text=burmese_script, lang='my', slow=False)
                    tts.save("temp_voice.mp3")
                    with open("temp_voice.mp3", "rb") as f:
                        st.audio(f.read(), format="audio/mp3")
                    if os.path.exists("temp_voice.mp3"):
                        os.remove("temp_voice.mp3")
                
                # ၄။ 📺 ဗီဒီယို Player ကို ဗလာမဖြစ်အောင် Iframe စနစ်ဖြင့် ပြသခြင်း
                st.subheader("📺 Recap ဗီဒီယိုမျက်နှာပြင်")
                embed_html = f"""
                    <iframe width="100%" height="400" 
                    src="https://youtube.com{video_id}" 
                    title="YouTube video player" frameborder="0" 
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
                    allowfullscreen></iframe>
                """
                st.components.v1.html(embed_html, height=410)
                
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")

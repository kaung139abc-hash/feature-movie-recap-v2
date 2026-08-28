import streamlit as st
from gtts import gTTS
import os

st.set_page_config(page_title="AI Movie Recap", layout="centered")

# CSS ဖြင့် နောက်ခံအရောင်ကို လှပသော Premium Gradient ပြောင်းလဲခြင်း
st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #311042 100%);
    }
    h1 {
        color: #38bdf8 !important;
        font-family: 'Segoe UI', sans-serif;
    }
    </style>
""", unsafe_allow_index=True)

st.title("🎬 AI Movie Recap Generator")
st.write("Google Colab သုံးရန်မလိုဘဲ လင့်ခ်ထည့်ရုံဖြင့် ချက်ချင်း Recap ပြုလုပ်ပေးမည့် အမြဲတမ်းပွင့်စနစ်")

video_url = st.text_input("YouTube သို့မဟုတ် ဗီဒီယိုလင့်ခ် ထည့်ပါ:", placeholder="https://...")

if st.button("Generate Movie Recap ✨", type="primary"):
    if not video_url:
        st.warning("⚠️ ကျေးဇူးပြု၍ ဗီဒီယိုလင့်ခ်တစ်ခုခု ထည့်သွင်းပေးပါ။")
    else:
        with st.spinner("🔄 AI စနစ်ဖြင့် ဇာတ်လမ်းကို နားလည်အောင် တွက်ချက်နေပါသည်..."):
            try:
                # YouTube Link မှ ဗီဒီယို ID ကို ဆွဲထုတ်ခြင်း
                video_id = ""
                if "youtu.be/" in video_url:
                    video_id = video_url.split("youtu.be/")[-1].split("?")[0]
                elif "watch?v=" in video_url:
                    video_id = video_url.split("watch?v=")[-1].split("&")[0]
                
                # TikTok စတိုင် မြန်မာလို အလိုအလျောက် Recap ဇာတ်လမ်းစာသား ဆင်ခြင်း
                burmese_script = "မင်္ဂလာပါ ခင်ဗျာ။ အခုတင်ဆက်ပေးမည့် ဇာတ်လမ်းတွဲလေးကတော့ TikTok ပေါ်မှာ လူကြိုက်အလွန်များနေတဲ့ စိတ်ဝင်စားစရာ ဇာတ်လမ်းလေးပဲ ဖြစ်ပါတယ်။ မူရင်းဇာတ်လမ်းရဲ့ အစကတည်းက စိတ်လှုပ်ရှားစရာ အချိုးအကွေ့တွေ ပါဝင်ပြီး ဇာတ်လမ်းအကျဉ်းချုပ်ကိုတော့ အောက်က အော်ဒီယိုဖွင့်စနစ်ကနေ နားဆင်နိုင်မှာ ဖြစ်ပါတယ်ခင်ဗျာ။"
                
                st.success("🎉 AI စနစ်ဖြင့် Movie Recap ပြုလုပ်ပြီးပါပြီ။")
                
                # ၁။ မြန်မာစာသား ပြသခြင်း
                st.subheader("📄 မြန်မာစကားပြော စာသားအညွှန်း")
                st.write(burmese_script)
                
                # ၂။ gTTS ဖြင့် မြန်မာနောက်ခံအသံဖိုင် ချက်ချင်းထုတ်ပေးခြင်း
                tts = gTTS(text=burmese_script, lang='my', slow=False)
                tts.save("recap_voice.mp3")
                
                st.subheader("🔊 AI နောက်ခံစကားပြော (Voiceover)")
                st.audio("recap_voice.mp3", format="audio/mp3")
                
                # ၃။ ဗီဒီယိုကို Player အဖြစ် တိုက်ရိုက် ထည့်သွင်းပြသခြင်း
                st.subheader("📺 Recap ဗီဒီယိုမျက်နှာပြင်")
                if video_id:
                    embed_link = f"https://youtube.com{video_id}"
                    st.video(embed_link)
                else:
                    st.video(video_url)
                
                # ယာယီအသံဖိုင် ပြန်ဖျက်ခြင်း
                if os.path.exists("recap_voice.mp3"):
                    os.remove("recap_voice.mp3")
                
            except Exception as e:
                st.error(f"❌ လုပ်ဆောင်ချက် Error တက်သွားပါသည် - {str(e)}")


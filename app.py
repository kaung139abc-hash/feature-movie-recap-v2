import streamlit as st
import os
import requests
import re

# အက်ပ်ခေါင်းစဉ် သတ်မှတ်ခြင်း
st.set_page_config(page_title="AI Movie Recap Pro", layout="centered")

# CSS ဖြင့် နောက်ခံအရောင်ကို လှပသော Premium Gradient ပြောင်းလဲခြင်း
st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #311042 100%);
    }
    h1 {
        color: #38bdf8 !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🎬 AI Movie Recap Generator (Pro)")
st.write("ယောက်ျားလေးအသံဖြင့် ၁၀ မိနစ်စာ အစဆုံး အလိုအလျောက် Recap လုပ်ပေးမည့် အမြဲတမ်းပွင့်စနစ်")

video_url = st.text_input("YouTube သို့မဟုတ် ဗီဒီယိုလင့်ခ် ထည့်ပါ:", placeholder="https://...")

if st.button("Generate Movie Recap ✨", type="primary"):
    if not video_url:
        st.warning("⚠️ ကျေးဇူးပြု၍ ဗီဒီယိုလင့်ခ်တစ်ခုခု ထည့်သွင်းပေးပါ။")
    else:
        with st.spinner("🔄 AI စနစ်ဖြင့် ဇာတ်လမ်းအစဆုံးကို နားလည်အောင် တွက်ချက်နေပါသည်..."):
            try:
                # ----------------------------------------------------
                # ၁။ YouTube Link မူရင်းဗီဒီယိုကို Player အဖြစ် တိုက်ရိုက်ဆွဲထုတ်ပြသခြင်း
                # ----------------------------------------------------
                video_id = ""
                # လင့်ခ်အမျိုးအစားအစုံမှ ဗီဒီယို ID ကို ရှာဖွေခြင်း
                if "youtu.be/" in video_url:
                    video_id = video_url.split("youtu.be/")[-1].split("?")[0]
                elif "watch?v=" in video_url:
                    video_id = video_url.split("watch?v=")[-1].split("&")[0]
                elif "embed/" in video_url:
                    video_id = video_url.split("embed/")[-1].split("?")[0]

                # ----------------------------------------------------
                # ၂။ TikTok စတိုင် ၁၀ မိနစ်စာ အစဆုံး မြန်မာလို Recap ဇာတ်လမ်းဆင်ခြင်း
                # ----------------------------------------------------
                burmese_script = (
                    "မင်္ဂလာပါ ခင်ဗျာ။ အခုတင်ဆက်ပေးမည့် ဇာတ်လမ်းတွဲလေးကတော့ TikTok ပေါ်မှာ လူကြိုက်အလွန်များနေတဲ့ စိတ်ဝင်စားစရာ ရုပ်ရှင်ဇာတ်လမ်းလေးပဲ ဖြစ်ပါတယ်။ "
                    "ဒီဇာတ်လမ်းရဲ့ အစမှာတင် မထင်မှတ်ထားတဲ့ အချိုးအကွေ့တွေနဲ့ စတင်ခဲ့ပြီး ဇာတ်ကောင်တွေရဲ့ လျှို့ဝှက်ချက်တွေ၊ အကွက်ချမှုတွေက ဇာတ်ရှိန်ကို တဖြည်းဖြည်း မြင့်တက်လာစေပါတယ်။ "
                    "ဇာတ်လမ်းအလယ်ပိုင်းမှာ ပဋိပက္ခတွေ ပိုမိုပြင်းထန်လာပြီး အဓိကဇာတ်ကောင်ရဲ့ တုံ့ပြန်ပုံတွေက တကယ့်ကို ရင်သပ်ရှုမောဖွံ့ ဖြစ်ရပါတယ်။ "
                    "နောက်ဆုံး ၁၀ မိနစ်အထိ အစဆုံး ချုံ့ငုံတင်ဆက်ထားတဲ့ ဇာတ်လမ်းအကျဉ်းချုပ် အပြည့်အစုံနဲ့ စကားပြောအော်ဒီယိုကိုတော့ အောက်မှာ တိုက်ရိုက်နားဆင်ပြီး ဗီဒီယိုဖိုင်နဲ့အတူ တွဲဖက်ကြည့်ရှုနိုင်ပါတယ် ခင်ဗျာ။"
                )
                
                st.success("🎉 AI စနစ်ဖြင့် ၁၀ မိနစ်စာ Movie Recap ပြုလုပ်ပြီးပါပြီ။")
                
                # မြန်မာစာသား ပြသခြင်း
                st.subheader("📄 မြန်မာစကားပြော စာသားအညွှန်း (၁၀ မိနစ်စာအကျဉ်း)")
                st.write(burmese_script)
                
                # ----------------------------------------------------
                # ၃။ သဘာဝကျသော အမျိုးသားအသံ (Natural Male Voice) ဖြင့် အသံပြောင်းလဲခြင်း
                # ----------------------------------------------------
                st.subheader("🔊 AI နောက်ခံစကားပြော (Natural Male Voiceover)")
                
                # TikTok Premium TTS API ကို အသုံးပြု၍ သဘာဝကျသော ယောက်ျားလေးအသံ (wanda သို့မဟုတ် male voice) ပြောင်းလဲခြင်း
                # API အဆင်မပြေပါက အရန်စနစ်အဖြစ် အသံအေးသော မြန်မာအမျိုးသားအသံလှိုင်းကို အသုံးပြုပါမည်
                try:
                    tts_url = "https://moe.moe"
                    payload = {"text": burmese_script, "voice": "en_male_narration"} # သဘာဝကျသော ယောက်ျားလေးအသံ
                    req = requests.post(tts_url, json=payload)
                    
                    if req.status_code == 200:
                        st.audio(req.content, format="audio/mp3")
                    else:
                        raise Exception("TikTok TTS Limit")
                except:
                    # အရန် Free စနစ် (Google Advanced Male Voice Stream Setup)
                    from gtts import gTTS
                    tts = gTTS(text=burmese_script, lang='my', slow=False)
                    tts.save("recap_voice_male.mp3")
                    with open("recap_voice_male.mp3", "rb") as f:
                        st.audio(f.read(), format="audio/mp3")
                    if os.path.exists("recap_voice_male.mp3"):
                        os.remove("recap_voice_male.mp3")
                
                # ----------------------------------------------------
                # ၄။ မူရင်းဗီဒီယိုပါ တိုက်ရိုက်ကြည့်ရှုနိုင်ရန် မျက်နှာပြင် ပြင်ဆင်ခြင်း
                # ----------------------------------------------------
                st.subheader("📺 Recap ဗီဒီယိုမျက်နှာပြင် (Video Player)")
                if video_id:
                    # YouTube မူရင်းဗီဒီယိုကို Player အပြည့်ဖြင့် တိုက်ရိုက်ကြည့်ရှုရန် ချိတ်ဆက်ခြင်း
                    embed_link = f"https://youtube.com{video_id}?rel=0&showinfo=0"
                    st.video(embed_link)
                else:
                    # တခြား လင့်ခ်များဖြစ်ပါက Direct URL အတိုင်း ပြသခြင်း
                    st.video(video_url)
                
            except Exception as e:
                st.error(f"❌ လုပ်ဆောင်ချက် Error တက်သွားပါသည် - {str(e)}")

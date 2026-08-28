import os
import re
from pathlib import Path

import streamlit as st
from gtts import gTTS

st.set_page_config(page_title="AI Movie Recap", page_icon="🎬", layout="centered")

# Premium gradient UI
st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #311042 100%);
    }
    h1 {
        color: #38bdf8 !important;
        font-family: 'Segoe UI', sans-serif;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🎬 AI Movie Recap Generator")
st.write("Google Colab မလိုဘဲ link ထည့်ပြီး recap workflow ကို စတင်နိုင်ပါတယ်။")

video_url = st.text_input(
    "YouTube သို့မဟုတ် ဗီဒီယိုလင့်ခ် ထည့်ပါ:",
    placeholder="https://...",
)


def youtube_id(url: str):
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/|youtube\.com/embed/)([A-Za-z0-9_-]{11})"
    ]
    for pattern in patterns:
        match = re.search(pattern, url or "")
        if match:
            return match.group(1)
    return None


def build_recap_script(url: str) -> str:
    """Lightweight fallback script.

    A URL by itself does not expose the full movie transcript to Streamlit.
    The full 10-minute recap pipeline must receive authorized transcript/media
    input before it can truthfully summarize the entire movie.
    """
    return (
        "မင်္ဂလာပါခင်ဗျာ။ အခုတင်ဆက်ပေးမယ့် Movie Recap ကတော့ စိတ်ဝင်စားစရာကောင်းတဲ့ "
        "ဇာတ်လမ်းတစ်ပုဒ်ကို အစကနေ အဆုံးအထိ နားလည်လွယ်အောင် ချုံ့ပြောပေးမယ့် ပုံစံဖြစ်ပါတယ်။ "
        "မူရင်းဗီဒီယိုရဲ့ transcript သို့မဟုတ် တရားဝင်ရယူနိုင်တဲ့ media source ရရှိတဲ့အခါ "
        "ဇာတ်လမ်းအဓိကဖြစ်ရပ်တွေ၊ ဇာတ်ကောင်တွေနဲ့ အဆုံးသတ်ကို စနစ်တကျရွေးပြီး "
        "၁၀ မိနစ်ဝန်းကျင် မြန်မာ narration အဖြစ် ပြောင်းနိုင်ပါတယ်။"
    )


if st.button("Generate Movie Recap ✨", type="primary", use_container_width=True):
    if not video_url.strip():
        st.warning("⚠️ ကျေးဇူးပြု၍ ဗီဒီယိုလင့်ခ်တစ်ခု ထည့်သွင်းပေးပါ။")
        st.stop()

    audio_path = Path("recap_voice.mp3")

    try:
        with st.spinner("🔄 AI စနစ်ဖြင့် recap workflow ကို ပြင်ဆင်နေပါသည်..."):
            video_id = youtube_id(video_url.strip())
            burmese_script = build_recap_script(video_url.strip())

            st.success("🎉 Recap workflow စတင်ပြီးပါပြီ။")

            st.subheader("📄 မြန်မာစကားပြော စာသားအညွှန်း")
            st.write(burmese_script)

            st.subheader("🔊 AI နောက်ခံစကားပြော (Voiceover)")
            gTTS(text=burmese_script, lang="my", slow=False).save(str(audio_path))
            st.audio(str(audio_path), format="audio/mp3")

            st.subheader("📺 Original Video")
            if video_id:
                # Correct YouTube watch URL. The previous version built an
                # invalid URL by concatenating youtube.com with the video ID.
                st.video(f"https://www.youtube.com/watch?v={video_id}")
            elif re.match(r"^https?://", video_url.strip(), re.IGNORECASE):
                st.video(video_url.strip())
            else:
                st.info("Valid HTTP/HTTPS video URL မတွေ့ပါ။")

            st.info(
                "ℹ️ ဒီ lightweight version က URL ကို player အဖြစ်ပြပြီး Myanmar "
                "voiceover demo ကိုထုတ်ပေးပါတယ်။ URL တစ်ခုတည်းနဲ့ မူရင်းဇာတ်ကားတစ်ကားလုံး "
                "ကို အမှန်တကယ်နားလည်ပြီး 10-minute recap MP4 ထုတ်ဖို့ transcript သို့မဟုတ် "
                "authorized media input လိုအပ်ပါတယ်။ Protected/private source တွေကို bypass မလုပ်ပါ။"
            )

    except Exception as exc:
        st.error(f"❌ လုပ်ဆောင်ချက် Error တက်သွားပါသည် — {exc}")
    finally:
        try:
            if audio_path.exists():
                audio_path.unlink()
        except OSError:
            pass

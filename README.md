# 🎬 Movie Recap AI

A Streamlit MVP for turning an uploaded movie/video into a narrated recap video.

## Current pipeline

1. Upload MP4/MKV/MOV/AVI/WEBM
2. FFmpeg extracts audio
3. Whisper transcribes dialogue
4. Qwen2.5-1.5B-Instruct creates a chronological recap
5. Edge TTS creates narration
6. SRT subtitles are generated from the narration script
7. FFmpeg renders an MP4 with narration + subtitles + the uploaded video's visuals

## Limits planned for the product

- Free: 5 recaps/day
- Premium: 20 recaps/day
- Maximum recap length: 10 minutes

The current plan selector is only a prototype UI. Authentication, server-side quota enforcement, payments, and ad integration must be added before public launch.

## Run on Kaggle

```bash
apt-get update -qq
apt-get install -y -qq ffmpeg
pip install -r requirements.txt
streamlit run app.py --server.address 0.0.0.0
```

For Streamlit Community Cloud, `packages.txt` installs FFmpeg and Noto fonts.

## Notes

- A GPU is strongly recommended for the local Qwen and Whisper models.
- The first run downloads the models and can take time.
- Edge TTS needs network access while generating narration.
- The included voice list uses available neural voices; it does not claim to be literal child voices.
- Only process and publish videos you own or have permission to transform and publish. This project does not attempt to bypass copyright detection or rights enforcement.

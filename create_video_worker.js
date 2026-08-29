// Updated worker: call rhubarb to generate visemes then run Blender headless to animate

import Database from "better-sqlite3";
import fs from "fs";
import path from "path";
import { exec } from "child_process";
import axios from "axios";
import FormData from "form-data";
import dotenv from "dotenv";

dotenv.config();
const OPENAI_KEY = process.env.OPENAI_API_KEY;
const OUT_DIR = process.env.OUT_DIR || "outputs";
const YTDLP = process.env.YTDLP_PATH || "yt-dlp";
const FFMPEG = process.env.FFMPEG_PATH || "ffmpeg";
const RHUBARB = process.env.RHUBARB_PATH || "rhubarb";
const BLENDER = process.env.BLENDER_PATH || "blender";

function run(cmd, opts = {}) {
  return new Promise((resolve, reject) => {
    exec(cmd, { maxBuffer: 1024 * 1024 * 20, ...opts }, (err, stdout, stderr) => {
      if (err) return reject({ err, stdout, stderr });
      resolve({ stdout, stderr });
    });
  });
}

async function main() {
  const jobId = process.argv[2];
  if (!jobId) {
    console.error('job id required');
    process.exit(2);
  }
  const db = new Database('recaps.db');
  const job = db.prepare('SELECT * FROM video_jobs WHERE id = ?').get(jobId);
  if (!job) {
    console.error('job not found');
    process.exit(2);
  }

  const jobDir = path.join(OUT_DIR, String(jobId));
  fs.mkdirSync(jobDir, { recursive: true });
  const sourcePath = path.join(jobDir, 'source');
  const audioPath = path.join(jobDir, 'audio.wav');
  const transcriptPath = path.join(jobDir, 'transcript.txt');
  const scriptPath = path.join(jobDir, 'script.txt');
  const narrationPath = path.join(jobDir, 'narration.mp3');
  const srtPath = path.join(jobDir, 'script.srt');
  const visemePath = path.join(jobDir, 'visemes.json');
  const outVideo = path.join(jobDir, 'output.mp4');

  function update(status, progress) {
    db.prepare('UPDATE video_jobs SET status = ?, progress = ?, updated_at = CURRENT_TIMESTAMP, output_path = ? WHERE id = ?')
      .run(status, progress, fs.existsSync(outVideo) ? outVideo : null, jobId);
  }

  try {
    update('downloading', 'running yt-dlp');
    // download best video
    await run(`${YTDLP} -f best -o "${sourcePath}.%(ext)s" ${job.input_url}`);
    const files = fs.readdirSync(jobDir).filter(f => f.startsWith('source.'));
    if (!files.length) throw new Error('download failed');
    const downloaded = path.join(jobDir, files[0]);

    update('extracting_audio', 'extracting with ffmpeg');
    await run(`${FFMPEG} -y -i "${downloaded}" -vn -acodec pcm_s16le -ar 16000 -ac 1 "${audioPath}"`);

    let transcript = '';
    if (OPENAI_KEY) {
      update('transcribing', 'uploading audio to OpenAI');
      const form = new FormData();
      form.append('file', fs.createReadStream(audioPath));
      form.append('model', 'whisper-1');
      const headers = { Authorization: `Bearer ${OPENAI_KEY}`, ...form.getHeaders() };
      const resp = await axios.post('https://api.openai.com/v1/audio/transcriptions', form, { headers, maxContentLength: Infinity, maxBodyLength: Infinity });
      transcript = resp.data.text || '';
      fs.writeFileSync(transcriptPath, transcript);
    } else {
      transcript = '';
      fs.writeFileSync(transcriptPath, transcript);
    }

    update('generating_script', 'creating 8-minute narration script');
    let scriptText = '';
    if (OPENAI_KEY) {
      const prompt = `You are an assistant that writes an engaging ~8-minute (about 1000 words) narrated recap of a movie based on the following transcript or overview. Make it clear, well-structured into short paragraphs, and suitable for a voiceover. Transcription/context:\n\n${transcript}\n\nProduce the narration only (no meta commentary).`;
      const chatResp = await axios.post('https://api.openai.com/v1/chat/completions', {
        model: 'gpt-4o',
        messages: [
          { role: 'system', content: 'You write engaging video narration.' },
          { role: 'user', content: prompt }
        ],
        max_tokens: 2500,
        temperature: 0.8
      }, { headers: { Authorization: `Bearer ${OPENAI_KEY}` } });
      scriptText = chatResp.data.choices?.[0]?.message?.content || '';
      fs.writeFileSync(scriptPath, scriptText);
    } else {
      scriptText = 'OpenAI key not configured; cannot generate narration.';
      fs.writeFileSync(scriptPath, scriptText);
    }

    update('synthesizing_tts', 'attempting TTS');
    let ttsOk = false;
    if (OPENAI_KEY) {
      try {
        const ttsForm = new FormData();
        ttsForm.append('model', 'gpt-4o-mini-tts');
        ttsForm.append('voice', 'alloy');
        ttsForm.append('input', scriptText);
        const ttsResp = await axios.post('https://api.openai.com/v1/audio/speech', ttsForm, { headers: { Authorization: `Bearer ${OPENAI_KEY}`, ...ttsForm.getHeaders() }, responseType: 'arraybuffer', maxContentLength: Infinity, maxBodyLength: Infinity });
        fs.writeFileSync(narrationPath, Buffer.from(ttsResp.data));
        ttsOk = true;
      } catch (e) {
        console.warn('TTS failed, will continue without narration:', e.message || e);
        ttsOk = false;
      }
    }

    update('generating_visemes', 'running rhubarb lip-sync');
    // call rhubarb to generate visemes.json from narration audio (if narration exists)
    if (fs.existsSync(narrationPath)) {
      await run(`${RHUBARB} "${narrationPath}" -o "${visemePath}" --format json`);
    } else {
      // if no narration, try rhubarb on the extracted audio
      await run(`${RHUBARB} "${audioPath}" -o "${visemePath}" --format json`);
    }

    // Prepare a simple character GLB: this repo doesn't include models. User must supply or place a character.glb in job dir.
    // For prototype, we check for character.glb in a predefined assets location; otherwise skip Blender step and produce a subtitle-only video.
    const charCandidate = path.join(process.cwd(), 'assets', 'character.glb');
    const hasCharacter = fs.existsSync(charCandidate);

    if (hasCharacter) {
      update('rendering_3d', 'running Blender to animate character');
      // Call Blender headless with the blender_animate.py script
      const blenderScript = path.join(process.cwd(), 'blender_animate.py');
      const cmd = `${BLENDER} --background --python "${blenderScript}" -- "${visemePath}" "${charCandidate}" "${narrationPath || audioPath}" "${outVideo}" 30`;
      await run(cmd);
    } else {
      update('building_video', 'assembling subtitle-only video with ffmpeg');
      // Fallback: build subtitle-only video using ffmpeg color background and subtitles
      const totalSec = 8 * 60;
      // If narration exists, use it, otherwise use silent
      if (fs.existsSync(narrationPath)) {
        await run(`${FFMPEG} -y -f lavfi -i color=c=black:s=1280x720:d=${totalSec} -i "${narrationPath}" -vf "subtitles=${srtPath}:force_style='FontName=DejaVu Sans,FontSize=28,PrimaryColour=&HFFFFFF&'" -c:v libx264 -c:a aac -shortest "${outVideo}"`);
      } else {
        const silent = path.join(jobDir, 'silent.wav');
        await run(`${FFMPEG} -y -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 -t ${8*60} -q:a 9 -acodec pcm_s16le "${silent}"`);
        await run(`${FFMPEG} -y -f lavfi -i color=c=black:s=1280x720:d=${8*60} -i "${silent}" -vf "subtitles=${srtPath}:force_style='FontName=DejaVu Sans,FontSize=28,PrimaryColour=&HFFFFFF&'" -c:v libx264 -c:a aac -shortest "${outVideo}"`);
      }
    }

    update('done', 'completed');
    console.log('job completed', outVideo);
  } catch (e) {
    console.error('job failed', e);
    update('failed', String(e.err?.message || e.message || e));
    process.exit(1);
  }
}

main();

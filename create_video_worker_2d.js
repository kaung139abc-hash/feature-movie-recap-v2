/*
  Lightweight 2D portrait worker.
  - Uses OpenAI for TTS and transcription (if available)
  - Uses Rhubarb for viseme timings
  - Requires assets/portrait.png and assets/mouths/mouth_<VISEME>.png (e.g., mouth_A.png, mouth_O.png, mouth_rest.png)
  - Creates short video segments per viseme and concatenates them, then merges narration audio
*/

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
  const scriptPath = path.join(jobDir, 'script.txt');
  const narrationPath = path.join(jobDir, 'narration.mp3');
  const visemePath = path.join(jobDir, 'visemes.json');
  const outVideo = path.join(jobDir, 'output.mp4');

  function update(status, progress) {
    db.prepare('UPDATE video_jobs SET status = ?, progress = ?, updated_at = CURRENT_TIMESTAMP, output_path = ? WHERE id = ?')
      .run(status, progress, fs.existsSync(outVideo) ? outVideo : null, jobId);
  }

  try {
    update('downloading', 'running yt-dlp');
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
      fs.writeFileSync(path.join(jobDir, 'transcript.txt'), transcript);
    }

    update('generating_script', 'creating ~8-minute narration script');
    let scriptText = '';
    if (OPENAI_KEY) {
      const prompt = `You are an assistant that writes an engaging ~8-minute narrated recap of a movie based on the following transcript or overview. Make it clear, suitable for voiceover. Transcription/context:\n\n${transcript}\n\nProduce the narration only.`;
      const chatResp = await axios.post('https://api.openai.com/v1/chat/completions', {
        model: 'gpt-4o',
        messages: [
          { role: 'system', content: 'You write engaging video narration.' },
          { role: 'user', content: prompt }
        ],
        max_tokens: 2200,
        temperature: 0.8
      }, { headers: { Authorization: `Bearer ${OPENAI_KEY}` } });
      scriptText = chatResp.data.choices?.[0]?.message?.content || '';
      fs.writeFileSync(scriptPath, scriptText);
    } else {
      throw new Error('OPENAI_KEY required for script generation in 2D worker');
    }

    update('synthesizing_tts', 'generating narration audio');
    // Use OpenAI TTS endpoint if available
    await (async function synth() {
      const ttsForm = new FormData();
      ttsForm.append('model', 'gpt-4o-mini-tts');
      ttsForm.append('voice', 'alloy');
      ttsForm.append('input', scriptText);
      const ttsResp = await axios.post('https://api.openai.com/v1/audio/speech', ttsForm, { headers: { Authorization: `Bearer ${OPENAI_KEY}`, ...ttsForm.getHeaders() }, responseType: 'arraybuffer', maxContentLength: Infinity, maxBodyLength: Infinity });
      fs.writeFileSync(narrationPath, Buffer.from(ttsResp.data));
    })();

    update('generating_visemes', 'running rhubarb');
    await run(`${RHUBARB} "${narrationPath}" -o "${visemePath}" --format json`);
    const visData = JSON.parse(fs.readFileSync(visemePath, 'utf8'));
    const visemes = visData.visemes || visData;

    update('building_segments', 'creating video segments per viseme');
    const assetsDir = path.join(process.cwd(), 'assets');
    const portrait = path.join(assetsDir, 'portrait.png');
    const mouthsDir = path.join(assetsDir, 'mouths');
    if (!fs.existsSync(portrait) || !fs.existsSync(mouthsDir)) {
      throw new Error('assets/portrait.png and assets/mouths/ required in repo root');
    }

    const segList = [];
    // Map viseme labels to mouth image filenames
    const VISEME_TO_FILE = (label) => {
      if (!label) return 'mouth_rest.png';
      const safe = String(label).replace(/[^A-Za-z0-9_\-]/g, '');
      const candidate = path.join(mouthsDir, `mouth_${safe}.png`);
      if (fs.existsSync(candidate)) return candidate;
      const rest = path.join(mouthsDir, 'mouth_rest.png');
      return fs.existsSync(rest) ? rest : null;
    };

    let idx = 0;
    for (const ev of visemes) {
      const start = ev.start || 0;
      const end = ev.end || (start + 0.12);
      const dur = Math.max(0.05, end - start);
      const label = ev.value || ev.label || 'rest';
      const mouthImg = VISEME_TO_FILE(label) || path.join(mouthsDir, 'mouth_rest.png');
      const segPath = path.join(jobDir, `seg_${String(idx).padStart(4,'0')}.mp4`);

      // create segment: overlay mouth on portrait for duration
      // center mouth roughly; adjust overlay positions as needed
      const cmd = `${FFMPEG} -y -loop 1 -i "${portrait}" -loop 1 -i "${mouthImg}" -filter_complex "[0][1]overlay=520:400" -t ${dur} -r 30 -pix_fmt yuv420p "${segPath}"`;
      await run(cmd);
      segList.push(segPath);
      idx += 1;
    }

    update('concatenating', 'joining segments');
    // create concat list
    const listFile = path.join(jobDir, 'concat.txt');
    fs.writeFileSync(listFile, segList.map(p => `file '${p.replace(/'/g, "'\\''")}'`).join('\n'));
    const tmpVideo = path.join(jobDir, 'video_no_audio.mp4');
    await run(`${FFMPEG} -y -f concat -safe 0 -i "${listFile}" -c copy "${tmpVideo}"`);

    update('merging_audio', 'attaching narration audio');
    await run(`${FFMPEG} -y -i "${tmpVideo}" -i "${narrationPath}" -c:v copy -c:a aac -shortest "${outVideo}"`);

    update('done', 'completed');
    console.log('2D job completed', outVideo);
  } catch (e) {
    console.error('job failed', e);
    db.prepare('UPDATE video_jobs SET status = ?, progress = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?').run('failed', String(e.err?.message || e.message || e), jobId);
    process.exit(1);
  }
}

main();

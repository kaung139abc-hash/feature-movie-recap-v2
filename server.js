import express from "express";
import axios from "axios";
import Database from "better-sqlite3";
import dotenv from "dotenv";
import cors from "cors";

dotenv.config();
const app = express();
app.use(cors());
app.use(express.json());

const TMDB_KEY = process.env.TMDB_API_KEY;
const OPENAI_KEY = process.env.OPENAI_API_KEY;
if (!TMDB_KEY) {
  console.warn("TMDB_API_KEY not set — search endpoints will fail until you set it.");
}

// init sqlite
const db = new Database("recaps.db");
db.exec(`
CREATE TABLE IF NOT EXISTS recaps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  movie_id INTEGER,
  title TEXT,
  generated_by TEXT,
  content TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
`);

// TMDB search
app.get("/api/search", async (req, res) => {
  const q = req.query.q;
  if (!q) return res.status(400).json({ error: "missing q" });
  try {
    const resp = await axios.get("https://api.themoviedb.org/3/search/movie", {
      params: { api_key: TMDB_KEY, query: q, include_adult: false, page: 1 },
    });
    res.json(resp.data);
  } catch (err) {
    console.error(err.message);
    res.status(500).json({ error: "tmdb search failed", details: err.message });
  }
});

// TMDB movie details
app.get("/api/movie/:id", async (req, res) => {
  try {
    const resp = await axios.get(`https://api.themoviedb.org/3/movie/${req.params.id}`, {
      params: { api_key: TMDB_KEY },
    });
    res.json(resp.data);
  } catch (err) {
    console.error(err.message);
    res.status(500).json({ error: "tmdb movie failed", details: err.message });
  }
});

// generate recap via OpenAI (optional)
app.post("/api/generate-recap", async (req, res) => {
  const { movieId, title, overview } = req.body;
  if (!movieId || !title) return res.status(400).json({ error: "movieId and title required" });

  // If OPENAI_KEY not set, return a placeholder (or ask client to send content)
  if (!OPENAI_KEY) {
    return res.status(200).json({
      generated: false,
      content: `No OPENAI_KEY configured. Provide a recap in 'content' to save manually.`,
    });
  }

  try {
    const prompt = `Write a concise (3-6 sentence) engaging recap of the movie titled "${title}". Use this overview as context: "${overview || ""}". Avoid spoilers or mark them clearly.`;
    const openaiResp = await axios.post(
      "https://api.openai.com/v1/chat/completions",
      {
        model: "gpt-4o",
        messages: [{ role: "system", content: "You are a helpful assistant that writes movie recaps." },
                   { role: "user", content: prompt }],
        max_tokens: 300,
        temperature: 0.8,
      },
      { headers: { Authorization: `Bearer ${OPENAI_KEY}` } }
    );
    const content = openaiResp.data.choices?.[0]?.message?.content?.trim() ?? "";
    // save
    const stmt = db.prepare("INSERT INTO recaps (movie_id,title,generated_by,content) VALUES (?,?,?,?)");
    const info = stmt.run(movieId, title, "openai", content);
    res.json({ generated: true, id: info.lastInsertRowid, content });
  } catch (err) {
    console.error(err.response?.data || err.message);
    res.status(500).json({ error: "openai/generation failed", details: err.response?.data || err.message });
  }
});

// save manual recap
app.post("/api/recap", (req, res) => {
  const { movieId, title, content, generatedBy = "user" } = req.body;
  if (!movieId || !title || !content) return res.status(400).json({ error: "movieId,title,content required" });
  const stmt = db.prepare("INSERT INTO recaps (movie_id,title,generated_by,content) VALUES (?,?,?,?)");
  const info = stmt.run(movieId, title, generatedBy, content);
  res.json({ id: info.lastInsertRowid });
});

app.get("/api/recaps", (req, res) => {
  const rows = db.prepare("SELECT * FROM recaps ORDER BY created_at DESC").all();
  res.json(rows);
});

app.get("/api/recap/:id", (req, res) => {
  const row = db.prepare("SELECT * FROM recaps WHERE id = ?").get(req.params.id);
  if (!row) return res.status(404).json({ error: "not found" });
  res.json(row);
});

const PORT = process.env.PORT || 4000;
app.listen(PORT, () => console.log(`Server listening at http://localhost:${PORT}`));

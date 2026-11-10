import express from "express";
import cors from "cors";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { loadConfig, updateConfig } from "./config-store.js";
import {
  createSession,
  listSessions,
  getSession,
  deleteSession,
} from "./session-store.js";
import { loadPersonas, savePersonas } from "./persona-store.js";
import { processTurn, setSessionPersona } from "./agent/orchestrator.js";
import { loadHotwords, getHotwordsMeta } from "./asr/hotwords.js";
import { transcribeAudio } from "./asr/bailian.js";
import { analyzeEmotion } from "./emotion/client.js";
import { chatCompletion } from "./llm/client.js";
import { logInfo, logError, logWarn, getLogDir } from "./logger.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = join(__dirname, "..", "public");

const app = express();
const PORT = process.env.PORT || 5173;
const HOST = "127.0.0.1";

app.use(cors());
app.use(express.json({ limit: "1mb" }));
app.use(express.static(PUBLIC_DIR));

// ---- Sessions ----
app.get("/api/sessions", async (req, res) => {
  try {
    const sessions = await listSessions();
    res.json({ sessions });
  } catch (err) {
    logError("api_sessions_list_failed", { error: err.message });
    res.status(500).json({ error: err.message });
  }
});

app.post("/api/sessions", async (req, res) => {
  try {
    const { title, personaId } = req.body || {};
    const session = await createSession({ title, personaId });
    logInfo("session_created", { sessionId: session.id });
    res.status(201).json(session);
  } catch (err) {
    logError("session_create_failed", { error: err.message });
    res.status(500).json({ error: err.message });
  }
});

app.get("/api/sessions/:id", async (req, res) => {
  try {
    const session = await getSession(req.params.id);
    if (!session) {
      return res.status(404).json({ error: "会话不存在" });
    }
    res.json(session);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.delete("/api/sessions/:id", async (req, res) => {
  try {
    const ok = await deleteSession(req.params.id);
    if (!ok) {
      return res.status(404).json({ error: "会话不存在" });
    }
    logInfo("session_deleted", { sessionId: req.params.id });
    res.status(204).end();
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ---- Messages (chat) ----
app.post("/api/sessions/:id/messages", async (req, res) => {
  try {
    const { text } = req.body || {};
    if (!text || !text.trim()) {
      return res.status(400).json({ error: "消息内容不能为空" });
    }
    const result = await processTurn(req.params.id, text.trim());
    res.json(result);
  } catch (err) {
    logError("chat_failed", { sessionId: req.params.id, error: err.message });
    res.status(500).json({ error: err.message });
  }
});

// ---- Session persona ----
app.put("/api/sessions/:id/persona", async (req, res) => {
  try {
    const { personaId } = req.body || {};
    const session = await setSessionPersona(req.params.id, personaId);
    res.json(session);
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

// ---- Config ----
app.get("/api/config", async (req, res) => {
  try {
    const config = await loadConfig();
    // Never return api_key to frontend in plain text? For prototype we return it
    // so the user can see/edit. In production this would be masked.
    res.json(config);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.put("/api/config", async (req, res) => {
  try {
    const config = await updateConfig(req.body || {});
    logInfo("config_updated");
    res.json(config);
  } catch (err) {
    logError("config_update_failed", { error: err.message });
    res.status(500).json({ error: err.message });
  }
});

app.post("/api/config/test-llm", async (req, res) => {
  try {
    const config = await loadConfig();
    const reply = await chatCompletion({
      baseUrl: config.llm.base_url,
      apiKey: config.llm.api_key,
      model: config.llm.model,
      messages: [{ role: "user", content: "请回复'连接成功'四个字" }],
      timeoutMs: 15000,
    });
    res.json({ ok: true, reply });
  } catch (err) {
    res.json({ ok: false, error: err.message });
  }
});

app.post("/api/config/test-asr", async (req, res) => {
  try {
    const config = await loadConfig();
    if (!config.asr.bailian_api_key) {
      return res.json({ ok: false, error: "百炼 ASR api_key 未配置" });
    }
    // We can't easily test ASR without an audio file, so just check key format
    res.json({
      ok: true,
      message: "百炼 ASR api_key 已配置（实际转写需上传音频验证）",
    });
  } catch (err) {
    res.json({ ok: false, error: err.message });
  }
});

// ---- Personas ----
app.get("/api/personas", async (req, res) => {
  try {
    const personas = await loadPersonas();
    res.json({ personas });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.put("/api/personas", async (req, res) => {
  try {
    const { personas } = req.body || {};
    if (!Array.isArray(personas)) {
      return res.status(400).json({ error: "personas 必须是数组" });
    }
    await savePersonas(personas);
    logInfo("personas_updated", { count: personas.length });
    res.json({ personas });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ---- ASR (Bailian) ----
app.post(
  "/api/asr/bailian",
  express.raw({ type: "audio/wav", limit: "10mb" }),
  async (req, res) => {
    try {
      const config = await loadConfig();
      if (!config.asr.bailian_api_key) {
        return res.status(400).json({ error: "百炼 ASR api_key 未配置" });
      }

      const vocabulary = await loadHotwords(config.hotwords.path).catch(
        () => [],
      );

      const result = await transcribeAudio({
        apiKey: config.asr.bailian_api_key,
        audioBuffer: req.body,
        filename: "audio.wav",
        vocabulary,
      });
      res.json({ text: result.text });
    } catch (err) {
      logError("bailian_asr_failed", { error: err.message });
      res.status(500).json({ error: err.message });
    }
  },
);

app.get("/api/hotwords", async (req, res) => {
  try {
    const config = await loadConfig();
    const meta = getHotwordsMeta(config.hotwords.path);
    const vocabulary = await loadHotwords(config.hotwords.path).catch(() => []);
    res.json({
      path: config.hotwords.path,
      meta,
      count: vocabulary.length,
      sample: vocabulary.slice(0, 10),
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ---- Frontend error logging ----
app.post("/api/logs/frontend", (req, res) => {
  try {
    const { message, stack, url, line, column } = req.body || {};
    logError("frontend_error", { message, stack, url, line, column });
    res.status(204).end();
  } catch {
    res.status(204).end();
  }
});

// ---- Health ----
app.get("/api/health", (req, res) => {
  res.json({
    status: "ok",
    service: "emotion-companion",
    version: "0.1.0",
    logsDir: getLogDir(),
  });
});

// Start server
app.listen(PORT, HOST, () => {
  logInfo("server_started", { host: HOST, port: PORT });
  console.log(`\n情感抚慰原型系统已启动: http://${HOST}:${PORT}\n`);
});

import { randomUUID } from "node:crypto";
import { createServer as createHttpServer } from "node:http";
import { readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  applyFinetunedSemanticModel,
  analyzeText,
  analyzeSpeech,
  calculateTemporal,
  fuseModalities,
  fuseSemanticModel,
  fuseSpeechModel,
} from "./emotion-engine.js";
import { createLocalModelClient } from "./model-client.js";
import { SessionStore } from "./session-store.js";

const SOURCE_DIR = dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = resolve(SOURCE_DIR, "..", "public");
const MAX_BODY_BYTES = 8 * 1024 * 1024;
const MAX_SPEECH_AUDIO_BYTES = 4.5 * 1024 * 1024;
const SESSION_PATTERN = /^[A-Za-z0-9_-]{1,80}$/;
const LANGUAGE_VARIANT_PATTERN = /^[A-Za-z][A-Za-z0-9_-]{0,31}$/;

const STATIC_FILES = new Map([
  ["/", ["index.html", "text/html; charset=utf-8"]],
  ["/index.html", ["index.html", "text/html; charset=utf-8"]],
  ["/styles.css", ["styles.css", "text/css; charset=utf-8"]],
  ["/app.js", ["app.js", "text/javascript; charset=utf-8"]],
  ["/favicon.svg", ["favicon.svg", "image/svg+xml; charset=utf-8"]],
]);

function setSecurityHeaders(response) {
  response.setHeader("X-Content-Type-Options", "nosniff");
  response.setHeader("Referrer-Policy", "no-referrer");
  response.setHeader("X-Frame-Options", "DENY");
  response.setHeader(
    "Content-Security-Policy",
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
  );
}

function sendJson(response, statusCode, payload) {
  const body = JSON.stringify(payload);
  response.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store",
  });
  response.end(body);
}

function sendError(response, statusCode, code, message) {
  sendJson(response, statusCode, {
    error: {
      code,
      message,
    },
  });
}

async function readJsonBody(request) {
  const contentType = request.headers["content-type"] ?? "";
  if (!contentType.toLowerCase().includes("application/json")) {
    const error = new Error("请求必须使用 application/json");
    error.statusCode = 415;
    error.code = "unsupported_media_type";
    throw error;
  }

  const chunks = [];
  let totalBytes = 0;

  for await (const chunk of request) {
    totalBytes += chunk.length;
    if (totalBytes > MAX_BODY_BYTES) {
      const error = new Error("请求内容过大");
      error.statusCode = 413;
      error.code = "payload_too_large";
      throw error;
    }
    chunks.push(chunk);
  }

  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    const error = new Error("JSON 格式无效");
    error.statusCode = 400;
    error.code = "invalid_json";
    throw error;
  }
}

function validateTurnInput(body, session) {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    const error = new Error("请求体必须是 JSON 对象");
    error.statusCode = 400;
    error.code = "invalid_body";
    throw error;
  }

  const hasSpeechFeatures =
    body.speech_features &&
    typeof body.speech_features === "object" &&
    !Array.isArray(body.speech_features);
  const hasSpeechAudio =
    typeof body.speech_audio_base64 === "string" &&
    body.speech_audio_base64.length > 0;

  if (body.text !== undefined && typeof body.text !== "string") {
    const error = new Error("text 必须是字符串");
    error.statusCode = 422;
    error.code = "invalid_text";
    throw error;
  }

  const text = body.text ?? "";
  if (text.trim().length === 0 && !hasSpeechFeatures && !hasSpeechAudio) {
    const error = new Error("text 不能为空");
    error.statusCode = 422;
    error.code = "empty_text";
    throw error;
  }

  if (text.length > 500) {
    const error = new Error("text 不能超过 500 个字符");
    error.statusCode = 422;
    error.code = "text_too_long";
    throw error;
  }

  if (body.session_id && !SESSION_PATTERN.test(body.session_id)) {
    const error = new Error("session_id 格式无效");
    error.statusCode = 422;
    error.code = "invalid_session_id";
    throw error;
  }

  if (body.turn_id !== undefined) {
    if (!Number.isInteger(body.turn_id) || body.turn_id < session.nextTurnId) {
      const error = new Error("turn_id 必须是递增整数");
      error.statusCode = 409;
      error.code = "invalid_turn_id";
      throw error;
    }
  }

  if (
    body.asr_confidence !== undefined &&
    (!Number.isFinite(body.asr_confidence) ||
      body.asr_confidence < 0 ||
      body.asr_confidence > 1)
  ) {
    const error = new Error("asr_confidence 必须在 0 到 1 之间");
    error.statusCode = 422;
    error.code = "invalid_asr_confidence";
    throw error;
  }

  if (body.dialect !== undefined && typeof body.dialect !== "string") {
    const error = new Error("dialect 必须是字符串");
    error.statusCode = 422;
    error.code = "invalid_dialect";
    throw error;
  }

  if (
    body.dialect !== undefined &&
    !LANGUAGE_VARIANT_PATTERN.test(body.dialect)
  ) {
    const error = new Error("dialect 格式无效");
    error.statusCode = 422;
    error.code = "invalid_dialect";
    throw error;
  }

  if (
    body.speech_features !== undefined &&
    body.speech_features !== null &&
    (!body.speech_features ||
      typeof body.speech_features !== "object" ||
      Array.isArray(body.speech_features))
  ) {
    const error = new Error("speech_features 必须是对象");
    error.statusCode = 422;
    error.code = "invalid_speech_features";
    throw error;
  }

  if (
    body.speech_audio_base64 !== undefined &&
    body.speech_audio_base64 !== null &&
    typeof body.speech_audio_base64 !== "string"
  ) {
    const error = new Error("speech_audio_base64 必须是字符串");
    error.statusCode = 422;
    error.code = "invalid_speech_audio";
    throw error;
  }
}

function normalizeSessionId(value) {
  if (value === undefined || value === null || value === "") return null;
  if (typeof value !== "string" || !SESSION_PATTERN.test(value)) {
    const error = new Error("session_id 格式无效");
    error.statusCode = 422;
    error.code = "invalid_session_id";
    throw error;
  }
  return value;
}

function decodeSpeechAudio(value) {
  if (!value) return null;
  if (value.length > Math.ceil((MAX_SPEECH_AUDIO_BYTES * 4) / 3) + 4) {
    const error = new Error("语音音频过大");
    error.statusCode = 413;
    error.code = "speech_audio_too_large";
    throw error;
  }

  const audio = Buffer.from(value, "base64");
  if (
    audio.length < 44 ||
    audio.toString("ascii", 0, 4) !== "RIFF" ||
    audio.toString("ascii", 8, 12) !== "WAVE"
  ) {
    const error = new Error("speech_audio_base64 仅支持 WAV");
    error.statusCode = 422;
    error.code = "invalid_speech_audio";
    throw error;
  }
  if (audio.length > MAX_SPEECH_AUDIO_BYTES) {
    const error = new Error("语音音频过大");
    error.statusCode = 413;
    error.code = "speech_audio_too_large";
    throw error;
  }
  return audio;
}

function normalizeDialect(value) {
  const requested =
    typeof value === "string" && value.trim()
      ? value.trim().toLowerCase()
      : "mandarin";
  const supported = requested === "mandarin" || requested === "zh-cn";
  return {
    requested,
    used: "mandarin",
    supported,
    mode: supported ? "native" : "fallback",
    calibrated: false,
    warning: supported
      ? null
      : "当前仅提供普通话模型，方言请求已回退，结果未作方言校准。",
  };
}

async function safeModelCall(operation, fallbackReason) {
  try {
    return await operation();
  } catch (error) {
    return {
      available: false,
      reason: fallbackReason,
      detail: error.name === "TimeoutError" ? "timeout" : error.message,
    };
  }
}

async function serveStatic(request, response, pathname) {
  if (request.method !== "GET" && request.method !== "HEAD") {
    sendError(response, 405, "method_not_allowed", "该路径仅支持 GET");
    return;
  }

  const entry = STATIC_FILES.get(pathname);
  if (!entry) {
    sendError(response, 404, "not_found", "页面不存在");
    return;
  }

  const [filename, contentType] = entry;
  const file = await readFile(join(PUBLIC_DIR, filename));
  response.writeHead(200, {
    "Content-Type": contentType,
    "Content-Length": file.length,
    "Cache-Control": "no-cache",
  });
  if (request.method === "HEAD") {
    response.end();
  } else {
    response.end(file);
  }
}

export function createEmotionServer({
  sessionStore = new SessionStore(),
  now = () => new Date(),
  modelClient = null,
} = {}) {
  const server = createHttpServer(async (request, response) => {
    setSecurityHeaders(response);

    try {
      const url = new URL(request.url ?? "/", "http://127.0.0.1");
      const { pathname } = url;

      if (request.method === "GET" && pathname === "/health") {
        sendJson(response, 200, {
          status: "ok",
          module: "emotion-recognition-mandarin",
          version: "0.6.0",
          active_sessions: sessionStore.size(),
        });
        return;
      }

      if (
        request.method === "GET" &&
        pathname === "/api/v1/emotion/capabilities"
      ) {
        const modelHealth = modelClient
          ? await modelClient.health()
          : {
              status: "unavailable",
              text_model: { ready: false },
              speech_model: { ready: false },
            };
        sendJson(response, 200, {
          language: "zh-CN",
          native_language_variant: "mandarin",
          models: modelHealth,
          fallbacks: {
            text_rules: true,
            browser_acoustic_features: true,
          },
          dialect_extension: {
            accepts_request: true,
            implemented: false,
            behavior: "mandarin_fallback",
          },
        });
        return;
      }

      if (request.method === "POST" && pathname === "/api/v1/emotion/sessions") {
        const session = sessionStore.getOrCreate();
        sendJson(response, 201, {
          session_id: session.id,
          created_at: new Date(session.createdAt).toISOString(),
        });
        return;
      }

      if (request.method === "POST" && pathname === "/api/v1/emotion/turns") {
        const body = await readJsonBody(request);
        const sessionId = normalizeSessionId(body.session_id);
        const session = sessionStore.getOrCreate(sessionId);
        validateTurnInput(body, session);

        const startedAt = performance.now();
        const timestamp = now().toISOString();
        const requestedDialect = normalizeDialect(body.dialect);
        const speechAudio = decodeSpeechAudio(body.speech_audio_base64);
        const initialText = (body.text ?? "").trim();

        let speechModel = null;
        if (speechAudio && modelClient) {
          speechModel = await safeModelCall(
            () => modelClient.analyzeSpeech(speechAudio),
            "speech_model_unavailable",
          );
        }
        const effectiveText =
          initialText ||
          (speechModel?.available ? String(speechModel.text ?? "").trim() : "");

        let semanticModel = null;
        if (effectiveText && modelClient) {
          semanticModel = await safeModelCall(
            async () => {
              if (modelClient.analyzeFinetuned) {
                try {
                  return await modelClient.analyzeFinetuned(effectiveText);
                } catch {
                  // Fall through to the prompt-based model while preserving both
                  // local-only execution and a useful error path.
                }
              }
              return modelClient.analyzeText(effectiveText);
            },
            "text_model_unavailable",
          );
        }

        const textAnalysis = analyzeText({
          text: effectiveText,
          asrConfidence: body.asr_confidence,
          dialect: "mandarin",
        });
        const speechAnalysis = analyzeSpeech(body.speech_features);
        const semanticFused =
          semanticModel?.provider === "finetuned"
            ? applyFinetunedSemanticModel(textAnalysis, semanticModel)
            : fuseSemanticModel(textAnalysis, semanticModel);
        const acousticFused = fuseModalities(semanticFused, speechAnalysis);
        const analysis = fuseSpeechModel(acousticFused, speechModel);

        analysis.dialect = {
          code: requestedDialect.used,
          used: requestedDialect.used,
          requested: requestedDialect.requested,
          supported: requestedDialect.supported,
          mode: requestedDialect.mode,
          calibrated: requestedDialect.calibrated,
          warning: requestedDialect.warning,
        };

        const turnId = body.turn_id ?? session.nextTurnId;
        const stateForTemporal = {
          ...analysis,
          turn_id: turnId,
          timestamp,
        };
        const temporal = calculateTemporal([
          ...session.states,
          stateForTemporal,
        ]);
        const latencyMs = Math.max(0, Math.round(performance.now() - startedAt));

        let status = analysis.status;
        if (
          status === "ok" &&
          !analysis.speech_analysis?.available &&
          !analysis.speech_model?.available
        ) {
          status = "partial";
        }

        const result = {
          schema_version: "1.0",
          request_id: `req-${randomUUID()}`,
          session_id: session.id,
          turn_id: turnId,
          timestamp,
          status,
          decision_mode:
            analysis.dominant_emotion.confidence >= 0.65
              ? "confident"
              : analysis.dominant_emotion.confidence >= 0.4
                ? "tentative"
                : "clarify",
          dominant_emotion: analysis.dominant_emotion,
          emotion_distribution: analysis.emotion_distribution,
          dimensions: analysis.dimensions,
          temporal,
          companion_needs: analysis.companion_needs,
          risk: analysis.risk,
          quality: analysis.quality,
          evidence: analysis.evidence,
          speech_analysis: analysis.speech_analysis ?? null,
          speech_model: analysis.speech_model ?? null,
          semantic_model: analysis.semantic_model ?? null,
          recognized_text: effectiveText || null,
          dialect: analysis.dialect,
          latency_ms: latencyMs,
        };

        sessionStore.appendState(session.id, result);
        sendJson(response, 200, result);
        return;
      }

      const sessionMatch = pathname.match(
        /^\/api\/v1\/emotion\/sessions\/([A-Za-z0-9_-]{1,80})$/,
      );
      if (sessionMatch && request.method === "GET") {
        const session = sessionStore.get(sessionMatch[1]);
        if (!session) {
          sendError(response, 404, "session_not_found", "会话不存在或已过期");
          return;
        }

        sendJson(response, 200, {
          session_id: session.id,
          created_at: new Date(session.createdAt).toISOString(),
          turns: session.states.length,
          states: session.states,
        });
        return;
      }

      if (sessionMatch && request.method === "DELETE") {
        sessionStore.delete(sessionMatch[1]);
        response.writeHead(204, { "Cache-Control": "no-store" });
        response.end();
        return;
      }

      if (pathname.startsWith("/api/")) {
        sendError(response, 404, "api_not_found", "接口不存在");
        return;
      }

      await serveStatic(request, response, pathname);
    } catch (error) {
      if (response.headersSent) {
        response.end();
        return;
      }
      sendError(
        response,
        error.statusCode ?? 500,
        error.code ?? "internal_error",
        error.statusCode ? error.message : "服务内部错误",
      );
    }
  });

  return { server, sessionStore };
}

function startFromCommandLine() {
  const port = Number(process.env.PORT ?? 4173);
  const host = "127.0.0.1";
  const { server } = createEmotionServer({
    modelClient: createLocalModelClient(),
  });

  server.listen(port, host, () => {
    console.log(`Emotion MVP is running at http://${host}:${port}`);
  });

  const shutdown = () => {
    server.close(() => process.exit(0));
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

const invokedPath = process.argv[1] ? resolve(process.argv[1]) : "";
if (invokedPath === fileURLToPath(import.meta.url)) {
  startFromCommandLine();
}

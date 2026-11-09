import assert from "node:assert/strict";
import test from "node:test";

import { createEmotionServer } from "../src/server.js";

async function startTestServer(t, options = {}) {
  const { server, sessionStore } = createEmotionServer(options);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise((resolve) => server.close(resolve)));

  const address = server.address();
  return {
    baseUrl: `http://127.0.0.1:${address.port}`,
    sessionStore,
  };
}

test("serves health and the demo page", async (t) => {
  const { baseUrl } = await startTestServer(t);

  const healthResponse = await fetch(`${baseUrl}/health`);
  const health = await healthResponse.json();
  assert.equal(healthResponse.status, 200);
  assert.equal(health.status, "ok");

  const pageResponse = await fetch(baseUrl);
  const page = await pageResponse.text();
  assert.equal(pageResponse.status, 200);
  assert.match(page, /心迹/);
  assert.match(pageResponse.headers.get("content-security-policy"), /default-src 'self'/);
});

test("creates a session and tracks two turns", async (t) => {
  const { baseUrl } = await startTestServer(t);

  const sessionResponse = await fetch(
    `${baseUrl}/api/v1/emotion/sessions`,
    { method: "POST" },
  );
  const session = await sessionResponse.json();
  assert.equal(sessionResponse.status, 201);
  assert.match(session.session_id, /^sess-/);

  const firstResponse = await fetch(
    `${baseUrl}/api/v1/emotion/turns`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: session.session_id,
        text: "今天还行，就是有点累。",
        dialect: "mandarin",
        speech_features: null,
      }),
    },
  );
  const first = await firstResponse.json();
  assert.equal(firstResponse.status, 200);
  assert.equal(first.turn_id, 1);
  assert.equal(first.status, "partial");
  assert.equal(first.temporal.trend, "insufficient_data");

  const secondResponse = await fetch(
    `${baseUrl}/api/v1/emotion/turns`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: session.session_id,
        text: "最近做什么都提不起劲，心里很难受。",
      }),
    },
  );
  const second = await secondResponse.json();
  assert.equal(secondResponse.status, 200);
  assert.equal(second.turn_id, 2);
  assert.equal(second.temporal.window_turns, 2);
  assert.notEqual(second.temporal.trend, "insufficient_data");

  const sessionStateResponse = await fetch(
    `${baseUrl}/api/v1/emotion/sessions/${session.session_id}`,
  );
  const sessionState = await sessionStateResponse.json();
  assert.equal(sessionState.turns, 2);
  assert.equal(sessionState.states.length, 2);

  const deleteResponse = await fetch(
    `${baseUrl}/api/v1/emotion/sessions/${session.session_id}`,
    { method: "DELETE" },
  );
  assert.equal(deleteResponse.status, 204);

  const missingResponse = await fetch(
    `${baseUrl}/api/v1/emotion/sessions/${session.session_id}`,
  );
  assert.equal(missingResponse.status, 404);
});

test("rejects empty and malformed turn requests", async (t) => {
  const { baseUrl } = await startTestServer(t);

  const emptyResponse = await fetch(
    `${baseUrl}/api/v1/emotion/turns`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "   " }),
    },
  );
  assert.equal(emptyResponse.status, 422);

  const malformedResponse = await fetch(
    `${baseUrl}/api/v1/emotion/turns`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{not-json}",
    },
  );
  assert.equal(malformedResponse.status, 400);
});

test("accepts a speech feature branch and returns multimodal status", async (t) => {
  const { baseUrl } = await startTestServer(t);

  const response = await fetch(
    `${baseUrl}/api/v1/emotion/turns`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: "sess-speech-test",
        text: "明天要答辩了，我一直睡不着，担心会搞砸。",
        asr_confidence: 0.79,
        speech_features: {
          duration_ms: 3200,
          speech_ratio: 0.72,
          mean_db: -22,
          variation_db: 11,
          mean_pitch_hz: 218,
          pitch_variation_hz: 54,
          pause_count: 2,
          clipping_ratio: 0,
        },
      }),
    },
  );
  const result = await response.json();

  assert.equal(response.status, 200);
  assert.equal(result.status, "ok");
  assert.equal(result.speech_analysis.available, true);
  assert.equal(result.speech_analysis.acoustic_hint, "high_activation");
  assert.ok(result.quality.speech > 0.5);
  assert.ok(result.evidence.speech.length >= 3);
});

test("accepts a dialect interface request and marks Mandarin fallback", async (t) => {
  const { baseUrl } = await startTestServer(t);

  const response = await fetch(
    `${baseUrl}/api/v1/emotion/turns`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: "今天有点累。",
        dialect: "cantonese",
      }),
    },
  );
  const payload = await response.json();

  assert.equal(response.status, 200);
  assert.equal(payload.dialect.requested, "cantonese");
  assert.equal(payload.dialect.used, "mandarin");
  assert.equal(payload.dialect.supported, false);
  assert.equal(payload.dialect.mode, "fallback");
  assert.match(payload.dialect.warning, /未作方言校准/);
});

test("fuses local text and speech model adapters when available", async (t) => {
  const calls = [];
  const { baseUrl } = await startTestServer(t, {
    modelClient: {
      async health() {
        return {
          status: "ok",
          text_model: { id: "test-text", ready: true },
          text_finetuned: { id: "test-finetuned", ready: true },
          speech_model: { id: "test-speech", ready: true },
        };
      },
      async analyzeText(text) {
        calls.push(["text", text]);
        return {
          available: true,
          model_id: "test-text",
          device: "cpu",
          predicted_raw: "happy",
          predicted_mapped: "joy",
          latency_ms: 20,
          raw_scores: { happy: 0.9 },
          mapped_distribution: {
            joy: 0.9,
            calm: 0,
            sadness: 0.02,
            anxiety: 0.02,
            anger_irritation: 0.02,
            neutral: 0.04,
          },
        };
      },
      async analyzeFinetuned(text) {
        calls.push(["finetuned", text]);
        return {
          available: true,
          provider: "finetuned",
          model_id: "test-finetuned",
          device: "mps",
          predicted_raw: "anger_irritation",
          predicted_mapped: "anger_irritation",
          latency_ms: 15,
          raw_scores: { anger_irritation: 0.88 },
          mapped_distribution: {
            joy: 0.02,
            calm: 0,
            sadness: 0.03,
            anxiety: 0.05,
            anger_irritation: 0.88,
            neutral: 0.02,
          },
        };
      },
      async analyzeSpeech(audio) {
        calls.push(["speech", audio.length]);
        return {
          available: true,
          model_id: "test-speech",
          device: "cpu",
          emotion_tag: "happy",
          text: "今天太好了。",
          latency_ms: 30,
        };
      },
    },
  });

  const wav = createSilentWav();
  const response = await fetch(`${baseUrl}/api/v1/emotion/turns`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: "事情办成了。",
      dialect: "mandarin",
      speech_audio_base64: wav.toString("base64"),
    }),
  });
  const payload = await response.json();

  assert.equal(response.status, 200);
  assert.equal(payload.status, "ok");
  assert.equal(payload.semantic_model.model_id, "test-finetuned");
  assert.equal(payload.speech_model.model_id, "test-speech");
  assert.equal(calls.length, 2);

  const capabilitiesResponse = await fetch(
    `${baseUrl}/api/v1/emotion/capabilities`,
  );
  const capabilities = await capabilitiesResponse.json();
  assert.equal(capabilities.models.text_model.ready, true);
  assert.equal(capabilities.models.text_finetuned.ready, true);
  assert.equal(capabilities.dialect_extension.behavior, "mandarin_fallback");
});

function createSilentWav() {
  const sampleRate = 16_000;
  const sampleCount = sampleRate;
  const buffer = Buffer.alloc(44 + sampleCount * 2);
  buffer.write("RIFF", 0, "ascii");
  buffer.writeUInt32LE(36 + sampleCount * 2, 4);
  buffer.write("WAVE", 8, "ascii");
  buffer.write("fmt ", 12, "ascii");
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36, "ascii");
  buffer.writeUInt32LE(sampleCount * 2, 40);
  return buffer;
}

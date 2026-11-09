const EMOTION_META = {
  joy: { label: "高兴", glyph: "◡", color: "var(--joy)", sentence: "有些积极、明亮的情绪。" },
  calm: { label: "平静", glyph: "○", color: "var(--calm)", sentence: "情绪整体比较平稳。" },
  sadness: { label: "悲伤", glyph: "◢", color: "var(--sadness)", sentence: "可能正在经历低落或失落。" },
  anxiety: { label: "焦虑", glyph: "◇", color: "var(--anxiety)", sentence: "可能存在担心、紧张或不安。" },
  anger_irritation: { label: "烦躁", glyph: "△", color: "var(--anger)", sentence: "可能正在感到烦躁或不满。" },
  neutral: { label: "中性", glyph: "·", color: "var(--neutral)", sentence: "当前没有明显情绪倾向。" },
};

const TREND_LABELS = {
  improving: "正在缓和",
  stable: "相对稳定",
  worsening: "有所恶化",
  fluctuating: "出现波动",
  insufficient_data: "等待更多轮次",
};

const NEED_LABELS = {
  listen: "希望被倾听",
  company: "需要陪伴",
  practical_help: "需要实际帮助",
  comfort: "适合温和安慰",
  celebrate: "可以共同庆祝",
  clarify: "适合温和追问",
};

const elements = {
  form: document.querySelector("#conversationForm"),
  input: document.querySelector("#textInput"),
  sendButton: document.querySelector("#sendButton"),
  micButton: document.querySelector("#micButton"),
  micLabel: document.querySelector("#micLabel"),
  messages: document.querySelector("#messages"),
  welcomeNote: document.querySelector("#welcomeNote"),
  connectionStatus: document.querySelector("#connectionStatus"),
  resetSession: document.querySelector("#resetSession"),
  modelBadgeText: document.querySelector("#modelBadgeText"),
  riskBanner: document.querySelector("#riskBanner"),
  riskTitle: document.querySelector("#riskTitle"),
  riskDetail: document.querySelector("#riskDetail"),
  emptyState: document.querySelector("#emptyState"),
  analysisPanel: document.querySelector("#analysisPanel"),
  analysisStatus: document.querySelector("#analysisStatus"),
  confidenceRing: document.querySelector("#confidenceRing"),
  emotionGlyph: document.querySelector("#emotionGlyph"),
  primaryEmotion: document.querySelector("#primaryEmotion"),
  confidenceValue: document.querySelector("#confidenceValue"),
  stateSentence: document.querySelector("#stateSentence"),
  dialectStatus: document.querySelector("#dialectStatus"),
  decisionStatus: document.querySelector("#decisionStatus"),
  textQualityBadge: document.querySelector("#textQualityBadge"),
  speechQualityBadge: document.querySelector("#speechQualityBadge"),
  valenceValue: document.querySelector("#valenceValue"),
  valenceMarker: document.querySelector("#valenceMarker"),
  valenceHint: document.querySelector("#valenceHint"),
  arousalValue: document.querySelector("#arousalValue"),
  arousalMarker: document.querySelector("#arousalMarker"),
  arousalHint: document.querySelector("#arousalHint"),
  intensityValue: document.querySelector("#intensityValue"),
  intensityMarker: document.querySelector("#intensityMarker"),
  intensityHint: document.querySelector("#intensityHint"),
  trendChart: document.querySelector("#trendChart"),
  trendLabel: document.querySelector("#trendLabel"),
  stabilityValue: document.querySelector("#stabilityValue"),
  durationValue: document.querySelector("#durationValue"),
  distributionList: document.querySelector("#distributionList"),
  needsList: document.querySelector("#needsList"),
  evidenceList: document.querySelector("#evidenceList"),
  sessionLabel: document.querySelector("#sessionLabel"),
};

const history = [];
let currentSessionId = createSessionId();
let busy = false;
let recognition = null;
let voiceActive = false;
let recognitionActive = false;
let audioCapture = null;
let captureRequestId = 0;
let maxCaptureTimer = null;
let lastSpeechFeatures = null;
let lastSpeechCapturedAt = 0;
let lastTranscript = "";
let lastSpeechAudio = null;
let capabilityRefreshAttempts = 0;
let capabilityRefreshTimer = null;

function createSessionId() {
  if (globalThis.crypto?.randomUUID) {
    return `sess-${globalThis.crypto.randomUUID()}`;
  }
  return `sess-local-${Date.now()}`;
}

function formatTime() {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());
}

function appendMessage(text, kind = "user") {
  const article = document.createElement("article");
  article.className = `message ${kind}`;
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  article.append(paragraph);

  if (kind === "user") {
    const meta = document.createElement("span");
    meta.className = "message-meta";
    meta.textContent = formatTime();
    article.append(meta);
  }

  elements.messages.append(article);
  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function setBusy(nextBusy) {
  busy = nextBusy;
  elements.sendButton.disabled = nextBusy;
  elements.sendButton.textContent = nextBusy ? "分析中…" : "分析情绪";
  elements.input.disabled = nextBusy;
  elements.micButton.disabled = nextBusy;
}

function setConnection(text, isError = false) {
  elements.connectionStatus.textContent = text;
  elements.connectionStatus.style.color = isError ? "var(--danger)" : "";
}

function getRecentSpeechFeatures() {
  if (!lastSpeechFeatures) return null;
  if (Date.now() - lastSpeechCapturedAt > 120_000) {
    lastSpeechFeatures = null;
    lastSpeechAudio = null;
    return null;
  }
  return lastSpeechFeatures;
}

function getRecentSpeechAudio() {
  if (!lastSpeechAudio || Date.now() - lastSpeechCapturedAt > 120_000) {
    lastSpeechAudio = null;
    return null;
  }
  return lastSpeechAudio;
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      const result = String(reader.result ?? "");
      resolve(result.includes(",") ? result.split(",")[1] : result);
    });
    reader.addEventListener("error", () => reject(reader.error));
    reader.readAsDataURL(blob);
  });
}

async function submitText(text, { allowSpeech = true } = {}) {
  if (voiceActive) {
    stopVoiceCapture();
  }
  const normalized = text.trim();
  const speechFeatures = allowSpeech ? getRecentSpeechFeatures() : null;
  const speechAudio = allowSpeech ? getRecentSpeechAudio() : null;
  if ((!normalized && !speechFeatures && !speechAudio) || busy) return;

  elements.welcomeNote.hidden = true;
  appendMessage(normalized || "（仅分析语音声学特征）", "user");
  elements.input.value = "";
  setBusy(true);
  setConnection(
    speechFeatures
      ? "正在融合文本、声学特征与对话上下文…"
      : "正在分析文本与对话上下文…",
  );

  const transcriptFromVoice =
    Boolean(normalized) && lastTranscript.trim() === normalized;
  const speechAudioBase64 = speechAudio
    ? await blobToBase64(speechAudio)
    : null;

  try {
    const response = await fetch("/api/v1/emotion/turns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: currentSessionId,
        text: normalized,
        dialect: "mandarin",
        asr_confidence: transcriptFromVoice ? 0.78 : 0.98,
        speech_features: speechFeatures,
        speech_audio_base64: speechAudioBase64,
      }),
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error?.message ?? "识别服务返回了错误");
    }

    history.push(payload);
    renderAnalysis(payload);
    appendMessage(
      `状态更新：${EMOTION_META[payload.dominant_emotion.label].label} · 第 ${payload.turn_id} 轮`,
      "system",
    );
    const hasSpeechResult =
      payload.speech_analysis?.available || payload.speech_model?.available;
    const mode = hasSpeechResult ? "文本 + 语音" : "文本模式";
    setConnection(`已返回 · ${payload.latency_ms} ms · ${mode}`);
  } catch (error) {
    appendMessage(error.message, "error");
    setConnection("分析失败，请确认本地服务仍在运行。", true);
  } finally {
    lastSpeechFeatures = null;
    lastSpeechCapturedAt = 0;
    lastTranscript = "";
    lastSpeechAudio = null;
    setBusy(false);
    elements.input.focus();
  }
}

function renderAnalysis(result) {
  const emotion = EMOTION_META[result.dominant_emotion.label] ?? EMOTION_META.neutral;
  const { dimensions, temporal } = result;
  const confidencePercent = Math.round(result.dominant_emotion.confidence * 100);

  elements.emptyState.hidden = true;
  elements.analysisPanel.hidden = false;
  elements.analysisStatus.textContent =
    result.speech_analysis?.available || result.speech_model?.available
      ? "文本 + 语音"
      : result.status === "partial"
        ? "文本模式"
        : "分析完成";
  elements.analysisStatus.classList.add("ready");
  document.documentElement.style.setProperty("--state-color", emotion.color);

  elements.confidenceRing.style.setProperty(
    "--confidence-angle",
    `${confidencePercent * 3.6}deg`,
  );
  elements.emotionGlyph.textContent = emotion.glyph;
  elements.primaryEmotion.textContent = emotion.label;
  elements.confidenceValue.textContent = `置信度 ${confidencePercent}%`;
  elements.stateSentence.textContent =
    result.risk.level === "urgent"
      ? "检测到明确风险线索，情感分类不能替代安全判断。"
      : result.risk.level === "watch"
        ? "检测到需要继续关注的线索，建议温和确认。"
        : confidencePercent < 45
          ? `${emotion.sentence} 当前判断置信度较低，更适合温和确认。`
          : emotion.sentence;
  elements.dialectStatus.textContent = "普通话 · zh-CN";
  const decisionLabels = {
    confident: "高置信度",
    tentative: "建议确认",
    clarify: "需要澄清",
  };
  elements.decisionStatus.textContent =
    decisionLabels[result.decision_mode] ?? "建议确认";
  elements.textQualityBadge.textContent = result.semantic_model?.available
    ? result.semantic_model.model_id?.includes("Qwen")
      ? "Qwen 语义在线"
      : "文本模型在线"
    : `文本输入 ${Math.round(result.quality.text * 100)}%`;
  elements.speechQualityBadge.textContent =
    result.quality.speech === null || result.quality.speech === undefined
      ? "语音未采集"
      : `语音 ${Math.round(result.quality.speech * 100)}%`;
  elements.speechQualityBadge.classList.toggle(
    "muted",
    result.quality.speech === null || result.quality.speech === undefined,
  );

  elements.valenceValue.textContent = formatSigned(dimensions.valence);
  elements.valenceHint.textContent =
    dimensions.valence > 0.2
      ? "偏积极"
      : dimensions.valence < -0.2
        ? "偏难受"
        : "接近中性";
  elements.valenceMarker.style.setProperty(
    "--metric-position",
    `${((dimensions.valence + 1) / 2) * 100}%`,
  );

  elements.arousalValue.textContent = dimensions.arousal.toFixed(2);
  elements.arousalHint.textContent =
    dimensions.arousal > 0.66
      ? "偏高唤醒"
      : dimensions.arousal < 0.35
        ? "较为平静"
        : "中等唤醒";
  elements.arousalMarker.style.setProperty(
    "--metric-position",
    `${dimensions.arousal * 100}%`,
  );

  elements.intensityValue.textContent = dimensions.intensity.toFixed(2);
  elements.intensityHint.textContent =
    dimensions.intensity > 0.66
      ? "表达明显"
      : dimensions.intensity < 0.35
        ? "表达轻微"
        : "强度适中";
  elements.intensityMarker.style.setProperty(
    "--metric-position",
    `${dimensions.intensity * 100}%`,
  );

  renderRisk(result.risk);
  renderDistribution(result.emotion_distribution);
  renderNeeds(result.companion_needs);
  renderEvidence([
    ...(result.evidence.text ?? []),
    ...(result.evidence.speech ?? []),
  ]);
  renderTrend();

  elements.trendLabel.textContent = TREND_LABELS[temporal.trend] ?? temporal.trend;
  elements.stabilityValue.textContent = `稳定性 ${Math.round(temporal.stability * 100)}%`;
  elements.durationValue.textContent =
    temporal.low_valence_duration_s > 0
      ? `低效价持续 ${formatDuration(temporal.low_valence_duration_s)}`
      : "本轮未检测到持续低效价";
  elements.sessionLabel.textContent = `临时会话 · ${history.length} 轮 · ${currentSessionId.slice(-8)}`;
}

function renderRisk(risk) {
  if (risk.level === "none") {
    elements.riskBanner.hidden = true;
    elements.riskBanner.classList.remove("urgent");
    return;
  }

  elements.riskBanner.hidden = false;
  elements.riskBanner.classList.toggle("urgent", risk.level === "urgent");
  elements.riskTitle.textContent =
    risk.level === "urgent" ? "需要立即关注" : "建议继续关注";
  elements.riskDetail.textContent =
    risk.level === "urgent"
      ? "检测到明确的紧急风险线索。演示系统不具备救援能力，应进入人工安全流程。"
      : "检测到间接风险或明显的自我否定线索，建议温和追问并避免轻视。";
}

function renderDistribution(distribution) {
  elements.distributionList.replaceChildren();
  const sorted = Object.entries(distribution).sort((left, right) => right[1] - left[1]);

  for (const [label, probability] of sorted) {
    const meta = EMOTION_META[label];
    const row = document.createElement("div");
    row.className = "distribution-row";

    const name = document.createElement("span");
    name.className = "distribution-label";
    name.textContent = meta.label;

    const track = document.createElement("div");
    track.className = "distribution-track";
    track.setAttribute("role", "progressbar");
    track.setAttribute("aria-label", `${meta.label}概率`);
    track.setAttribute("aria-valuemin", "0");
    track.setAttribute("aria-valuemax", "100");
    track.setAttribute("aria-valuenow", String(Math.round(probability * 100)));
    const fill = document.createElement("span");
    fill.className = "distribution-fill";
    fill.style.setProperty("--distribution-width", `${probability * 100}%`);
    fill.style.setProperty("--bar-color", meta.color);
    track.append(fill);

    const value = document.createElement("span");
    value.className = "distribution-value";
    value.textContent = `${Math.round(probability * 100)}%`;

    row.append(name, track, value);
    elements.distributionList.append(row);
  }
}

function renderNeeds(needs) {
  elements.needsList.replaceChildren();
  if (!needs.length) {
    const empty = document.createElement("span");
    empty.className = "empty-tag";
    empty.textContent = "暂无明确线索";
    elements.needsList.append(empty);
    return;
  }

  for (const need of needs) {
    const tag = document.createElement("span");
    tag.className = "need-tag";
    tag.textContent = `${NEED_LABELS[need.label] ?? need.label} · ${Math.round(need.confidence * 100)}%`;
    elements.needsList.append(tag);
  }
}

function renderEvidence(items) {
  elements.evidenceList.replaceChildren();
  const visibleItems = items.length ? items : ["未发现明显文本线索"];
  for (const item of visibleItems.slice(0, 5)) {
    const listItem = document.createElement("li");
    listItem.textContent = item;
    elements.evidenceList.append(listItem);
  }
}

function renderTrend() {
  const svg = elements.trendChart;
  for (const child of [...svg.children]) {
    if (!child.classList.contains("trend-baseline")) child.remove();
  }

  if (history.length === 0) return;

  const points = history.slice(-6).map((item, index, all) => {
    const x = all.length === 1 ? 160 : 16 + (index / (all.length - 1)) * 288;
    const y = 52 - item.dimensions.valence * 34;
    return { x, y };
  });

  if (points.length > 1) {
    const polyline = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    polyline.setAttribute("class", "trend-line");
    polyline.setAttribute("points", points.map(({ x, y }) => `${x},${y}`).join(" "));
    svg.append(polyline);
  }

  for (const point of points) {
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("class", "trend-point");
    circle.setAttribute("cx", point.x);
    circle.setAttribute("cy", point.y);
    circle.setAttribute("r", "3.5");
    svg.append(circle);
  }

  const topLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
  topLabel.setAttribute("class", "trend-axis-label");
  topLabel.setAttribute("x", "12");
  topLabel.setAttribute("y", "18");
  topLabel.textContent = "积极";

  const bottomLabel = document.createElementNS("http://www.w3.org/2000/svg", "text");
  bottomLabel.setAttribute("class", "trend-axis-label");
  bottomLabel.setAttribute("x", "12");
  bottomLabel.setAttribute("y", "96");
  bottomLabel.textContent = "难受";
  svg.append(topLabel, bottomLabel);
}

function formatSigned(value) {
  if (Math.abs(value) < 0.005) return "0.00";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}

function formatDuration(seconds) {
  if (seconds < 60) return `${seconds} 秒`;
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
}

function setVoiceUnavailable(message) {
  elements.micButton.disabled = true;
  elements.micLabel.textContent = "不可用";
  elements.micButton.title = message;
}

function setupSpeechRecognition() {
  const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) return;

  recognition = new SpeechRecognition();
  recognition.lang = "zh-CN";
  recognition.interimResults = true;
  recognition.continuous = false;

  recognition.addEventListener("start", () => {
    recognitionActive = true;
  });

  recognition.addEventListener("result", (event) => {
    let transcript = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      transcript += event.results[index][0].transcript;
    }
    lastTranscript = transcript.trim();
    elements.input.value = lastTranscript;
  });

  recognition.addEventListener("end", () => {
    recognitionActive = false;
    if (voiceActive && audioCapture) {
      elements.micLabel.textContent = "采样中";
    } else if (voiceActive) {
      window.setTimeout(() => {
        if (voiceActive && !audioCapture && !recognitionActive) {
          stopVoiceCapture();
        }
      }, 250);
    }
  });

  recognition.addEventListener("error", (event) => {
    if (event.error !== "aborted" && event.error !== "no-speech") {
      setConnection(
        "浏览器语音转写未完成，可继续录音后手动输入文字。",
        true,
      );
    }
    if (!audioCapture) {
      window.setTimeout(() => {
        if (voiceActive && !audioCapture && !recognitionActive) {
          stopVoiceCapture();
        }
      }, 250);
    }
  });
}

function estimatePitch(samples, sampleRate) {
  let energy = 0;
  for (const sample of samples) energy += sample * sample;
  const rms = Math.sqrt(energy / samples.length);
  if (rms < 0.008) return 0;

  const minimumLag = Math.max(2, Math.floor(sampleRate / 420));
  const maximumLag = Math.min(
    Math.floor(sampleRate / 70),
    Math.floor(samples.length / 2),
  );
  let bestLag = 0;
  let bestCorrelation = 0;

  for (let lag = minimumLag; lag <= maximumLag; lag += 1) {
    let correlation = 0;
    let normalization = 0;
    for (let index = 0; index < samples.length - lag; index += 2) {
      correlation += samples[index] * samples[index + lag];
      normalization += samples[index] ** 2;
    }
    const normalized = normalization > 0 ? correlation / normalization : 0;
    if (normalized > bestCorrelation) {
      bestCorrelation = normalized;
      bestLag = lag;
    }
  }

  return bestCorrelation >= 0.32 && bestLag > 0
    ? sampleRate / bestLag
    : 0;
}

function percentile(sortedValues, fraction) {
  if (!sortedValues.length) return 0;
  const index = Math.min(
    sortedValues.length - 1,
    Math.max(0, Math.floor((sortedValues.length - 1) * fraction)),
  );
  return sortedValues[index];
}

function summarizeSpeechFrames(frames, durationMs) {
  if (!frames.length || durationMs < 200) return null;

  const energies = frames.map((frame) => frame.db);
  const sortedEnergies = [...energies].sort((left, right) => left - right);
  const noiseFloor = percentile(sortedEnergies, 0.15);
  const voicedThreshold = Math.max(-56, noiseFloor + 7);
  const voicedFrames = frames.filter((frame) => frame.db >= voicedThreshold);
  const speechRatio = voicedFrames.length / frames.length;

  const voicedEnergy = voicedFrames.length
    ? voicedFrames.reduce((sum, frame) => sum + frame.db, 0) /
      voicedFrames.length
    : noiseFloor;
  const energyVariance = voicedFrames.length
    ? voicedFrames.reduce(
        (sum, frame) => sum + (frame.db - voicedEnergy) ** 2,
        0,
      ) / voicedFrames.length
    : 0;

  const pitches = voicedFrames
    .map((frame) => frame.pitch)
    .filter((pitch) => pitch >= 70 && pitch <= 420);
  const meanPitch = pitches.length
    ? pitches.reduce((sum, pitch) => sum + pitch, 0) / pitches.length
    : 0;
  const pitchVariance = pitches.length
    ? pitches.reduce((sum, pitch) => sum + (pitch - meanPitch) ** 2, 0) /
      pitches.length
    : 0;

  let silenceStartedAt = null;
  let pauseCount = 0;
  for (const frame of frames) {
    if (frame.db >= voicedThreshold) {
      if (
        silenceStartedAt !== null &&
        frame.timestamp - silenceStartedAt >= 180
      ) {
        pauseCount += 1;
      }
      silenceStartedAt = null;
    } else if (silenceStartedAt === null) {
      silenceStartedAt = frame.timestamp;
    }
  }

  const clippingRatio =
    frames.reduce((sum, frame) => sum + frame.clippedRatio, 0) /
    frames.length;

  return {
    duration_ms: Math.round(durationMs),
    speech_ratio: Math.min(1, Math.max(0, speechRatio)),
    mean_db: voicedEnergy,
    variation_db: Math.sqrt(energyVariance),
    mean_pitch_hz: meanPitch,
    pitch_variation_hz: Math.sqrt(pitchVariance),
    pause_count: pauseCount,
    clipping_ratio: Math.min(1, Math.max(0, clippingRatio)),
  };
}

function encodePcmAsWav(chunks, inputSampleRate, targetSampleRate = 16_000) {
  const totalSamples = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  if (totalSamples === 0) return null;

  const input = new Float32Array(totalSamples);
  let offset = 0;
  for (const chunk of chunks) {
    input.set(chunk, offset);
    offset += chunk.length;
  }

  const ratio = inputSampleRate / targetSampleRate;
  const outputLength = Math.max(1, Math.floor(input.length / ratio));
  const pcm = new Int16Array(outputLength);
  for (let index = 0; index < outputLength; index += 1) {
    const start = Math.floor(index * ratio);
    const end = Math.max(start + 1, Math.floor((index + 1) * ratio));
    let sum = 0;
    for (let sourceIndex = start; sourceIndex < end; sourceIndex += 1) {
      sum += input[sourceIndex] ?? 0;
    }
    const sample = Math.max(-1, Math.min(1, sum / (end - start)));
    pcm[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }

  const buffer = new ArrayBuffer(44 + pcm.byteLength);
  const view = new DataView(buffer);
  const writeAscii = (position, value) => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(position + index, value.charCodeAt(index));
    }
  };
  writeAscii(0, "RIFF");
  view.setUint32(4, 36 + pcm.byteLength, true);
  writeAscii(8, "WAVE");
  writeAscii(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, targetSampleRate, true);
  view.setUint32(28, targetSampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeAscii(36, "data");
  view.setUint32(40, pcm.byteLength, true);
  new Int16Array(buffer, 44).set(pcm);

  return new Blob([buffer], { type: "audio/wav" });
}

function releaseAudioCapture(capture) {
  if (!capture) return;
  window.clearInterval(capture.sampleTimer);
  if (capture.processor) {
    capture.processor.onaudioprocess = null;
    capture.processor.disconnect();
  }
  capture.silentGain?.disconnect();
  for (const track of capture.stream.getTracks()) track.stop();
  capture.context.close().catch(() => {});
}

async function startAudioCapture(requestId) {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("microphone_not_supported");
  }

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: false,
    },
  });

  if (!voiceActive || requestId !== captureRequestId) {
    for (const track of stream.getTracks()) track.stop();
    return;
  }

  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) {
    for (const track of stream.getTracks()) track.stop();
    throw new Error("audio_context_not_supported");
  }

  const context = new AudioContextClass();
  await context.resume();
  const source = context.createMediaStreamSource(stream);
  const analyser = context.createAnalyser();
  analyser.fftSize = 2048;
  analyser.smoothingTimeConstant = 0.25;
  const processor = context.createScriptProcessor(4096, 1, 1);
  const silentGain = context.createGain();
  silentGain.gain.value = 0;
  source.connect(analyser);
  source.connect(processor);
  analyser.connect(silentGain);
  processor.connect(silentGain);
  silentGain.connect(context.destination);

  const samples = new Float32Array(analyser.fftSize);
  const capture = {
    requestId,
    stream,
    context,
    analyser,
    samples,
    frames: [],
    pcmChunks: [],
    processor,
    silentGain,
    startedAt: performance.now(),
    lastSampleAt: 0,
    sampleTimer: null,
  };
  processor.onaudioprocess = (event) => {
    if (!voiceActive || audioCapture !== capture) return;
    capture.pcmChunks.push(
      new Float32Array(event.inputBuffer.getChannelData(0)),
    );
  };
  audioCapture = capture;
  elements.micLabel.textContent = "录音中";

  capture.sampleTimer = window.setInterval(() => {
    if (!voiceActive || audioCapture !== capture) return;
    const now = performance.now();
    if (now - capture.lastSampleAt < 75) return;
    capture.lastSampleAt = now;

    analyser.getFloatTimeDomainData(samples);
    let energy = 0;
    let clippedSamples = 0;
    for (const sample of samples) {
      energy += sample * sample;
      if (Math.abs(sample) >= 0.96) clippedSamples += 1;
    }
    const rms = Math.sqrt(energy / samples.length);
    const db = 20 * Math.log10(Math.max(rms, 1e-8));
    capture.frames.push({
      timestamp: now - capture.startedAt,
      db,
      pitch: estimatePitch(samples, context.sampleRate),
      clippedRatio: clippedSamples / samples.length,
    });
  }, 40);
}

function finishAudioCapture() {
  if (!audioCapture) return null;
  const capture = audioCapture;
  audioCapture = null;
  const durationMs = performance.now() - capture.startedAt;
  const features = summarizeSpeechFrames(capture.frames, durationMs);
  const audioBlob = encodePcmAsWav(
    capture.pcmChunks,
    capture.context.sampleRate,
  );
  releaseAudioCapture(capture);
  return { features, audioBlob };
}

function stopVoiceCapture() {
  const hadVoiceSession = voiceActive || audioCapture || recognitionActive;
  if (!hadVoiceSession) return;

  voiceActive = false;
  captureRequestId += 1;
  window.clearTimeout(maxCaptureTimer);
  maxCaptureTimer = null;

  if (recognitionActive) {
    try {
      recognition.stop();
    } catch {
      // The recognition session may already have ended.
    }
  }
  recognitionActive = false;

  const captureResult = finishAudioCapture();
  const features = captureResult?.features ?? null;
  lastSpeechAudio = captureResult?.audioBlob ?? null;
  if (features) {
    lastSpeechFeatures = features;
    lastSpeechCapturedAt = Date.now();
    setConnection(
      `语音特征已捕获 · 有效语音 ${Math.round(features.speech_ratio * 100)}% · 点击分析情绪`,
    );
  } else {
    setConnection("本轮未取得可用声学特征，可继续使用文本分析。");
  }

  elements.micButton.setAttribute("aria-pressed", "false");
  elements.micLabel.textContent = "语音";
  elements.input.placeholder = "比如：最近总觉得自己做得不够好……";
  elements.input.focus();
}

async function startVoiceCapture() {
  if (busy || voiceActive) return;

  const supportsMicrophone = Boolean(navigator.mediaDevices?.getUserMedia);
  if (!supportsMicrophone && !recognition) {
    setVoiceUnavailable("当前浏览器不支持语音或麦克风采样，可直接键入文本");
    return;
  }

  voiceActive = true;
  const requestId = ++captureRequestId;
  lastSpeechFeatures = null;
  lastSpeechCapturedAt = 0;
  lastTranscript = "";
  lastSpeechAudio = null;
  lastSpeechAudio = null;
  elements.micButton.setAttribute("aria-pressed", "true");
  elements.micLabel.textContent = "准备中";
  elements.input.placeholder = "正在聆听，再点一次结束…";
  setConnection("正在请求麦克风并采集声学特征…");

  let audioPending = false;
  if (supportsMicrophone) {
    audioPending = true;
    startAudioCapture(requestId).catch(() => {
      if (requestId === captureRequestId && voiceActive) {
        elements.micLabel.textContent = "转写中";
        setConnection("麦克风采样不可用，继续尝试浏览器语音转写。", true);
      }
    });
  }

  let recognitionPending = false;
  if (recognition) {
    try {
      recognition.start();
      recognitionPending = true;
    } catch {
      setConnection("语音转写未启动，仍在采集声学特征。", true);
    }
  }

  if (!audioPending && !recognitionPending) {
    stopVoiceCapture();
    setVoiceUnavailable("当前浏览器无法开始语音采集，可直接键入文本");
    return;
  }

  maxCaptureTimer = window.setTimeout(() => {
    if (voiceActive) stopVoiceCapture();
  }, 60_000);
}

async function resetSession() {
  if (busy) return;
  if (voiceActive) stopVoiceCapture();
  const oldSessionId = currentSessionId;
  currentSessionId = createSessionId();
  history.length = 0;
  lastSpeechFeatures = null;
  lastSpeechCapturedAt = 0;
  lastTranscript = "";
  elements.messages.replaceChildren();
  elements.welcomeNote.hidden = false;
  elements.emptyState.hidden = false;
  elements.analysisPanel.hidden = true;
  elements.analysisStatus.textContent = "等待输入";
  elements.analysisStatus.classList.remove("ready");
  elements.riskBanner.hidden = true;
  elements.input.value = "";
  elements.sessionLabel.textContent = "新的本地临时会话";
  setConnection("新会话已建立，等待输入。");
  elements.input.focus();

  try {
    await fetch(`/api/v1/emotion/sessions/${encodeURIComponent(oldSessionId)}`, {
      method: "DELETE",
    });
  } catch {
    // The old session is memory-only and will expire even if cleanup fails.
  }
}

elements.form.addEventListener("submit", (event) => {
  event.preventDefault();
  submitText(elements.input.value);
});

elements.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    submitText(elements.input.value);
  }
});

for (const chip of document.querySelectorAll("[data-text]")) {
  chip.addEventListener("click", () =>
    submitText(chip.dataset.text, { allowSpeech: false }),
  );
}

elements.micButton.addEventListener("click", () => {
  if (elements.micButton.getAttribute("aria-pressed") === "true") {
    stopVoiceCapture();
  } else {
    startVoiceCapture();
  }
});

elements.resetSession.addEventListener("click", resetSession);

async function checkHealth() {
  try {
    const [response, capabilitiesResponse] = await Promise.all([
      fetch("/health", { headers: { Accept: "application/json" } }),
      fetch("/api/v1/emotion/capabilities", {
        headers: { Accept: "application/json" },
      }),
    ]);
    const payload = await response.json();
    if (!response.ok || payload.status !== "ok") throw new Error("服务未就绪");
    const capabilities = capabilitiesResponse.ok
      ? await capabilitiesResponse.json()
      : null;
    const textReady =
      capabilities?.models?.text_finetuned?.ready ||
      capabilities?.models?.text_model?.ready;
    const speechReady = capabilities?.models?.speech_model?.ready;
    const speechEmotionReady =
      capabilities?.models?.speech_emotion_model?.ready;
    if (textReady && speechReady && speechEmotionReady) {
      elements.modelBadgeText.textContent = "本地三模型";
    } else if (textReady && speechReady) {
      elements.modelBadgeText.textContent = "本地双模型";
    } else if (textReady) {
      elements.modelBadgeText.textContent = "文本模型 + 规则";
    } else {
      elements.modelBadgeText.textContent = "规则回退";
    }
    setConnection("本地服务已连接 · 音频只在当前电脑处理");
    if (
      !(textReady && speechReady && speechEmotionReady) &&
      capabilityRefreshAttempts < 3
    ) {
      capabilityRefreshAttempts += 1;
      window.clearTimeout(capabilityRefreshTimer);
      capabilityRefreshTimer = window.setTimeout(checkHealth, 4_000);
    }
  } catch {
    setConnection("本地服务未连接，请运行 npm start。", true);
  }
}

setupSpeechRecognition();
if (!recognition && !navigator.mediaDevices?.getUserMedia) {
  setVoiceUnavailable("当前浏览器不支持语音输入，可直接键入文本");
}
checkHealth();
elements.input.focus();

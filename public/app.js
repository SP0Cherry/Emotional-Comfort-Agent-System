// ==================== State ====================
let currentSessionId = null;
let personas = [];
let config = {};
let recognition = null;
let isRecording = false;
let audioContext = null;
let mediaRecorder = null;
let audioChunks = [];

const API = ""; // same origin

// ==================== DOM Elements ====================
const $ = (id) => document.getElementById(id);
const sessionListEl = $("sessionList");
const messagesEl = $("messages");
const emptyStateEl = $("emptyState");
const messageInputEl = $("messageInput");
const sendBtnEl = $("sendBtn");
const voiceBtnEl = $("voiceBtn");
const voiceStatusEl = $("voiceStatus");
const asrEngineSelectEl = $("asrEngineSelect");
const personaSelectEl = $("personaSelect");
const emotionBadgeEl = $("emotionBadge");
const emotionLabelEl = $("emotionLabel");
const emotionRiskEl = $("emotionRisk");
const newSessionBtnEl = $("newSessionBtn");
const settingsBtnEl = $("settingsBtn");
const settingsModalEl = $("settingsModal");
const closeSettingsBtnEl = $("closeSettingsBtn");
const saveConfigBtnEl = $("saveConfigBtn");

// ==================== API helpers ====================
async function apiGet(path) {
  const resp = await fetch(`${API}${path}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

async function apiPost(path, body) {
  const resp = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
  return data;
}

async function apiPut(path, body) {
  const resp = await fetch(`${API}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
  return data;
}

async function apiDelete(path) {
  const resp = await fetch(`${API}${path}`, { method: "DELETE" });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
}

// ==================== Sessions ====================
async function loadSessions() {
  try {
    const { sessions } = await apiGet("/api/sessions");
    renderSessionList(sessions);
  } catch (e) {
    console.error("加载会话失败", e);
  }
}

function renderSessionList(sessions) {
  sessionListEl.innerHTML = "";
  if (sessions.length === 0) {
    sessionListEl.innerHTML =
      '<p style="padding:12px;color:#999;font-size:13px;">暂无对话，点击上方新建</p>';
    return;
  }
  for (const s of sessions) {
    const item = document.createElement("div");
    item.className = "session-item" + (s.id === currentSessionId ? " active" : "");
    item.innerHTML = `
      <span class="title">${escapeHtml(s.title || "新对话")}</span>
      <button class="delete-btn" title="删除">×</button>
    `;
    item.querySelector(".title").addEventListener("click", () =>
      switchSession(s.id),
    );
    item.querySelector(".delete-btn").addEventListener("click", async (e) => {
      e.stopPropagation();
      if (confirm(`删除对话"${s.title}"？`)) {
        await apiDelete(`/api/sessions/${s.id}`);
        if (currentSessionId === s.id) {
          currentSessionId = null;
          messagesEl.innerHTML = "";
          emptyStateEl.classList.remove("hidden");
        }
        loadSessions();
      }
    });
    sessionListEl.appendChild(item);
  }
}

async function newSession() {
  try {
    const now = new Date();
    const title = `对话 ${now.getMonth() + 1}/${now.getDate()} ${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
    const session = await apiPost("/api/sessions", { title });
    await switchSession(session.id);
    loadSessions();
  } catch (e) {
    console.error("创建会话失败", e);
    alert("创建失败：" + e.message);
  }
}

async function switchSession(id) {
  currentSessionId = id;
  emptyStateEl.classList.add("hidden");
  messagesEl.innerHTML = "";
  emotionBadgeEl.classList.add("hidden");
  try {
    const session = await apiGet(`/api/sessions/${id}`);
    // Set persona
    if (session.personaId) {
      personaSelectEl.value = session.personaId;
    }
    // Render messages
    for (const msg of session.messages || []) {
      renderMessage(msg);
    }
    loadSessions();
  } catch (e) {
    console.error("加载会话失败", e);
  }
}

// ==================== Messages ====================
function renderMessage(msg) {
  const div = document.createElement("div");
  div.className = `message ${msg.role}`;
  const avatar = msg.role === "user" ? "🧑" : "🤖";
  let emotionTag = "";
  if (msg.emotion) {
    const cn = {
      joy: "高兴",
      calm: "平静",
      sadness: "悲伤",
      anxiety: "焦虑",
      anger_irritation: "烦躁",
      neutral: "中性",
    };
    emotionTag = `<div class="emotion-tag">情绪：${cn[msg.emotion.dominantEmotion] || msg.emotion.dominantEmotion}</div>`;
  }
  div.innerHTML = `
    <div class="avatar">${avatar}</div>
    <div class="bubble">${escapeHtml(msg.content)}${emotionTag}</div>
  `;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function showTypingIndicator() {
  const div = document.createElement("div");
  div.className = "message assistant";
  div.id = "typingIndicator";
  div.innerHTML = `
    <div class="avatar">🤖</div>
    <div class="bubble"><div class="typing-indicator"><span></span><span></span><span></span></div></div>
  `;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function removeTypingIndicator() {
  const el = $("typingIndicator");
  if (el) el.remove();
}

async function sendMessage() {
  const text = messageInputEl.value.trim();
  if (!text) return;
  // 无会话时自动创建一个
  if (!currentSessionId) {
    await newSession();
    if (!currentSessionId) return;
  }
  messageInputEl.value = "";
  renderMessage({ role: "user", content: text });
  showTypingIndicator();
  try {
    const result = await apiPost(`/api/sessions/${currentSessionId}/messages`, {
      text,
    });
    removeTypingIndicator();
    renderMessage({
      role: "assistant",
      content: result.reply,
    });
    // Update emotion badge
    if (result.emotion && result.emotion.available) {
      updateEmotionBadge(result.emotion);
    } else {
      emotionBadgeEl.classList.add("hidden");
    }
  } catch (e) {
    removeTypingIndicator();
    renderMessage({ role: "assistant", content: "抱歉，我出了点问题：" + e.message });
    console.error("发送失败", e);
  }
}

function updateEmotionBadge(emotion) {
  const cn = {
    joy: "高兴",
    calm: "平静",
    sadness: "悲伤",
    anxiety: "焦虑",
    anger_irritation: "烦躁",
    neutral: "中性",
  };
  const riskCn = { none: "", watch: "⚠ 关注", urgent: "🚨 紧急" };
  emotionLabelEl.textContent = `情绪：${cn[emotion.dominantEmotion] || emotion.dominantEmotion}`;
  emotionRiskEl.textContent = riskCn[emotion.risk] || "";
  emotionBadgeEl.className = "emotion-badge";
  if (emotion.risk === "watch") emotionBadgeEl.classList.add("risk-watch");
  if (emotion.risk === "urgent") emotionBadgeEl.classList.add("risk-urgent");
  emotionBadgeEl.classList.remove("hidden");
}

// ==================== Voice Input ====================
async function toggleVoice() {
  const engine = asrEngineSelectEl.value;
  if (engine === "web-speech") {
    toggleWebSpeech();
  } else {
    toggleBailianRecording();
  }
}

function toggleWebSpeech() {
  const SR =
    window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    alert("当前浏览器不支持 Web Speech API，请使用 Chrome 或切换到百炼 ASR");
    return;
  }
  if (isRecording) {
    recognition.stop();
    return;
  }
  recognition = new SR();
  recognition.lang = "zh-CN";
  recognition.continuous = false;
  recognition.interimResults = false;

  recognition.onstart = () => {
    isRecording = true;
    voiceBtnEl.classList.add("recording");
    voiceStatusEl.textContent = "🎙 正在聆听...";
    voiceStatusEl.classList.remove("hidden");
  };
  recognition.onresult = (e) => {
    const text = e.results[0][0].transcript;
    messageInputEl.value = text;
    voiceStatusEl.textContent = `识别结果：${text}`;
  };
  recognition.onerror = (e) => {
    voiceStatusEl.textContent = "识别失败：" + e.error;
  };
  recognition.onend = () => {
    isRecording = false;
    voiceBtnEl.classList.remove("recording");
    setTimeout(() => voiceStatusEl.classList.add("hidden"), 2000);
  };
  recognition.start();
}

async function toggleBailianRecording() {
  if (isRecording) {
    mediaRecorder.stop();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioContext = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: 16000,
    });
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    audioChunks = [];

    processor.onaudioprocess = (e) => {
      const data = e.inputBuffer.getChannelData(0);
      audioChunks.push(new Float32Array(data));
    };

    source.connect(processor);
    processor.connect(audioContext.destination);

    isRecording = true;
    voiceBtnEl.classList.add("recording");
    voiceStatusEl.textContent = "🎙 正在录音...（点击停止）";
    voiceStatusEl.classList.remove("hidden");

    // Stop handler
    mediaRecorder = {
      stop: () => {
        processor.disconnect();
        source.disconnect();
        stream.getTracks().forEach((t) => t.stop());
        audioContext.close();
        isRecording = false;
        voiceBtnEl.classList.remove("recording");
        voiceStatusEl.textContent = "正在上传识别...";
        const wav = encodeWAV(audioChunks);
        uploadWavForAsr(wav);
      },
    };
  } catch (e) {
    alert("无法访问麦克风：" + e.message);
    isRecording = false;
    voiceBtnEl.classList.remove("recording");
  }
}

function encodeWAV(chunks) {
  let total = 0;
  for (const c of chunks) total += c.length;
  const buf = new ArrayBuffer(44 + total * 2);
  const view = new DataView(buf);
  // WAV header
  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + total * 2, true);
  writeString(view, 8, "WAVE");
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true);
  view.setUint32(28, 16000 * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(view, 36, "data");
  view.setUint32(40, total * 2, true);
  let offset = 44;
  for (const chunk of chunks) {
    for (let i = 0; i < chunk.length; i++, offset += 2) {
      let s = Math.max(-1, Math.min(1, chunk[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
  }
  return new Blob([buf], { type: "audio/wav" });
}

function writeString(view, offset, str) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i));
  }
}

async function uploadWavForAsr(blob) {
  try {
    const resp = await fetch(`${API}/api/asr/bailian`, {
      method: "POST",
      headers: { "Content-Type": "audio/wav" },
      body: blob,
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "识别失败");
    messageInputEl.value = data.text;
    voiceStatusEl.textContent = `识别结果：${data.text}`;
  } catch (e) {
    voiceStatusEl.textContent = "识别失败：" + e.message;
  }
  setTimeout(() => voiceStatusEl.classList.add("hidden"), 3000);
}

// ==================== Persona ====================
async function loadPersonas() {
  try {
    const { personas: list } = await apiGet("/api/personas");
    personas = list;
    personaSelectEl.innerHTML =
      '<option value="">选择陪伴者年龄段</option>';
    for (const p of list) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = `${p.ageRange}岁 - ${p.name}`;
      personaSelectEl.appendChild(opt);
    }
  } catch (e) {
    console.error("加载人格失败", e);
  }
}

personaSelectEl.addEventListener("change", async () => {
  if (!currentSessionId || !personaSelectEl.value) return;
  try {
    await apiPut(`/api/sessions/${currentSessionId}/persona`, {
      personaId: personaSelectEl.value,
    });
  } catch (e) {
    alert("切换人格失败：" + e.message);
  }
});

// ==================== Settings ====================
async function openSettings() {
  try {
    config = await apiGet("/api/config");
    $("cfgBaseUrl").value = config.llm?.base_url || "";
    $("cfgApiKey").value = config.llm?.api_key || "";
    $("cfgModel").value = config.llm?.model || "";
    $("cfgBailianKey").value = config.asr?.bailian_api_key || "";
    $("cfgHotwordsPath").value = config.hotwords?.path || "";
    renderPersonaEditor();
    settingsModalEl.classList.remove("hidden");
  } catch (e) {
    alert("加载配置失败：" + e.message);
  }
}

function renderPersonaEditor() {
  const container = $("personaEditor");
  container.innerHTML = "";
  for (const p of personas) {
    const div = document.createElement("div");
    div.className = "persona-item";
    div.innerHTML = `
      <label>年龄段 <input type="text" value="${escapeHtml(p.ageRange)}" data-id="${p.id}" data-field="ageRange" /></label>
      <label>名称 <input type="text" value="${escapeHtml(p.name)}" data-id="${p.id}" data-field="name" /></label>
      <label>人格 Prompt <textarea rows="3" data-id="${p.id}" data-field="prompt">${escapeHtml(p.prompt)}</textarea></label>
    `;
    container.appendChild(div);
  }
}

async function saveConfig() {
  try {
    const newConfig = {
      llm: {
        base_url: $("cfgBaseUrl").value.trim(),
        api_key: $("cfgApiKey").value.trim(),
        model: $("cfgModel").value.trim(),
      },
      asr: {
        bailian_api_key: $("cfgBailianKey").value.trim(),
      },
      hotwords: {
        path: $("cfgHotwordsPath").value.trim(),
      },
    };
    await apiPut("/api/config", newConfig);
    alert("配置已保存");
  } catch (e) {
    alert("保存失败：" + e.message);
  }
}

async function savePersonas() {
  try {
    const items = $("personaEditor").querySelectorAll(".persona-item");
    const updated = personas.map((p) => ({ ...p }));
    items.forEach((item) => {
      const inputs = item.querySelectorAll("[data-id]");
      inputs.forEach((inp) => {
        const id = inp.dataset.id;
        const field = inp.dataset.field;
        const p = updated.find((x) => x.id === id);
        if (p) p[field] = inp.value;
      });
    });
    await apiPut("/api/personas", { personas: updated });
    personas = updated;
    await loadPersonas();
    alert("人格配置已保存");
  } catch (e) {
    alert("保存人格失败：" + e.message);
  }
}

async function testLlm() {
  const resultEl = $("testLlmResult");
  resultEl.textContent = "测试中...";
  resultEl.className = "test-result";
  try {
    const r = await apiPost("/api/config/test-llm", {});
    if (r.ok) {
      resultEl.textContent = `✓ 连接成功：${r.reply}`;
      resultEl.classList.add("ok");
    } else {
      resultEl.textContent = `✗ 失败：${r.error}`;
      resultEl.classList.add("fail");
    }
  } catch (e) {
    resultEl.textContent = `✗ 失败：${e.message}`;
    resultEl.classList.add("fail");
  }
}

async function testAsr() {
  const resultEl = $("testAsrResult");
  resultEl.textContent = "测试中...";
  resultEl.className = "test-result";
  try {
    const r = await apiPost("/api/config/test-asr", {});
    if (r.ok) {
      resultEl.textContent = `✓ ${r.message}`;
      resultEl.classList.add("ok");
    } else {
      resultEl.textContent = `✗ ${r.error}`;
      resultEl.classList.add("fail");
    }
  } catch (e) {
    resultEl.textContent = `✗ ${e.message}`;
    resultEl.classList.add("fail");
  }
}

// ==================== Utility ====================
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = String(str);
  return div.innerHTML;
}

// ==================== Event Listeners ====================
newSessionBtnEl.addEventListener("click", newSession);
sendBtnEl.addEventListener("click", sendMessage);
voiceBtnEl.addEventListener("click", toggleVoice);
settingsBtnEl.addEventListener("click", openSettings);
closeSettingsBtnEl.addEventListener("click", () =>
  settingsModalEl.classList.add("hidden"),
);
saveConfigBtnEl.addEventListener("click", saveConfig);
$("savePersonasBtn").addEventListener("click", savePersonas);
$("testLlmBtn").addEventListener("click", testLlm);
$("testAsrBtn").addEventListener("click", testAsr);

messageInputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

settingsModalEl.addEventListener("click", (e) => {
  if (e.target === settingsModalEl) {
    settingsModalEl.classList.add("hidden");
  }
});

// ==================== Frontend Error Reporting ====================
window.addEventListener("error", (e) => {
  fetch(`${API}/api/logs/frontend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: e.message,
      url: location.href,
      line: e.lineno,
      column: e.colno,
      stack: e.error?.stack,
    }),
  }).catch(() => {});
});

window.addEventListener("unhandledrejection", (e) => {
  fetch(`${API}/api/logs/frontend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: String(e.reason),
      url: location.href,
    }),
  }).catch(() => {});
});

// ==================== Init ====================
async function init() {
  await loadPersonas();
  await loadSessions();
  // Auto-select first session if exists
  const { sessions } = await apiGet("/api/sessions");
  if (sessions.length > 0) {
    await switchSession(sessions[0].id);
  }
}

init();

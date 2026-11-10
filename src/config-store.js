import { readFile, writeFile, mkdir } from "node:fs/promises";
import { existsSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = join(__dirname, "..");
const DATA_DIR = join(PROJECT_ROOT, "data");
const CONFIG_PATH = join(DATA_DIR, "config.json");
const DEV_CONFIG_PATH = join(PROJECT_ROOT, "dev-config.json");

// 开发模式优先使用 dev-config.json，便于直接编辑测试 API
function getActiveConfigPath() {
  return existsSync(DEV_CONFIG_PATH) ? DEV_CONFIG_PATH : CONFIG_PATH;
}

const DEFAULT_CONFIG = {
  llm: {
    base_url: "",
    api_key: "",
    model: "",
    temperature: 0.7,
  },
  asr: {
    engine: "web-speech", // "web-speech" | "bailian"
    bailian_api_key: "",
  },
  hotwords: {
    path: "../ASR/hotwords/cantonese_elderly.json",
  },
  emotion: {
    service_url: "http://127.0.0.1:4173",
    timeout_ms: 8000,
  },
};

let cache = null;
let cacheMtime = 0;

async function ensureDir() {
  await mkdir(DATA_DIR, { recursive: true });
}

// 读取配置文件的修改时间，用于判断缓存是否过期
function getConfigMtime() {
  try {
    return statSync(getActiveConfigPath()).mtimeMs;
  } catch {
    return 0;
  }
}

export async function loadConfig() {
  const mtime = getConfigMtime();
  // 缓存有效：内存中已有且文件未被外部修改
  if (cache && mtime === cacheMtime) return cache;

  await ensureDir();
  const activePath = getActiveConfigPath();
  let parsed;
  try {
    const raw = await readFile(activePath, "utf-8");
    parsed = JSON.parse(raw);
  } catch {
    parsed = structuredClone(DEFAULT_CONFIG);
    await writeFile(activePath, JSON.stringify(parsed, null, 2), "utf-8");
  }
  cache = { ...DEFAULT_CONFIG, ...parsed };
  cache.llm = { ...DEFAULT_CONFIG.llm, ...(parsed.llm || {}) };
  cache.asr = { ...DEFAULT_CONFIG.asr, ...(parsed.asr || {}) };
  cache.hotwords = { ...DEFAULT_CONFIG.hotwords, ...(parsed.hotwords || {}) };
  cache.emotion = { ...DEFAULT_CONFIG.emotion, ...(parsed.emotion || {}) };
  cacheMtime = getConfigMtime();
  return cache;
}

export async function saveConfig(config) {
  await ensureDir();
  await writeFile(getActiveConfigPath(), JSON.stringify(config, null, 2), "utf-8");
  cache = config;
  cacheMtime = getConfigMtime();
  return config;
}

export async function updateConfig(partial) {
  // 始终从磁盘重读，避免覆盖用户的外部编辑
  const current = await loadConfig();
  const merged = { ...current, ...partial };
  if (partial.llm) merged.llm = { ...current.llm, ...partial.llm };
  if (partial.asr) merged.asr = { ...current.asr, ...partial.asr };
  if (partial.hotwords) merged.hotwords = { ...current.hotwords, ...partial.hotwords };
  if (partial.emotion) merged.emotion = { ...current.emotion, ...partial.emotion };
  await saveConfig(merged);
  return merged;
}

export function getConfigPath() {
  return getActiveConfigPath();
}

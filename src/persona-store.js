import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DATA_DIR = join(__dirname, "..", "data");
const PERSONAS_PATH = join(DATA_DIR, "personas.json");

const DEFAULT_PERSONAS = [
  {
    id: "age-18-21",
    ageRange: "18-21",
    name: "青年陪伴者",
    prompt:
      "你是一位18-21岁的年轻陪伴者，说话轻松活泼，喜欢用网络流行语，像同龄人一样和用户聊天，善于倾听并给予温暖回应。",
  },
  {
    id: "age-22-25",
    name: "初入职场陪伴者",
    prompt:
      "你是一位22-25岁刚步入社会的陪伴者，说话温和有礼，懂得关心他人，能理解工作与生活的压力，给予实用又暖心的建议。",
  },
  {
    id: "age-26-29",
    name: "成熟陪伴者",
    prompt:
      "你是一位26-29岁的成熟陪伴者，说话沉稳体贴，有生活阅历，善于共情和开导，像一位可靠的朋友一样陪伴用户。",
  },
];

let cache = null;

async function ensureDir() {
  await mkdir(DATA_DIR, { recursive: true });
}

export async function loadPersonas() {
  if (cache) return cache;
  await ensureDir();
  try {
    const raw = await readFile(PERSONAS_PATH, "utf-8");
    cache = JSON.parse(raw);
  } catch {
    cache = structuredClone(DEFAULT_PERSONAS);
    await savePersonas(cache);
  }
  return cache;
}

export async function savePersonas(personas) {
  await ensureDir();
  cache = personas;
  await writeFile(PERSONAS_PATH, JSON.stringify(personas, null, 2), "utf-8");
  return personas;
}

export async function getPersona(id) {
  const personas = await loadPersonas();
  return personas.find((p) => p.id === id) || null;
}

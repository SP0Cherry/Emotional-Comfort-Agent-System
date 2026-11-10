import { readFileSync } from "node:fs";
import { readFile as readFilePromise } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

function resolveHotwordsPath(hotwordsPath) {
  if (!hotwordsPath) return null;
  return hotwordsPath.startsWith(".")
    ? resolve(__dirname, "..", "..", hotwordsPath)
    : hotwordsPath;
}

/**
 * Load hotwords from a JSON file (cantonese_elderly.json format)
 * and flatten into 百炼 vocabulary format: [{ word, weight }]
 */
export async function loadHotwords(hotwordsPath) {
  const resolvedPath = resolveHotwordsPath(hotwordsPath);
  if (!resolvedPath) return [];

  try {
    const raw = await readFilePromise(resolvedPath, "utf-8");
    const data = JSON.parse(raw);
    return flattenHotwords(data);
  } catch (err) {
    throw new Error(`热词表加载失败: ${err.message}`);
  }
}

function flattenHotwords(data) {
  const vocabulary = [];
  const hotwords = data.hotwords || data;

  for (const [, catData] of Object.entries(hotwords)) {
    if (!catData || !Array.isArray(catData.words)) continue;
    const weight = catData.weight || 1;
    for (const word of catData.words) {
      if (typeof word === "string" && word.trim()) {
        vocabulary.push({ word: word.trim(), weight });
      }
    }
  }
  return vocabulary;
}

export function getHotwordsMeta(hotwordsPath) {
  const resolvedPath = resolveHotwordsPath(hotwordsPath);
  if (!resolvedPath) return null;
  try {
    const raw = readFileSync(resolvedPath, "utf-8");
    const data = JSON.parse(raw);
    return data.meta || null;
  } catch {
    return null;
  }
}

import { readFile, stat } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const EMOTIONS = new Set([
  "joy",
  "calm",
  "sadness",
  "anxiety",
  "anger_irritation",
  "neutral",
]);
const SPLITS = new Set(["train", "dev", "test"]);
const REQUIRED_FIELDS = [
  "sample_id",
  "speaker_id",
  "split",
  "audio_path",
  "text",
  "emotion",
  "valence",
  "arousal",
  "intensity",
  "consent",
];

const projectDirectory = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "..",
);
const manifestArgument =
  process.argv.find((argument) => !argument.startsWith("-") && argument.endsWith(".jsonl")) ??
  process.argv[2];
if (!manifestArgument) {
  console.error("用法：npm run validate:data -- data/emotion-samples.jsonl");
  process.exit(2);
}

const manifestPath = resolve(projectDirectory, manifestArgument);
const content = await readFile(manifestPath, "utf8");
const items = content
  .split(/\r?\n/)
  .filter((line) => line.trim())
  .map((line, index) => {
    try {
      return JSON.parse(line);
    } catch {
      throw new Error(`第 ${index + 1} 行不是有效 JSON`);
    }
  });

const errors = [];
const warnings = [];
const ids = new Set();
const speakersBySplit = Object.fromEntries(
  [...SPLITS].map((split) => [split, new Set()]),
);
const emotionCounts = Object.fromEntries(
  [...EMOTIONS].map((emotion) => [emotion, 0]),
);
const splitCounts = Object.fromEntries([...SPLITS].map((split) => [split, 0]));
const speakerCounts = {};

for (const [index, item] of items.entries()) {
  const line = index + 1;
  for (const field of REQUIRED_FIELDS) {
    if (!(field in item)) errors.push(`第 ${line} 行缺少 ${field}`);
  }
  if (ids.has(item.sample_id)) errors.push(`sample_id 重复：${item.sample_id}`);
  ids.add(item.sample_id);
  if (!EMOTIONS.has(item.emotion)) errors.push(`第 ${line} 行情绪标签无效`);
  if (!SPLITS.has(item.split)) errors.push(`第 ${line} 行 split 无效`);
  if (item.consent !== true) errors.push(`第 ${line} 行缺少有效授权`);

  for (const [field, min, max] of [
    ["valence", -1, 1],
    ["arousal", 0, 1],
    ["intensity", 0, 1],
  ]) {
    if (
      typeof item[field] !== "number" ||
      !Number.isFinite(item[field]) ||
      item[field] < min ||
      item[field] > max
    ) {
      errors.push(`第 ${line} 行 ${field} 超出范围`);
    }
  }

  if (item.speaker_id) {
    speakersBySplit[item.split]?.add(item.speaker_id);
    speakerCounts[item.speaker_id] =
      (speakerCounts[item.speaker_id] ?? 0) + 1;
  }
  if (EMOTIONS.has(item.emotion)) emotionCounts[item.emotion] += 1;
  if (SPLITS.has(item.split)) splitCounts[item.split] += 1;

  if (item.audio_path) {
    const audioPath = resolve(dirname(manifestPath), item.audio_path);
    try {
      const audioStat = await stat(audioPath);
      if (audioStat.size < 44) errors.push(`第 ${line} 行音频为空`);
    } catch {
      errors.push(`第 ${line} 行音频不存在：${item.audio_path}`);
    }
  }
}

const splitEntries = Object.entries(speakersBySplit);
for (let left = 0; left < splitEntries.length; left += 1) {
  for (let right = left + 1; right < splitEntries.length; right += 1) {
    const [leftName, leftSpeakers] = splitEntries[left];
    const [rightName, rightSpeakers] = splitEntries[right];
    const overlap = [...leftSpeakers].filter((speaker) =>
      rightSpeakers.has(speaker),
    );
    if (overlap.length) {
      errors.push(
        `${leftName}/${rightName} 存在说话人泄漏：${overlap.join(", ")}`,
      );
    }
  }
}

if (items.length < 30) warnings.push("样本少于 30 条，只能做错误分析");
if (Object.keys(speakerCounts).length < 3) {
  warnings.push("说话人少于 3 人，不能报告泛化准确率");
}
if (Object.values(splitCounts).some((count) => count === 0)) {
  warnings.push("至少一个数据划分没有样本");
}
const minimumClassCount = Math.min(...Object.values(emotionCounts));
const maximumClassCount = Math.max(...Object.values(emotionCounts));
if (maximumClassCount > Math.max(2, minimumClassCount * 2)) {
  warnings.push("情绪类别明显不平衡");
}

console.log(
  JSON.stringify(
    {
      manifest: manifestPath,
      samples: items.length,
      splits: splitCounts,
      emotions: emotionCounts,
      speakers: speakerCounts,
      warnings,
      errors,
      valid: errors.length === 0,
    },
    null,
    2,
  ),
);

if (errors.length) process.exitCode = 1;

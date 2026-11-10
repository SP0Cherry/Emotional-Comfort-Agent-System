import { readFile, writeFile, readdir, mkdir, unlink } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { v4 as uuidv4 } from "uuid";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SESSIONS_DIR = join(__dirname, "..", "data", "sessions");

const ID_PATTERN = /^[A-Za-z0-9_-]{1,80}$/;

function sanitizeId(id) {
  if (ID_PATTERN.test(id)) return id;
  // replace invalid chars with dashes, trim, cap length
  return id.replace(/[^A-Za-z0-9_-]/g, "-").slice(0, 80) || uuidv4().slice(0, 16);
}

function sessionPath(id) {
  return join(SESSIONS_DIR, `${sanitizeId(id)}.json`);
}

async function ensureDir() {
  await mkdir(SESSIONS_DIR, { recursive: true });
}

export async function createSession({ title = "新对话", personaId = null } = {}) {
  await ensureDir();
  const id = uuidv4();
  const session = {
    id,
    title,
    personaId,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    messages: [],
  };
  await writeFile(sessionPath(id), JSON.stringify(session, null, 2), "utf-8");
  return session;
}

export async function listSessions() {
  await ensureDir();
  let files = [];
  try {
    files = await readdir(SESSIONS_DIR);
  } catch {
    return [];
  }
  const sessions = [];
  for (const f of files) {
    if (!f.endsWith(".json")) continue;
    try {
      const raw = await readFile(join(SESSIONS_DIR, f), "utf-8");
      const s = JSON.parse(raw);
      sessions.push({
        id: s.id,
        title: s.title,
        personaId: s.personaId,
        createdAt: s.createdAt,
        updatedAt: s.updatedAt,
        messageCount: (s.messages || []).length,
      });
    } catch {
      // skip corrupt files
    }
  }
  sessions.sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt));
  return sessions;
}

export async function getSession(id) {
  try {
    const raw = await readFile(sessionPath(id), "utf-8");
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export async function appendMessage(id, message) {
  const session = await getSession(id);
  if (!session) return null;
  session.messages.push({
    ...message,
    timestamp: message.timestamp || new Date().toISOString(),
  });
  session.updatedAt = new Date().toISOString();
  await writeFile(sessionPath(id), JSON.stringify(session, null, 2), "utf-8");
  return session;
}

export async function updateSession(id, partial) {
  const session = await getSession(id);
  if (!session) return null;
  Object.assign(session, partial);
  session.updatedAt = new Date().toISOString();
  await writeFile(sessionPath(id), JSON.stringify(session, null, 2), "utf-8");
  return session;
}

export async function deleteSession(id) {
  try {
    await unlink(sessionPath(id));
    return true;
  } catch {
    return false;
  }
}

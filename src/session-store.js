import { randomUUID } from "node:crypto";

export class SessionStore {
  constructor({
    maxSessions = 200,
    maxStatesPerSession = 20,
    ttlMs = 4 * 60 * 60 * 1000,
    now = () => Date.now(),
  } = {}) {
    this.maxSessions = maxSessions;
    this.maxStatesPerSession = maxStatesPerSession;
    this.ttlMs = ttlMs;
    this.now = now;
    this.sessions = new Map();
  }

  getOrCreate(sessionId) {
    this.prune();

    const id = sessionId || `sess-${randomUUID()}`;
    const timestamp = this.now();
    let session = this.sessions.get(id);

    if (!session) {
      if (this.sessions.size >= this.maxSessions) {
        const oldestId = [...this.sessions.entries()].sort(
          ([, left], [, right]) => left.lastAccess - right.lastAccess,
        )[0]?.[0];
        if (oldestId) this.sessions.delete(oldestId);
      }

      session = {
        id,
        createdAt: timestamp,
        lastAccess: timestamp,
        nextTurnId: 1,
        states: [],
      };
      this.sessions.set(id, session);
    }

    session.lastAccess = timestamp;
    return session;
  }

  get(sessionId) {
    this.prune();
    const session = this.sessions.get(sessionId);
    if (session) session.lastAccess = this.now();
    return session ?? null;
  }

  appendState(sessionId, state) {
    const session = this.getOrCreate(sessionId);
    session.states.push(state);
    session.states = session.states.slice(-this.maxStatesPerSession);
    session.nextTurnId += 1;
    session.lastAccess = this.now();
    return session;
  }

  delete(sessionId) {
    this.prune();
    return this.sessions.delete(sessionId);
  }

  prune() {
    const threshold = this.now() - this.ttlMs;
    for (const [id, session] of this.sessions) {
      if (session.lastAccess < threshold) {
        this.sessions.delete(id);
      }
    }
  }

  size() {
    this.prune();
    return this.sessions.size;
  }
}

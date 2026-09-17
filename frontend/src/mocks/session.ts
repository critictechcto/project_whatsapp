/**
 * Mock-only stand-in for the HttpOnly refresh cookie.
 *
 * MSW can't set HttpOnly cookies, so the mock auth handlers keep the "cookie" themselves, in
 * localStorage under a mock-only key. Like the real cookie it is shared by every tab and survives
 * reloads (the mock database is rebuilt on each page load), and app code never reads it: only the
 * handlers do. Refresh rotates the session id, logout removes it.
 */

import { db } from './db'
import { uuid } from './utils'

export const MOCK_SESSION_KEY = 'upchatz.mock-only.refresh-session'

export type MockSession = { id: string; userId: string }

function storage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage
  } catch {
    return null
  }
}

/** Session kept in memory when localStorage is unavailable. */
let fallback: MockSession | null = null

export function readMockSession(): MockSession | null {
  const store = storage()
  if (!store) return fallback
  try {
    const parsed = JSON.parse(store.getItem(MOCK_SESSION_KEY) ?? 'null') as Partial<MockSession> | null
    if (!parsed || typeof parsed.id !== 'string' || typeof parsed.userId !== 'string') return null
    if (!db.users.some((user) => user.id === parsed.userId)) return null
    return { id: parsed.id, userId: parsed.userId }
  } catch {
    return null
  }
}

function writeMockSession(session: MockSession | null) {
  fallback = session
  const store = storage()
  if (!store) return
  try {
    if (session) store.setItem(MOCK_SESSION_KEY, JSON.stringify(session))
    else store.removeItem(MOCK_SESSION_KEY)
  } catch {
    // ignore
  }
}

/** Login/register: "sets the cookie". */
export function startMockSession(userId: string): MockSession {
  const session = { id: uuid(), userId }
  writeMockSession(session)
  return session
}

/** Refresh: "rotates the cookie". Returns null when there is no valid session. */
export function rotateMockSession(): MockSession | null {
  const current = readMockSession()
  if (!current) {
    writeMockSession(null)
    return null
  }
  return startMockSession(current.userId)
}

/** Logout or a rejected refresh: "clears the cookie". */
export function endMockSession() {
  writeMockSession(null)
}

/**
 * Secure storage utilities for LOKO frontend
 * Implements X3 from PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md
 *
 * Security model:
 * - Session cookies (HTTPOnly) for admin auth
 * - sessionStorage only for non-sensitive data
 * - API keys stored server-side, never exposed to client in admin app
 * - Widget: API key required but scoped per bot (lot T)
 */

// Types of data we store
type StorageKey = 'bot_id' | 'wizard_step' | 'playground_bot_id';

/**
 * Store non-sensitive data in sessionStorage.
 *
 * Use ONLY for:
 * - UI state (wizard step, selected bot ID)
 * - Non-sensitive preferences
 *
 * NEVER use for:
 * - Passwords
 * - API keys
 * - Session tokens (use HTTPOnly cookies instead)
 * - User messages
 */
export function setStorage(key: StorageKey, value: string): void {
  try {
    sessionStorage.setItem(`loko_${key}`, value);
  } catch (e) {
    console.warn(`Failed to write to sessionStorage: ${e}`);
  }
}

/**
 * Get non-sensitive data from sessionStorage.
 */
export function getStorage(key: StorageKey): string | null {
  try {
    return sessionStorage.getItem(`loko_${key}`);
  } catch (e) {
    console.warn(`Failed to read from sessionStorage: ${e}`);
    return null;
  }
}

/**
 * Remove data from sessionStorage.
 */
export function removeStorage(key: StorageKey): void {
  try {
    sessionStorage.removeItem(`loko_${key}`);
  } catch (e) {
    console.warn(`Failed to remove from sessionStorage: ${e}`);
  }
}

/**
 * Clear all LOKO data from sessionStorage (called on logout).
 */
export function clearStorage(): void {
  try {
    // Remove only LOKO-prefixed items
    const keys = Object.keys(sessionStorage);
    for (const key of keys) {
      if (key.startsWith('loko_')) {
        sessionStorage.removeItem(key);
      }
    }
  } catch (e) {
    console.warn(`Failed to clear sessionStorage: ${e}`);
  }
}

/**
 * Check if any sensitive data is in storage (security audit).
 *
 * Returns:
 *   List of suspicious keys found
 */
export function auditStorage(): string[] {
  const suspicious: string[] = [];
  const sensitivePatterns = [
    /password/i,
    /token/i,
    /api[_-]?key/i,
    /secret/i,
    /auth/i,
  ];

  try {
    const keys = Object.keys(sessionStorage);
    for (const key of keys) {
      // Check key name
      if (sensitivePatterns.some(pattern => pattern.test(key))) {
        suspicious.push(key);
      }

      // Check value (basic heuristic: long random strings)
      const value = sessionStorage.getItem(key);
      if (value && value.length > 30 && /^[A-Za-z0-9+/=_-]{30,}$/.test(value)) {
        suspicious.push(`${key} (suspicious value)`);
      }
    }
  } catch (e) {
    console.warn(`Failed to audit storage: ${e}`);
  }

  return suspicious;
}

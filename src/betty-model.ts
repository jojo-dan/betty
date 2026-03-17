/**
 * betty-model.ts
 * Betty-specific model state management.
 * Allows switching the Claude model via alias or full model ID.
 * State is persisted to data/betty-model.json.
 */
import { readFileSync, writeFileSync } from 'fs';
import path from 'path';

import { DATA_DIR } from './config.js';
import { logger } from './logger.js';

const MODEL_FILE = path.join(DATA_DIR, 'betty-model.json');

const ALIAS_MAP: Record<string, string> = {
  sonnet: 'claude-sonnet-4-6',
  opus: 'claude-opus-4-6',
  haiku: 'claude-haiku-4-5-20251001',
};

let currentModel: string | null = null;

// Load persisted model on startup
try {
  const raw = readFileSync(MODEL_FILE, 'utf8');
  const parsed = JSON.parse(raw) as { model: string };
  if (parsed.model) {
    currentModel = parsed.model;
    logger.info({ model: currentModel }, 'betty-model: loaded from file');
  }
} catch {
  // File absent or unreadable — start with null (default)
}

function persist(model: string): void {
  try {
    writeFileSync(MODEL_FILE, JSON.stringify({ model }), 'utf8');
  } catch (err) {
    logger.error({ err }, 'betty-model: failed to persist model');
  }
}

/** Returns the currently active model ID, or null if none has been set. */
export function getCurrentModel(): string | null {
  return currentModel;
}

/**
 * Sets the active model.
 * Accepts an alias (sonnet / opus / haiku) or a full model ID starting with "claude-".
 * Returns the resolved model ID on success, or null if the input is invalid.
 */
export function setModel(nameOrAlias: string): string | null {
  const alias = nameOrAlias.toLowerCase();
  if (ALIAS_MAP[alias]) {
    currentModel = ALIAS_MAP[alias];
    persist(currentModel);
    return currentModel;
  }
  if (nameOrAlias.startsWith('claude-')) {
    currentModel = nameOrAlias;
    persist(currentModel);
    return currentModel;
  }
  return null;
}

/** Returns the list of recognised alias names. */
export function getValidAliases(): string[] {
  return Object.keys(ALIAS_MAP);
}

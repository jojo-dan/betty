/**
 * Betty media download utilities.
 * Downloads Telegram media files to data/media/<groupFolder>/
 * and manages disk usage with automatic cleanup.
 */
import fs from 'fs';
import https from 'https';
import path from 'path';

import { Bot } from 'grammy';

import { DATA_DIR } from './config.js';
import { logger } from './logger.js';

const MEDIA_DIR = path.join(DATA_DIR, 'media');
const MAX_TOTAL_BYTES = 500 * 1024 * 1024; // 500 MB
const MAX_AGE_MS = 24 * 60 * 60 * 1000; // 24 hours

/**
 * Downloads a Telegram file to data/media/<groupFolder>/<prefix>_<file_unique_id>.<ext>.
 * Returns the saved file path on success, or null on failure.
 */
export async function downloadMediaFile(
  bot: Bot,
  fileId: string,
  fileUniqueId: string,
  groupFolder: string,
  prefix: string,
  ext: string,
): Promise<string | null> {
  try {
    const file = await bot.api.getFile(fileId);
    if (!file.file_path) {
      logger.warn({ fileId }, 'getFile returned no file_path');
      return null;
    }

    const token = (bot as any).token as string;
    const downloadUrl = `https://api.telegram.org/file/bot${token}/${file.file_path}`;

    const groupMediaDir = path.join(MEDIA_DIR, groupFolder);
    fs.mkdirSync(groupMediaDir, { recursive: true });

    const fileName = `${prefix}_${fileUniqueId}.${ext}`;
    const filePath = path.join(groupMediaDir, fileName);

    await downloadFile(downloadUrl, filePath);
    logger.info({ filePath }, 'Media file downloaded');
    return filePath;
  } catch (err) {
    logger.warn({ fileId, err }, 'Failed to download media file');
    return null;
  }
}

function downloadFile(url: string, dest: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    https
      .get(url, (res) => {
        if (res.statusCode !== 200) {
          file.close();
          fs.unlink(dest, () => {});
          reject(new Error(`HTTP ${res.statusCode}`));
          return;
        }
        res.pipe(file);
        file.on('finish', () => file.close(() => resolve()));
      })
      .on('error', (err) => {
        file.close();
        fs.unlink(dest, () => {});
        reject(err);
      });
  });
}

/**
 * Deletes media files older than 24 hours and enforces the 500 MB cap.
 */
export function cleanupMediaFiles(): void {
  if (!fs.existsSync(MEDIA_DIR)) return;

  const now = Date.now();
  const allFiles: { path: string; mtime: number; size: number }[] = [];

  for (const groupDir of fs.readdirSync(MEDIA_DIR)) {
    const groupPath = path.join(MEDIA_DIR, groupDir);
    if (!fs.statSync(groupPath).isDirectory()) continue;
    for (const file of fs.readdirSync(groupPath)) {
      const filePath = path.join(groupPath, file);
      try {
        const stat = fs.statSync(filePath);
        if (!stat.isFile()) continue;
        // Delete files older than 24 hours immediately
        if (now - stat.mtimeMs > MAX_AGE_MS) {
          fs.unlinkSync(filePath);
          logger.debug({ filePath }, 'Cleaned up expired media file');
          continue;
        }
        allFiles.push({ path: filePath, mtime: stat.mtimeMs, size: stat.size });
      } catch {
        // File may have been deleted concurrently — skip
      }
    }
  }

  // Enforce 500 MB cap: delete oldest files first
  let total = allFiles.reduce((sum, f) => sum + f.size, 0);
  if (total > MAX_TOTAL_BYTES) {
    allFiles.sort((a, b) => a.mtime - b.mtime);
    for (const f of allFiles) {
      if (total <= MAX_TOTAL_BYTES) break;
      try {
        fs.unlinkSync(f.path);
        total -= f.size;
        logger.debug(
          { filePath: f.path },
          'Cleaned up media file (cap exceeded)',
        );
      } catch {
        // Skip if already deleted
      }
    }
  }
}

/**
 * Starts cleanup on service start and then every hour.
 */
export function startMediaCleanup(): void {
  cleanupMediaFiles();
  setInterval(cleanupMediaFiles, 60 * 60 * 1000);
}

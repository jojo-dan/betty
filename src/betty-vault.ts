import fs from 'fs';
import path from 'path';
import { logger } from './logger.js';

const VAULT_OUTBOX_DIR = path.join(process.cwd(), 'data', 'vault-outbox');
const PROCESSED_DIR = path.join(VAULT_OUTBOX_DIR, 'processed');
const POLL_INTERVAL = 10_000; // 10초
const DELAY_TIMEOUT = 5 * 60 * 1000; // 5분

// 추적 중인 JSON 파일 (uuid → created timestamp)
const tracked = new Map<string, number>();
// 지연 알림 발송 완료
const delayNotified = new Set<string>();

export function startVaultWatcher(
  sendMessage: (jid: string, text: string) => Promise<void>,
  getMainGroupJid: () => string | null,
): void {
  logger.info('Vault watcher started');

  let polling = false;

  setInterval(async () => {
    if (polling) return;
    polling = true;

    const mainJid = getMainGroupJid();
    if (!mainJid) {
      polling = false;
      return;
    }

    try {
      // 1. 새 JSON 파일 스캔 (아직 추적하지 않는 것)
      const files = fs
        .readdirSync(VAULT_OUTBOX_DIR)
        .filter((f) => f.endsWith('.json') && !f.startsWith('._'));

      for (const file of files) {
        const uuid = file.replace('.json', '');
        if (!tracked.has(uuid)) {
          // JSON의 created 필드를 읽거나, 현재 시각 사용
          let created = Date.now();
          try {
            const json = JSON.parse(
              fs.readFileSync(path.join(VAULT_OUTBOX_DIR, file), 'utf-8'),
            );
            if (json.created) {
              created = new Date(json.created).getTime();
            }
          } catch {
            // JSON 파싱 실패 — 현재 시각 사용
          }
          tracked.set(uuid, created);
        }
      }

      // 2. 추적 중인 항목 처리
      for (const [uuid, createdAt] of tracked) {
        const doneFile = path.join(PROCESSED_DIR, `${uuid}.done`);

        if (fs.existsSync(doneFile)) {
          // 완료 처리 — delete 먼저 (async 중복 방지)
          tracked.delete(uuid);
          delayNotified.delete(uuid);
          await sendMessage(mainJid, '노트 만들어뒀어. 볼트에서 확인해봐.');
          logger.info({ uuid }, 'Vault note completed');
          continue;
        }

        // 5분 경과 + 지연 알림 미발송
        const elapsed = Date.now() - createdAt;
        if (elapsed > DELAY_TIMEOUT && !delayNotified.has(uuid)) {
          delayNotified.add(uuid);
          await sendMessage(
            mainJid,
            '아직 노트가 안 만들어진 것 같아. 랩탑이 꺼져 있으면 켜면 자동으로 처리될 거야. 메모 내용은 내가 들고 있으니까 사라지진 않아.',
          );
          logger.info({ uuid }, 'Vault note delay notification sent');
        }
      }
    } catch (err) {
      logger.error({ err }, 'Vault watcher error');
    } finally {
      polling = false;
    }
  }, POLL_INTERVAL);
}

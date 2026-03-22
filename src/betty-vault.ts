import fs from 'fs';
import path from 'path';
import { randomUUID } from 'crypto';

import { DATA_DIR } from './config.js';
import { logger } from './logger.js';

const VAULT_OUTBOX_DIR = path.join(process.cwd(), 'data', 'vault-outbox');
const PROCESSED_DIR = path.join(VAULT_OUTBOX_DIR, 'processed');
const POLL_INTERVAL = 10_000; // 10초
const DELAY_TIMEOUT = 5 * 60 * 1000; // 5분

// 추적 중인 JSON 파일 (uuid → { createdAt, action })
const tracked = new Map<string, { createdAt: number; action: string }>();
// 지연 알림 발송 완료
const delayNotified = new Set<string>();
// 배치 알림 쿨다운 (마지막 전송 시각)
let lastBatchNotifyTime = 0;
const BATCH_COOLDOWN = 5 * 60 * 1000; // 5분 쿨다운

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
          // JSON의 created / action 필드를 읽거나, 기본값 사용
          let createdAt = Date.now();
          let action = '';
          try {
            const json = JSON.parse(
              fs.readFileSync(path.join(VAULT_OUTBOX_DIR, file), 'utf-8'),
            );
            if (json.created) {
              createdAt = new Date(json.created).getTime();
            }
            if (json.action) {
              action = json.action;
            }
          } catch {
            // JSON 파싱 실패 — 기본값 사용
          }
          tracked.set(uuid, { createdAt, action });
        }
      }

      // 2. 추적 중인 항목 처리
      const pendingForNotify: string[] = [];
      const completedCreateUuids: string[] = [];

      for (const [uuid, { createdAt, action: trackedAction }] of tracked) {
        const doneFile = path.join(PROCESSED_DIR, `${uuid}.done`);

        if (fs.existsSync(doneFile)) {
          // 완료 처리 — delete 먼저 (async 중복 방지)
          tracked.delete(uuid);
          delayNotified.delete(uuid);
          // .done 파일 내용으로 action 유형 판별
          let action = '';
          try {
            action = fs.readFileSync(doneFile, 'utf-8').trim();
          } catch {
            // 읽기 실패 — 빈 문자열로 처리 (레거시 동작)
          }
          if (action === 'create' || action === '') {
            completedCreateUuids.push(uuid);
            logger.info(
              { uuid, action },
              'Vault note completed — queued for batch message',
            );
          } else {
            logger.info(
              { uuid, action },
              'Vault note completed — silent (non-create action)',
            );
          }
          continue;
        }

        // 5분 경과 + 지연 알림 미발송 + update-reminder 제외
        const elapsed = Date.now() - createdAt;
        if (
          elapsed > DELAY_TIMEOUT &&
          !delayNotified.has(uuid) &&
          trackedAction !== 'update-reminder'
        ) {
          pendingForNotify.push(uuid);
        } else if (
          elapsed > DELAY_TIMEOUT &&
          !delayNotified.has(uuid) &&
          trackedAction === 'update-reminder'
        ) {
          delayNotified.add(uuid);
          logger.info(
            { uuid, action: trackedAction },
            'Delay notification skipped — non-create action',
          );
        }
      }

      // 완료 알림 배치 발송 (폴링 사이클당 최대 1회)
      if (completedCreateUuids.length > 0) {
        const count = completedCreateUuids.length;
        const msg =
          count === 1
            ? '노트 만들어뒀으니 확인해보면 되는 거야.'
            : `노트 ${count}개 만들어뒀으니 확인해보면 되는 거야.`;
        await sendMessage(mainJid, msg);
        logger.info(
          { uuids: completedCreateUuids, count },
          'Vault note batch completed — message sent',
        );
      }

      // 지연 알림 배치 발송 (폴링 사이클당 최대 1회 + 5분 쿨다운)
      if (pendingForNotify.length > 0) {
        // delayNotified에 등록 (재알림 방지)
        pendingForNotify.forEach((u) => delayNotified.add(u));

        // 쿨다운 내이면 알림 억제 (다음 쿨다운 만료 시 새 pending이 있으면 발송)
        const now = Date.now();
        if (now - lastBatchNotifyTime >= BATCH_COOLDOWN) {
          // 전체 미처리 개수 (이번 배치 + 이전에 이미 알림한 것 중 아직 미처리)
          const totalPending =
            [...tracked.keys()].filter(
              (u) => !delayNotified.has(u) || pendingForNotify.includes(u),
            ).length || pendingForNotify.length;
          const count = totalPending;
          const msg =
            count === 1
              ? '아직 처리가 안 된 것 같은데… 랩탑이 꺼져 있으면 켜면 자동으로 되는 거야. 내용은 베티가 들고 있으니 사라지진 않을까.'
              : `노트 ${count}개가 아직 처리가 안 된 것 같은데… 랩탑이 꺼져 있으면 켜면 자동으로 되는 거야. 내용은 베티가 들고 있으니 사라지진 않을까.`;
          await sendMessage(mainJid, msg);
          lastBatchNotifyTime = now;
          logger.info(
            { uuids: pendingForNotify, count },
            'Vault note batch delay notification sent',
          );
        } else {
          logger.info(
            {
              uuids: pendingForNotify,
              cooldownRemaining: BATCH_COOLDOWN - (now - lastBatchNotifyTime),
            },
            'Vault note delay notification suppressed — cooldown active',
          );
        }
      }
    } catch (err) {
      logger.error({ err }, 'Vault watcher error');
    } finally {
      polling = false;
    }
  }, POLL_INTERVAL);
}

export function writeVaultOutboxUpdateReminder(
  reminderId: string,
  status: 'done' | 'cancelled' | 'active',
  options?: { reminder?: string; newReminderId?: string },
): void {
  const outboxDir = path.join(DATA_DIR, 'vault-outbox');
  const payload = {
    action: 'update-reminder',
    reminder_id: reminderId,
    reminder_status: status,
    ...(options?.reminder ? { reminder: options.reminder } : {}),
    ...(options?.newReminderId
      ? { new_reminder_id: options.newReminderId }
      : {}),
  };
  const filename = path.join(outboxDir, `${randomUUID()}.json`);
  try {
    fs.mkdirSync(outboxDir, { recursive: true });
    fs.writeFileSync(filename, JSON.stringify(payload, null, 2));
    logger.info({ reminderId, status }, 'Vault outbox update-reminder written');
  } catch (err) {
    logger.error(
      { err, reminderId },
      'Failed to write vault outbox update-reminder',
    );
  }
}

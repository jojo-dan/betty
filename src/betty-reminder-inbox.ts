import fs from 'fs';
import path from 'path';
import { logger } from './logger.js';
import { createTask, getTaskById, updateTask, deleteTask } from './db.js';

const REMINDER_INBOX_DIR = path.join(process.cwd(), 'data', 'reminder-inbox');
const PROCESSED_DIR = path.join(REMINDER_INBOX_DIR, 'processed');
const POLL_INTERVAL = 10_000; // 10초

export function startReminderInboxWatcher(
  getMainGroupJid: () => string | null,
): void {
  // 디렉토리 자동 생성
  fs.mkdirSync(REMINDER_INBOX_DIR, { recursive: true });
  fs.mkdirSync(PROCESSED_DIR, { recursive: true });

  logger.info('Reminder inbox watcher started');

  let polling = false;

  setInterval(async () => {
    if (polling) return;
    polling = true;

    try {
      const mainJid = getMainGroupJid();
      if (!mainJid) {
        return; // finally에서 polling = false
      }

      // JSON 파일 스캔 (._로 시작하는 파일 제외)
      const files = fs
        .readdirSync(REMINDER_INBOX_DIR)
        .filter((f) => f.endsWith('.json') && !f.startsWith('.') && !f.startsWith('._'));

      for (const file of files) {
        try {
          const filePath = path.join(REMINDER_INBOX_DIR, file);
          const raw = fs.readFileSync(filePath, 'utf-8');
          const json = JSON.parse(raw);

          const action = json.action || 'create';
          const id = json.id;

          if (!id) {
            logger.error({ file }, 'Reminder inbox: missing id field');
            // 잘못된 파일도 processed로 이동 (무한 재처리 방지)
            fs.renameSync(filePath, path.join(PROCESSED_DIR, file));
            continue;
          }

          if (action === 'create') {
            const scheduleValue = json.schedule_value;
            if (!scheduleValue) {
              logger.error({ file, id }, 'Reminder inbox: missing schedule_value for create');
              fs.renameSync(filePath, path.join(PROCESSED_DIR, file));
              continue;
            }

            // schedule_value 파싱 검증
            const nextRun = new Date(scheduleValue);
            if (isNaN(nextRun.getTime())) {
              logger.error({ file, id, scheduleValue }, 'Reminder inbox: invalid schedule_value');
              fs.renameSync(filePath, path.join(PROCESSED_DIR, file));
              continue;
            }

            createTask({
              id,
              group_folder: 'telegram_main',
              chat_jid: mainJid,
              prompt: json.prompt || '',
              schedule_type: 'once',
              schedule_value: scheduleValue,
              context_mode: json.context_mode || 'isolated',
              next_run: nextRun.toISOString(),
              status: 'active',
              created_at: new Date().toISOString(),
            });

            logger.info({ id, scheduleValue }, 'Reminder inbox: task created');

          } else if (action === 'update') {
            const existing = getTaskById(id);
            if (!existing) {
              logger.error({ file, id }, 'Reminder inbox: task not found for update');
              fs.renameSync(filePath, path.join(PROCESSED_DIR, file));
              continue;
            }

            const updates: Partial<Pick<import('./types.js').ScheduledTask, 'prompt' | 'schedule_type' | 'schedule_value' | 'next_run' | 'status'>> = {};
            if (json.prompt) updates.prompt = json.prompt;
            if (json.schedule_value) {
              const nextRun = new Date(json.schedule_value);
              if (isNaN(nextRun.getTime())) {
                logger.error({ file, id }, 'Reminder inbox: invalid schedule_value for update');
                fs.renameSync(filePath, path.join(PROCESSED_DIR, file));
                continue;
              }
              updates.schedule_value = json.schedule_value;
              updates.next_run = nextRun.toISOString();
            }

            updateTask(id, updates);
            logger.info({ id, updates }, 'Reminder inbox: task updated');

          } else if (action === 'cancel') {
            const existing = getTaskById(id);
            if (!existing) {
              logger.error({ file, id }, 'Reminder inbox: task not found for cancel');
              fs.renameSync(filePath, path.join(PROCESSED_DIR, file));
              continue;
            }

            deleteTask(id);
            logger.info({ id }, 'Reminder inbox: task cancelled');

          } else {
            logger.error({ file, action }, 'Reminder inbox: unknown action');
          }

          // 처리 완료: processed로 이동
          fs.renameSync(filePath, path.join(PROCESSED_DIR, file));

        } catch (fileErr) {
          logger.error({ file, err: fileErr }, 'Reminder inbox: error processing file');
          // 파싱 실패 등의 에러는 파일을 스킵하고 계속
          try {
            fs.renameSync(
              path.join(REMINDER_INBOX_DIR, file),
              path.join(PROCESSED_DIR, file),
            );
          } catch { /* 이동 실패도 무시 */ }
        }
      }
    } catch (err) {
      logger.error({ err }, 'Reminder inbox watcher error');
    } finally {
      polling = false;
    }
  }, POLL_INTERVAL);
}

/**
 * Betty-specific MCP tool: create_reminder
 * Atomically creates vault-outbox JSON + IPC schedule_task JSON.
 * Fork separation: this file is betty-only; ipc-mcp-stdio.ts imports it.
 */

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { z } from 'zod';
import fs from 'fs';
import path from 'path';
import crypto from 'crypto';

const IPC_DIR = '/workspace/ipc';
const TASKS_DIR = path.join(IPC_DIR, 'tasks');
const VAULT_OUTBOX_DIR = '/workspace/extra/vault-outbox';

function writeFileAtomic(filePath: string, data: object): void {
  const dir = path.dirname(filePath);
  fs.mkdirSync(dir, { recursive: true });
  const tempPath = `${filePath}.tmp`;
  fs.writeFileSync(tempPath, JSON.stringify(data, null, 2));
  fs.renameSync(tempPath, filePath);
}

export function registerCreateReminderTool(
  server: McpServer,
  chatJid: string,
  groupFolder: string,
): void {
  server.tool(
    'create_reminder',
    `Create a reminder: saves a vault note (with reminder date) AND schedules a Telegram notification in one atomic operation. Use this for ALL reminder requests instead of schedule_task.

Internally writes:
1. /workspace/extra/vault-outbox/{uuid}.json — vault note with reminder frontmatter
2. /workspace/ipc/tasks/{taskId}.json — once-type schedule task for Telegram notification

SCHEDULE VALUE FORMAT: Local time WITHOUT timezone suffix (e.g., "2026-03-20T09:00:00"). Default time is 09:00 if user does not specify.
REMINDER DATE: YYYY-MM-DD format matching the schedule date.`,
    {
      prompt: z.string().describe('Telegram notification text to send at the scheduled time'),
      content: z.string().describe('Note body in markdown'),
      type: z.enum(['idea', 'clipping', 'guide', 'learning', 'journal']).default('idea').describe('Vault category'),
      title_hint: z.string().min(1, '영문 kebab-case 형식이어야 합니다 (예: remind-tim-ferriss)').regex(/^[a-z0-9]+(-[a-z0-9]+)*$/, '영문 kebab-case 형식이어야 합니다 (예: remind-tim-ferriss)').describe('Suggested filename in English kebab-case (e.g., remind-tim-ferriss)'),
      tags: z.array(z.string()).default([]).describe('Tag array'),
      project: z.string().default('').describe('Project name'),
      schedule_value: z.string().describe('Local time ISO 8601 without timezone suffix (e.g., "2026-03-20T09:00:00")'),
      reminder_date: z.string().describe('Reminder datetime in YYYY-MM-DDTHH:mm format (e.g., "2026-03-20T09:00"). Use the same date and time as schedule_value.'),
    },
    async (args) => {
      // Validate schedule_value: must not have timezone suffix
      if (/[Zz]$/.test(args.schedule_value) || /[+-]\d{2}:\d{2}$/.test(args.schedule_value)) {
        return {
          content: [{ type: 'text' as const, text: `schedule_value must be local time without timezone suffix. Got "${args.schedule_value}" — use format like "2026-03-20T09:00:00".` }],
          isError: true,
        };
      }
      const scheduleDate = new Date(args.schedule_value);
      if (isNaN(scheduleDate.getTime())) {
        return {
          content: [{ type: 'text' as const, text: `Invalid schedule_value: "${args.schedule_value}". Use local time format like "2026-03-20T09:00:00".` }],
          isError: true,
        };
      }

      // Validate reminder_date (YYYY-MM-DD or YYYY-MM-DDTHH:mm)
      if (!/^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$/.test(args.reminder_date)) {
        return {
          content: [{ type: 'text' as const, text: `Invalid reminder_date: "${args.reminder_date}". Use YYYY-MM-DDTHH:mm format (e.g., "2026-03-20T09:00").` }],
          isError: true,
        };
      }

      const uuid = crypto.randomUUID();
      const taskId = `task-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const now = new Date().toISOString();

      try {
        // 1. Write vault-outbox JSON
        const vaultOutboxPath = path.join(VAULT_OUTBOX_DIR, `${uuid}.json`);
        const vaultData = {
          id: uuid,
          type: args.type,
          content: args.content,
          title_hint: args.title_hint,
          tags: args.tags,
          project: args.project,
          source: 'telegram',
          created: now,
          reminder: args.reminder_date,
          reminder_id: taskId,
        };
        writeFileAtomic(vaultOutboxPath, vaultData);

        // 2. Write IPC schedule_task JSON
        const taskFilename = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}.json`;
        const taskPath = path.join(TASKS_DIR, taskFilename);
        const taskData = {
          type: 'schedule_task',
          taskId,
          prompt: args.prompt,
          schedule_type: 'once',
          schedule_value: args.schedule_value,
          context_mode: 'isolated',
          targetJid: chatJid,
          createdBy: groupFolder,
          timestamp: now,
        };
        writeFileAtomic(taskPath, taskData);

        return {
          content: [{ type: 'text' as const, text: `Reminder created. Vault note: ${uuid}.json. Task: ${taskId} scheduled at ${args.schedule_value}.` }],
        };
      } catch (err) {
        return {
          content: [{ type: 'text' as const, text: `Failed to create reminder: ${err instanceof Error ? err.message : String(err)}` }],
          isError: true,
        };
      }
    },
  );
}

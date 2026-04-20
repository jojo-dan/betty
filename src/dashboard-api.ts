/**
 * Dashboard API server for betty Dashboard (v1.x track).
 * Exposes read-only VPS state over HTTP on 127.0.0.1:8318 (default).
 * Protected by X-Betty-Dashboard-Secret header.
 *
 * API contract (SSOT: versions/v1.1.0/build-plan.md §API 계약):
 *   GET /api/dashboard/skills   → { skills: SkillSummary[] }
 *   GET /api/dashboard/queue    → { scheduled, outbox, reminderInbox: QueueSectionSnapshot }
 *   GET /api/dashboard/vps      → { metrics: VPSMetricSnapshot[], generatedAt: ISO8601 }
 *   GET /api/dashboard/history  → { entries: HistoryEntrySnapshot[] }
 *
 * Unauthorized (missing/wrong secret) → 401 { error: 'unauthorized' }
 * Internal error                      → 500 { error: 'internal_error' }
 */
import { createServer, Server, IncomingMessage, ServerResponse } from 'http';
import fs from 'fs';
import path from 'path';
import { exec } from 'child_process';

import { BETTY_DASHBOARD_SECRET } from './config.js';
import { logger } from './logger.js';
import { getAllTasks, getMessagesBySkillId, getRecentMessages } from './db.js';
import {
  extractSkillBody,
  extractSpecLinks,
  formatUptime2Units,
} from './dashboard-format.js';

// ---------------------------------------------------------------------------
// Shared interfaces (mirror of dashboard/src/lib/data/dashboard.ts)
// ---------------------------------------------------------------------------

interface SkillCall {
  entryId: string;
  ts: string;
}

interface SkillSummary {
  id: string;
  name: string;
  description: string;
  body: string;
  specLinks: string[];
  recentCalls: SkillCall[];
}

interface QueueItemDetail {
  action?: string;
  targetPath?: string;
  prompt?: string;
  createdAt?: string;
}

interface QueueItemSummary {
  id: string;
  primary: string;
  secondary: string;
  trailingLabel?: string;
  detail?: QueueItemDetail;
}

interface QueueSectionSnapshot {
  badgeLabel: string;
  waitingCount: number;
  nextLabel?: string;
  items: QueueItemSummary[];
}

interface QueueSnapshot {
  scheduled: QueueSectionSnapshot;
  outbox: QueueSectionSnapshot;
  reminderInbox: QueueSectionSnapshot;
}

type StatusBadgeTone = 'success' | 'warning' | 'error' | 'neutral';

interface VPSMetricSnapshot {
  id: string;
  label: string;
  value: string | number;
  unit?: string;
  trend?: string;
  tone: StatusBadgeTone;
  badgeLabel: string;
}

interface HistoryResult {
  kind: 'task-done' | 'outbox-processed' | 'message';
  output?: string;
  notePath?: string;
}

interface HistoryEntrySnapshot {
  id: string;
  timestamp: string;
  source: 'messages' | 'task' | 'outbox';
  primary: string;
  secondary: string;
  skillId?: string;
  full?: string;
  result?: HistoryResult;
}

// ---------------------------------------------------------------------------
// In-memory VPS cache (5s TTL — exec is expensive)
// ---------------------------------------------------------------------------

interface VpsCache {
  data: { metrics: VPSMetricSnapshot[]; generatedAt: string };
  ts: number;
}

const vpsCache = new Map<'vps', VpsCache>();
const VPS_CACHE_TTL_MS = 5_000;

// ---------------------------------------------------------------------------
// Handler: /api/dashboard/skills
// ---------------------------------------------------------------------------

async function handleSkills(): Promise<{ skills: SkillSummary[] }> {
  const skillsDir = path.join(process.cwd(), 'container', 'skills');
  let dirents: fs.Dirent[];
  try {
    dirents = fs.readdirSync(skillsDir, { withFileTypes: true });
  } catch {
    return { skills: [] };
  }

  const skills: SkillSummary[] = [];

  for (const dirent of dirents) {
    if (!dirent.isDirectory()) continue;
    if (!dirent.name.startsWith('betty-')) continue;

    const skillMdPath = path.join(skillsDir, dirent.name, 'SKILL.md');
    let description = '';
    let body = '';
    let specLinks: string[] = [];

    try {
      const content = fs.readFileSync(skillMdPath, 'utf-8');
      body = extractSkillBody(content);
      specLinks = extractSpecLinks(content);

      // Try explicit "description:" key in frontmatter
      const descKey = content.match(/^description:\s*(.+)$/m);
      if (descKey) {
        description = descKey[1].trim();
      } else {
        // Fall back to first non-empty paragraph in body
        const firstParagraph = body
          .split(/\n{2,}/)
          .map((p) => p.replace(/^#+\s+/, '').trim())
          .find((p) => p.length > 0);
        description = firstParagraph ?? '';
        // Strip leading # heading chars (single line headings used as description)
        if (description.startsWith('#')) {
          description = description.replace(/^#+\s*/, '');
        }
      }
    } catch {
      description = '';
      body = '';
      specLinks = [];
    }

    // recentCalls: messages 테이블의 skill_id 역매핑(Top 10).
    // v1.2.0 현재 skill_id 기록 경로는 옵션 I(null 유지)로 빈 배열 반환이
    // 일반적이지만, 실 데이터가 들어오면 자동으로 채워진다.
    let recentCalls: SkillCall[] = [];
    try {
      const rows = getMessagesBySkillId(dirent.name, 10);
      recentCalls = rows.map((r) => ({
        entryId: `msg-${r.id}`,
        ts: r.timestamp,
      }));
    } catch (err) {
      logger.warn(
        { err, skill: dirent.name },
        'Dashboard API: skill recentCalls query failed',
      );
    }

    skills.push({
      id: dirent.name,
      name: dirent.name,
      description: description.slice(0, 200),
      body,
      specLinks,
      recentCalls,
    });
  }

  return { skills };
}

// ---------------------------------------------------------------------------
// Handler: /api/dashboard/queue
// ---------------------------------------------------------------------------

async function handleQueue(): Promise<QueueSnapshot> {
  // --- scheduled tasks from DB ---
  const allTasks = getAllTasks();
  const activeTasks = allTasks.filter((t) => t.status === 'active');
  activeTasks.sort((a, b) => {
    if (!a.next_run) return 1;
    if (!b.next_run) return -1;
    return a.next_run < b.next_run ? -1 : 1;
  });
  const scheduledItems: QueueItemSummary[] = activeTasks
    .slice(0, 3)
    .map((t) => ({
      id: t.id,
      primary: t.prompt.slice(0, 80),
      secondary: `${t.schedule_type} · ${t.group_folder}`,
      trailingLabel: t.next_run
        ? new Date(t.next_run).toLocaleTimeString('ko-KR', {
            hour: '2-digit',
            minute: '2-digit',
          })
        : undefined,
      detail: {
        action: t.schedule_type,
        targetPath: t.group_folder,
        prompt: t.prompt,
        createdAt: t.created_at,
      },
    }));

  const scheduledNextLabel =
    activeTasks.length > 0 && activeTasks[0].next_run
      ? `다음 실행 ${new Date(activeTasks[0].next_run).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })} · ${activeTasks[0].prompt.slice(0, 30)}`
      : undefined;

  // --- vault-outbox FS ---
  const outboxDir = path.join(process.cwd(), 'data', 'vault-outbox');
  const outboxItems = readJsonFiles(outboxDir, 5);

  // --- reminder-inbox FS ---
  const reminderDir = path.join(process.cwd(), 'data', 'reminder-inbox');
  const reminderItems = readJsonFiles(reminderDir, 5);

  return {
    scheduled: {
      badgeLabel: 'DB',
      waitingCount: activeTasks.length,
      nextLabel: scheduledNextLabel,
      items: scheduledItems,
    },
    outbox: {
      badgeLabel: 'FS',
      waitingCount: outboxItems.length,
      nextLabel:
        outboxItems.length > 0
          ? `가장 오래된 · ${outboxItems[outboxItems.length - 1].id}`
          : undefined,
      items: outboxItems,
    },
    reminderInbox: {
      badgeLabel: 'FS',
      waitingCount: reminderItems.length,
      items: reminderItems,
    },
  };
}

/** Read .json files from a directory (not recursing into subdirs). */
function readJsonFiles(dir: string, maxItems: number): QueueItemSummary[] {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return [];
  }

  const jsonFiles = entries
    .filter(
      (e) => e.isFile() && e.name.endsWith('.json') && !e.name.startsWith('.'),
    )
    .sort((a, b) => {
      const statA = fs.statSync(path.join(dir, a.name));
      const statB = fs.statSync(path.join(dir, b.name));
      return statB.mtimeMs - statA.mtimeMs; // newest first
    })
    .slice(0, maxItems);

  return jsonFiles.map((f) => {
    const fpath = path.join(dir, f.name);
    const stat = fs.statSync(fpath);
    let label: string | undefined;
    let detail: QueueItemDetail | undefined;
    try {
      const raw = fs.readFileSync(fpath, 'utf-8');
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      const action =
        typeof parsed['action'] === 'string'
          ? parsed['action']
          : typeof parsed['type'] === 'string'
            ? parsed['type']
            : undefined;
      label = action;

      const pickString = (key: string): string | undefined =>
        typeof parsed[key] === 'string' ? (parsed[key] as string) : undefined;

      detail = {
        action,
        // target_path 키가 있으면 우선, 없으면 title_hint(outbox) 등 대체
        targetPath:
          pickString('target_path') ??
          pickString('targetPath') ??
          pickString('title_hint'),
        prompt: pickString('prompt') ?? pickString('content'),
        createdAt:
          pickString('created') ??
          pickString('created_at') ??
          pickString('schedule_value'),
      };
    } catch {
      /* ignore parse errors */
    }
    return {
      id: f.name.replace('.json', ''),
      primary: label ?? f.name,
      secondary: `${path.basename(dir)}/${f.name}`,
      trailingLabel: new Date(stat.mtimeMs).toLocaleTimeString('ko-KR', {
        hour: '2-digit',
        minute: '2-digit',
      }),
      detail,
    };
  });
}

// ---------------------------------------------------------------------------
// Handler: /api/dashboard/vps
// ---------------------------------------------------------------------------

async function handleVps(): Promise<{
  metrics: VPSMetricSnapshot[];
  generatedAt: string;
}> {
  const cached = vpsCache.get('vps');
  if (cached && Date.now() - cached.ts < VPS_CACHE_TTL_MS) {
    return cached.data;
  }

  const result = await execVpsMetrics();
  vpsCache.set('vps', { data: result, ts: Date.now() });
  return result;
}

function execVpsMetrics(): Promise<{
  metrics: VPSMetricSnapshot[];
  generatedAt: string;
}> {
  const cmd = [
    "echo \"CPU:$(top -bn1 | grep 'Cpu(s)' | awk '{print $2}')\"",
    'echo "MEM:$(free -m | awk \'/Mem:/{printf \"%d/%dMB\", $3, $2}\')"',
    'echo "DISK:$(df -h / | awk \'NR==2{printf "%s/%s %s", $3, $2, $5}\')"',
    'echo "UPTIME:$(uptime -p)"',
    'echo "BETTY:$(systemctl is-active betty)"',
  ].join('; ');

  return new Promise((resolve) => {
    exec(cmd, (err, stdout) => {
      const generatedAt = new Date().toISOString();

      if (err) {
        logger.warn({ err }, 'Dashboard API: VPS exec error');
        resolve({
          metrics: [
            {
              id: 'error',
              label: 'VPS',
              value: 'unavailable',
              tone: 'error',
              badgeLabel: '오류',
            },
          ],
          generatedAt,
        });
        return;
      }

      const lines = stdout.trim().split('\n');
      const get = (prefix: string): string | null => {
        const line = lines.find((l) => l.startsWith(prefix + ':'));
        return line ? line.slice(prefix.length + 1).trim() : null;
      };

      // CPU
      const cpuRaw = get('CPU');
      const cpuVal = cpuRaw !== null ? parseFloat(cpuRaw) : NaN;
      const cpuDisplay = isNaN(cpuVal) ? 'N/A' : cpuVal.toFixed(1);
      const cpuTone: StatusBadgeTone = isNaN(cpuVal)
        ? 'neutral'
        : cpuVal >= 90
          ? 'error'
          : cpuVal >= 70
            ? 'warning'
            : 'success';
      const cpuBadge = isNaN(cpuVal)
        ? 'N/A'
        : cpuVal >= 90
          ? '위험'
          : cpuVal >= 70
            ? '주의'
            : '정상';

      // MEM
      const memRaw = get('MEM');
      let memDisplay = 'N/A';
      let memTone: StatusBadgeTone = 'neutral';
      let memBadge = 'N/A';
      let memTrend: string | undefined;
      let memPct = NaN;
      if (memRaw) {
        const m = memRaw.match(/^(\d+)\/(\d+)MB$/);
        if (m) {
          const used = parseInt(m[1], 10);
          const total = parseInt(m[2], 10);
          memPct = total > 0 ? (used / total) * 100 : NaN;
          const pctStr = isNaN(memPct) ? '?' : `${memPct.toFixed(0)}%`;
          memDisplay = pctStr;
          memTrend = `${used} / ${total} MB`;
          memTone = isNaN(memPct)
            ? 'neutral'
            : memPct >= 90
              ? 'error'
              : memPct >= 70
                ? 'warning'
                : 'success';
          memBadge = isNaN(memPct)
            ? 'N/A'
            : memPct >= 90
              ? '위험'
              : memPct >= 70
                ? '주의'
                : '정상';
        }
      }

      // DISK
      const diskRaw = get('DISK');
      let diskDisplay = 'N/A';
      let diskTone: StatusBadgeTone = 'neutral';
      let diskBadge = 'N/A';
      let diskTrend: string | undefined;
      let diskPct = NaN;
      if (diskRaw) {
        const dm = diskRaw.match(/^(\S+)\/(\S+)\s+(\d+)%$/);
        if (dm) {
          const used = dm[1];
          const total = dm[2];
          diskPct = parseInt(dm[3], 10);
          diskDisplay = `${diskPct}%`;
          diskTrend = `${used} / ${total}`;
          diskTone = isNaN(diskPct)
            ? 'neutral'
            : diskPct >= 85
              ? 'error'
              : diskPct >= 70
                ? 'warning'
                : 'success';
          diskBadge = isNaN(diskPct)
            ? 'N/A'
            : diskPct >= 85
              ? '위험'
              : diskPct >= 70
                ? '주의'
                : '정상';
        }
      }

      // UPTIME — Linux `uptime -p` 원문을 한국어 축약 2단위로 변환(v1.2.0).
      const uptimeRaw = get('UPTIME');
      const uptimeDisplay = uptimeRaw ? formatUptime2Units(uptimeRaw) : 'N/A';

      // BETTY
      const bettyRaw = get('BETTY');
      const bettyDisplay = bettyRaw || 'N/A';
      const bettyTone: StatusBadgeTone =
        bettyRaw === 'active'
          ? 'success'
          : bettyRaw !== null
            ? 'error'
            : 'neutral';
      const bettyBadge =
        bettyRaw === 'active' ? '정상' : bettyRaw !== null ? '위험' : 'N/A';

      // Health summary (for logging, not returned to client directly)
      const bettyDown = bettyRaw !== null && bettyRaw !== 'active';
      const hasCritical =
        cpuVal >= 90 ||
        (!isNaN(memPct) && memPct >= 90) ||
        diskPct >= 85 ||
        bettyDown;
      const hasWarn =
        !hasCritical &&
        (cpuVal >= 70 || (!isNaN(memPct) && memPct >= 70) || diskPct >= 70);

      logger.debug(
        { hasCritical, hasWarn },
        'Dashboard API: VPS metrics computed',
      );

      const metrics: VPSMetricSnapshot[] = [
        {
          id: 'cpu',
          label: 'CPU',
          value: cpuDisplay,
          unit: '%',
          tone: cpuTone,
          badgeLabel: cpuBadge,
        },
        {
          id: 'memory',
          label: '메모리',
          value: memDisplay,
          unit: '%',
          trend: memTrend,
          tone: memTone,
          badgeLabel: memBadge,
        },
        {
          id: 'disk',
          label: '디스크',
          value: diskDisplay,
          unit: '%',
          trend: diskTrend,
          tone: diskTone,
          badgeLabel: diskBadge,
        },
        {
          id: 'uptime',
          label: 'uptime',
          value: uptimeDisplay,
          tone: 'success',
          badgeLabel: 'active',
        },
        {
          id: 'systemctl',
          label: 'systemctl',
          value: bettyDisplay,
          tone: bettyTone,
          badgeLabel: bettyBadge,
        },
      ];

      resolve({ metrics, generatedAt });
    });
  });
}

// ---------------------------------------------------------------------------
// Handler: /api/dashboard/history
// ---------------------------------------------------------------------------

async function handleHistory(): Promise<{ entries: HistoryEntrySnapshot[] }> {
  const entries: HistoryEntrySnapshot[] = [];

  // 1. DB messages (recent 50, non-bot)
  try {
    const msgs = getRecentMessages(50);
    for (const m of msgs) {
      entries.push({
        id: `msg-${m.id}`,
        timestamp: m.timestamp,
        source: 'messages',
        primary: m.content.slice(0, 80),
        secondary: `${m.sender} · ${m.chat_jid}`,
        skillId: m.skill_id ?? undefined,
        full: m.content,
        result: { kind: 'message' },
      });
    }
  } catch (err) {
    logger.warn({ err }, 'Dashboard API: history messages query failed');
  }

  // 2. scheduled_tasks status=done (recent 20)
  try {
    const allTasks = getAllTasks();
    const doneTasks = allTasks
      .filter((t) => t.status === 'completed')
      .sort((a, b) =>
        (b.last_run ?? b.created_at) > (a.last_run ?? a.created_at) ? 1 : -1,
      )
      .slice(0, 20);
    for (const t of doneTasks) {
      entries.push({
        id: `task-${t.id}`,
        timestamp: t.last_run ?? t.created_at,
        source: 'task',
        primary: t.prompt.slice(0, 80),
        secondary: `scheduled_tasks · ${t.group_folder}`,
        full: t.prompt,
        result: {
          kind: 'task-done',
          output: t.last_result ?? undefined,
        },
      });
    }
  } catch (err) {
    logger.warn({ err }, 'Dashboard API: history tasks query failed');
  }

  // 3. vault-outbox/processed/ (recent 20 by mtime)
  try {
    const processedDir = path.join(
      process.cwd(),
      'data',
      'vault-outbox',
      'processed',
    );
    let procEntries: fs.Dirent[] = [];
    try {
      procEntries = fs.readdirSync(processedDir, { withFileTypes: true });
    } catch {
      /* dir may not exist */
    }

    const jsonFiles = procEntries
      .filter(
        (e) =>
          e.isFile() && e.name.endsWith('.json') && !e.name.startsWith('.'),
      )
      .map((e) => ({
        name: e.name,
        mtime: fs.statSync(path.join(processedDir, e.name)).mtimeMs,
      }))
      .sort((a, b) => b.mtime - a.mtime)
      .slice(0, 20);

    for (const f of jsonFiles) {
      let full: string | undefined;
      let notePath: string | undefined;
      try {
        const raw = fs.readFileSync(path.join(processedDir, f.name), 'utf-8');
        const parsed = JSON.parse(raw) as Record<string, unknown>;
        if (typeof parsed['content'] === 'string') {
          full = parsed['content'] as string;
        }
        const pickString = (key: string): string | undefined =>
          typeof parsed[key] === 'string' ? (parsed[key] as string) : undefined;
        notePath =
          pickString('target_path') ??
          pickString('targetPath') ??
          pickString('title_hint');
      } catch {
        /* ignore — fallback to file name */
      }
      entries.push({
        id: `outbox-${f.name.replace('.json', '')}`,
        timestamp: new Date(f.mtime).toISOString(),
        source: 'outbox',
        primary: f.name.replace('.json', ''),
        secondary: 'vault-outbox/processed/',
        full,
        result: {
          kind: 'outbox-processed',
          notePath,
        },
      });
    }
  } catch (err) {
    logger.warn({ err }, 'Dashboard API: history outbox scan failed');
  }

  // Merge and sort by timestamp DESC
  entries.sort((a, b) => (b.timestamp > a.timestamp ? 1 : -1));

  return { entries };
}

// ---------------------------------------------------------------------------
// HTTP server
// ---------------------------------------------------------------------------

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(payload),
  });
  res.end(payload);
}

async function handleRequest(
  req: IncomingMessage,
  res: ServerResponse,
): Promise<void> {
  // Auth middleware
  const secret = req.headers['x-betty-dashboard-secret'];
  if (!BETTY_DASHBOARD_SECRET || secret !== BETTY_DASHBOARD_SECRET) {
    sendJson(res, 401, { error: 'unauthorized' });
    return;
  }

  const method = req.method ?? 'GET';
  const url = req.url ?? '/';

  logger.debug({ method, url }, 'Dashboard API request');

  // Router
  try {
    if (method === 'GET' && url === '/api/dashboard/skills') {
      const data = await handleSkills();
      sendJson(res, 200, data);
    } else if (method === 'GET' && url === '/api/dashboard/queue') {
      const data = await handleQueue();
      sendJson(res, 200, data);
    } else if (method === 'GET' && url === '/api/dashboard/vps') {
      const data = await handleVps();
      sendJson(res, 200, data);
    } else if (method === 'GET' && url === '/api/dashboard/history') {
      const data = await handleHistory();
      sendJson(res, 200, data);
    } else {
      sendJson(res, 404, { error: 'not_found' });
    }
  } catch (err) {
    logger.error({ err, method, url }, 'Dashboard API handler error');
    sendJson(res, 500, { error: 'internal_error' });
  }
}

export function startDashboardApi(
  port: number,
  host = '127.0.0.1',
): Promise<Server> {
  return new Promise((resolve, reject) => {
    const server = createServer((req, res) => {
      handleRequest(req, res).catch((err) => {
        logger.error({ err }, 'Dashboard API unhandled error');
        if (!res.headersSent) {
          sendJson(res, 500, { error: 'internal_error' });
        }
      });
    });

    server.listen(port, host, () => {
      logger.info({ port, host }, 'Dashboard API started');
      resolve(server);
    });

    server.on('error', reject);
  });
}

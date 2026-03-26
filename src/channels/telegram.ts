import { exec } from 'child_process';

import { Api, Bot } from 'grammy';

import {
  ASSISTANT_NAME,
  TRIGGER_PATTERN,
  OWNER_TELEGRAM_ID,
  SESSION_WARN_CONVERSATIONS,
  SESSION_WARN_SIZE_MB,
  SESSION_CRITICAL_CONVERSATIONS,
  SESSION_CRITICAL_SIZE_MB,
} from '../config.js';
import { readEnvFile } from '../env.js';
import { logger } from '../logger.js';
import { getCurrentModel, setModel, getValidAliases } from '../betty-model.js';
import { downloadMediaFile } from '../betty-media.js';
import { registerChannel, ChannelOpts } from './registry.js';
import {
  Channel,
  OnChatMetadata,
  OnInboundMessage,
  RegisteredGroup,
} from '../types.js';

export interface SessionInfo {
  conversations: number;
  sizeMB: number;
  model: string | null;
}

export interface TelegramChannelOpts {
  onMessage: OnInboundMessage;
  onChatMetadata: OnChatMetadata;
  registeredGroups: () => Record<string, RegisteredGroup>;
  clearSession?: (chatJid: string) => Promise<string | null>;
  getSessionInfo?: (chatJid: string) => Promise<SessionInfo | null>;
}

/**
 * Send a message with Telegram Markdown parse mode, falling back to plain text.
 * Claude's output naturally matches Telegram's Markdown v1 format:
 *   *bold*, _italic_, `code`, ```code blocks```, [links](url)
 */
async function sendTelegramMessage(
  api: { sendMessage: Api['sendMessage'] },
  chatId: string | number,
  text: string,
  options: { message_thread_id?: number } = {},
): Promise<void> {
  try {
    await api.sendMessage(chatId, text, {
      ...options,
      parse_mode: 'Markdown',
    });
  } catch (err) {
    // Fallback: send as plain text if Markdown parsing fails
    logger.debug({ err }, 'Markdown send failed, falling back to plain text');
    await api.sendMessage(chatId, text, options);
  }
}

export class TelegramChannel implements Channel {
  name = 'telegram';

  private bot: Bot | null = null;
  private opts: TelegramChannelOpts;
  private botToken: string;
  private mediaGroupBuffer: Map<
    string,
    {
      messages: Array<{
        fileId: string;
        fileUniqueId: string;
        caption: string;
        folder: string;
      }>;
      timer: ReturnType<typeof setTimeout>;
      ctx: any;
    }
  > = new Map();

  constructor(botToken: string, opts: TelegramChannelOpts) {
    this.botToken = botToken;
    this.opts = opts;
  }

  async connect(): Promise<void> {
    this.bot = new Bot(this.botToken);

    // Command to get chat ID (useful for registration)
    this.bot.command('chatid', (ctx) => {
      const chatId = ctx.chat.id;
      const chatType = ctx.chat.type;
      const chatName =
        chatType === 'private'
          ? ctx.from?.first_name || 'Private'
          : (ctx.chat as any).title || 'Unknown';

      ctx.reply(
        `Chat ID: \`tg:${chatId}\`\nName: ${chatName}\nType: ${chatType}`,
        { parse_mode: 'Markdown' },
      );
    });

    // Command to check bot status
    this.bot.command('ping', (ctx) => {
      ctx.reply('베티는 여기 있는 거야.');
    });

    // Command to view or change the active Claude model
    this.bot.command('model', (ctx) => {
      const arg = (ctx.match as string | undefined)?.trim() || '';
      if (!arg) {
        const current = getCurrentModel();
        if (current) {
          ctx.reply(`지금 베티가 쓰는 건 ${current}인 거야.`);
        } else {
          ctx.reply(
            '지금은 기본값인 거야. 바꾸고 싶으면 /model [모델명]으로 말해.',
          );
        }
        return;
      }
      const resolved = setModel(arg);
      if (resolved) {
        ctx.reply(`${resolved}로 바꿨어. 다음 대화부터 적용되는 거야.`);
      } else {
        const aliases = getValidAliases().join(', ');
        ctx.reply(
          `${arg}는 베티가 모르는 모델인 거야. 사용 가능한 건 ${aliases} — 또는 claude-로 시작하는 모델 ID일까.`,
        );
      }
    });

    // Command to restart betty service or VPS (owner only)
    this.bot.command('restart', async (ctx) => {
      if (!OWNER_TELEGRAM_ID || ctx.from?.id.toString() !== OWNER_TELEGRAM_ID)
        return;

      const arg = (ctx.match as string | undefined)?.trim().toLowerCase() || '';
      if (arg === 'vps') {
        await ctx.reply('VPS를 재시작하는 거야. 좀 걸릴까.');
        setTimeout(() => exec('shutdown -r now'), 1000);
      } else if (arg === '' || arg === 'betty') {
        await ctx.reply('잠깐 기다려. 베티가 다시 돌아올 거야.');
        setTimeout(() => exec('systemctl restart betty'), 1000);
      } else {
        await ctx.reply(
          '그건 모르는 명령인 거야. /restart 또는 /restart vps 로 말해.',
        );
      }
    });

    // Command to clear session (owner only)
    this.bot.command('clear', async (ctx) => {
      if (!OWNER_TELEGRAM_ID || ctx.from?.id.toString() !== OWNER_TELEGRAM_ID)
        return;

      const chatJid = `tg:${ctx.chat.id}`;
      if (!this.opts.clearSession) return;

      const folder = await this.opts.clearSession(chatJid);
      if (folder) {
        await ctx.reply('세션을 초기화했어. 다음 대화부터 새로 시작인 거야.');
      } else {
        await ctx.reply('등록된 채팅이 아닌 거야.');
      }
    });

    // Command to show session context health
    this.bot.command('context', async (ctx) => {
      const chatJid = `tg:${ctx.chat.id}`;
      if (!this.opts.getSessionInfo) return;

      const info = await this.opts.getSessionInfo(chatJid);
      if (!info) {
        await ctx.reply('세션이 없는 거야.');
        return;
      }

      const convTag =
        info.conversations >= SESSION_CRITICAL_CONVERSATIONS
          ? '[!!]'
          : info.conversations >= SESSION_WARN_CONVERSATIONS
            ? '[!]'
            : '[ok]';
      const sizeTag =
        info.sizeMB >= SESSION_CRITICAL_SIZE_MB
          ? '[!!]'
          : info.sizeMB >= SESSION_WARN_SIZE_MB
            ? '[!]'
            : '[ok]';

      const isCritical =
        info.conversations >= SESSION_CRITICAL_CONVERSATIONS ||
        info.sizeMB >= SESSION_CRITICAL_SIZE_MB;
      const isWarn =
        info.conversations >= SESSION_WARN_CONVERSATIONS ||
        info.sizeMB >= SESSION_WARN_SIZE_MB;

      let voice: string;
      if (isCritical) {
        voice =
          '세션이 너무 무거운 거야. /clear 로 초기화하지 않으면 안 되는 거야.';
      } else if (isWarn) {
        voice =
          '세션이 좀 무거워진 거야. 슬슬 /clear 를 생각해야 할까.';
      } else {
        voice = '세션은 아직 여유 있는 거야.';
      }

      const model = info.model || '기본값';
      const lines = [
        voice,
        '',
        `${convTag} 대화: ${info.conversations}/${SESSION_CRITICAL_CONVERSATIONS}회`,
        `${sizeTag} 크기: ${info.sizeMB}MB/${SESSION_CRITICAL_SIZE_MB}MB`,
        `[--] 모델: ${model}`,
      ];

      await ctx.reply(lines.join('\n'));
    });

    this.bot.on('message:text', async (ctx) => {
      // Skip commands
      if (ctx.message.text.startsWith('/')) return;

      const chatJid = `tg:${ctx.chat.id}`;
      let content = ctx.message.text;
      const timestamp = new Date(ctx.message.date * 1000).toISOString();
      const senderName =
        ctx.from?.first_name ||
        ctx.from?.username ||
        ctx.from?.id.toString() ||
        'Unknown';
      const sender = ctx.from?.id.toString() || '';
      const msgId = ctx.message.message_id.toString();

      // Determine chat name
      const chatName =
        ctx.chat.type === 'private'
          ? senderName
          : (ctx.chat as any).title || chatJid;

      // Translate Telegram @bot_username mentions into TRIGGER_PATTERN format.
      // Telegram @mentions (e.g., @andy_ai_bot) won't match TRIGGER_PATTERN
      // (e.g., ^@Andy\b), so we prepend the trigger when the bot is @mentioned.
      const botUsername = ctx.me?.username?.toLowerCase();
      if (botUsername) {
        const entities = ctx.message.entities || [];
        const isBotMentioned = entities.some((entity) => {
          if (entity.type === 'mention') {
            const mentionText = content
              .substring(entity.offset, entity.offset + entity.length)
              .toLowerCase();
            return mentionText === `@${botUsername}`;
          }
          return false;
        });
        if (isBotMentioned && !TRIGGER_PATTERN.test(content)) {
          content = `@${ASSISTANT_NAME} ${content}`;
        }
      }

      // Store chat metadata for discovery
      const isGroup =
        ctx.chat.type === 'group' || ctx.chat.type === 'supergroup';
      this.opts.onChatMetadata(
        chatJid,
        timestamp,
        chatName,
        'telegram',
        isGroup,
      );

      // Only deliver full message for registered groups
      const group = this.opts.registeredGroups()[chatJid];
      if (!group) {
        logger.debug(
          { chatJid, chatName },
          'Message from unregistered Telegram chat',
        );
        return;
      }

      // Deliver message — startMessageLoop() will pick it up
      this.opts.onMessage(chatJid, {
        id: msgId,
        chat_jid: chatJid,
        sender,
        sender_name: senderName,
        content,
        timestamp,
        is_from_me: false,
      });

      logger.info(
        { chatJid, chatName, sender: senderName },
        'Telegram message stored',
      );
    });

    // Handle non-text messages with placeholders so the agent knows something was sent
    const storeNonText = async (ctx: any, placeholder: string) => {
      const chatJid = `tg:${ctx.chat.id}`;
      const group = this.opts.registeredGroups()[chatJid];
      if (!group) return;

      const timestamp = new Date(ctx.message.date * 1000).toISOString();
      const senderName =
        ctx.from?.first_name ||
        ctx.from?.username ||
        ctx.from?.id?.toString() ||
        'Unknown';
      const caption = ctx.message.caption ? ` ${ctx.message.caption}` : '';

      const isGroup =
        ctx.chat.type === 'group' || ctx.chat.type === 'supergroup';
      this.opts.onChatMetadata(
        chatJid,
        timestamp,
        undefined,
        'telegram',
        isGroup,
      );
      this.opts.onMessage(chatJid, {
        id: ctx.message.message_id.toString(),
        chat_jid: chatJid,
        sender: ctx.from?.id?.toString() || '',
        sender_name: senderName,
        content: `${placeholder}${caption}`,
        timestamp,
        is_from_me: false,
      });
    };

    const storeMediaMessage = async (
      ctx: any,
      fileId: string | undefined,
      fileUniqueId: string | undefined,
      prefix: string,
      ext: string,
      successTemplate: (fileName: string) => string,
      fallback: string,
    ) => {
      const chatJid = `tg:${ctx.chat.id}`;
      const group = this.opts.registeredGroups()[chatJid];
      if (!group) return;

      let content = fallback;
      if (fileId && fileUniqueId && this.bot) {
        const filePath = await downloadMediaFile(
          this.bot,
          fileId,
          fileUniqueId,
          group.folder,
          prefix,
          ext,
        );
        if (filePath) {
          const fileName = filePath.split('/').pop()!;
          content = successTemplate(fileName);
        }
      }

      const caption = ctx.message.caption ? ` ${ctx.message.caption}` : '';
      const timestamp = new Date(ctx.message.date * 1000).toISOString();
      const senderName =
        ctx.from?.first_name ||
        ctx.from?.username ||
        ctx.from?.id?.toString() ||
        'Unknown';
      const isGroup =
        ctx.chat.type === 'group' || ctx.chat.type === 'supergroup';

      this.opts.onChatMetadata(
        chatJid,
        timestamp,
        undefined,
        'telegram',
        isGroup,
      );
      this.opts.onMessage(chatJid, {
        id: ctx.message.message_id.toString(),
        chat_jid: chatJid,
        sender: ctx.from?.id?.toString() || '',
        sender_name: senderName,
        content: `${content}${caption}`,
        timestamp,
        is_from_me: false,
      });
    };

    this.bot.on('message:photo', async (ctx) => {
      const photo = ctx.message.photo?.at(-1);
      const mediaGroupId = ctx.message.media_group_id;

      // 단일 사진 (앨범 아님) → 기존 즉시 처리
      if (!mediaGroupId) {
        return storeMediaMessage(
          ctx,
          photo?.file_id,
          photo?.file_unique_id,
          'photo',
          'jpg',
          (f) => `[Photo: /workspace/media/${f}]`,
          '[Photo]',
        );
      }

      // 앨범 사진 → 버퍼링 (다운로드는 플러시 시점에 일괄 처리)
      const chatJid = `tg:${ctx.chat.id}`;
      const registeredGroup = this.opts.registeredGroups()[chatJid];
      if (!registeredGroup) return;

      const caption = ctx.message.caption || '';

      const existing = this.mediaGroupBuffer.get(mediaGroupId);
      if (existing) {
        existing.messages.push({
          fileId: photo?.file_id || '',
          fileUniqueId: photo?.file_unique_id || '',
          caption,
          folder: registeredGroup.folder,
        });
        clearTimeout(existing.timer);
        existing.timer = setTimeout(
          () => this.flushMediaGroup(mediaGroupId),
          300,
        );
      } else {
        const timer = setTimeout(() => this.flushMediaGroup(mediaGroupId), 300);
        this.mediaGroupBuffer.set(mediaGroupId, {
          messages: [
            {
              fileId: photo?.file_id || '',
              fileUniqueId: photo?.file_unique_id || '',
              caption,
              folder: registeredGroup.folder,
            },
          ],
          timer,
          ctx,
        });
      }
    });
    this.bot.on('message:animation', (ctx) => {
      const animation = ctx.message.animation;
      return storeMediaMessage(
        ctx,
        animation?.file_id,
        animation?.file_unique_id,
        'animation',
        'mp4',
        (f) => `[Video: /workspace/media/${f}]`,
        '[Animation]',
      );
    });
    this.bot.on('message:video', (ctx) => {
      const video = ctx.message.video;
      return storeMediaMessage(
        ctx,
        video?.file_id,
        video?.file_unique_id,
        'video',
        'mp4',
        (f) => `[Video: /workspace/media/${f}]`,
        '[Video]',
      );
    });
    this.bot.on('message:voice', (ctx) => {
      const voice = ctx.message.voice;
      return storeMediaMessage(
        ctx,
        voice?.file_id,
        voice?.file_unique_id,
        'voice',
        'oga',
        (f) => `[Voice: /workspace/media/${f}]`,
        '[Voice message]',
      );
    });
    this.bot.on('message:audio', (ctx) => {
      const audio = ctx.message.audio;
      return storeMediaMessage(
        ctx,
        audio?.file_id,
        audio?.file_unique_id,
        'audio',
        'mp3',
        (f) => `[Audio: /workspace/media/${f}]`,
        '[Audio]',
      );
    });
    this.bot.on('message:document', (ctx) => {
      const doc = ctx.message.document;
      const name = doc?.file_name || 'file';
      return storeMediaMessage(
        ctx,
        doc?.file_id,
        doc?.file_unique_id,
        'doc',
        name.includes('.') ? name.split('.').pop()! : 'bin',
        (f) => `[Document: /workspace/media/${f}]`,
        `[Document: ${name}]`,
      );
    });
    this.bot.on('message:sticker', (ctx) => {
      const emoji = ctx.message.sticker?.emoji || '';
      storeNonText(ctx, `[Sticker ${emoji}]`);
    });
    this.bot.on('message:location', (ctx) => storeNonText(ctx, '[Location]'));
    this.bot.on('message:contact', (ctx) => storeNonText(ctx, '[Contact]'));

    // Handle errors gracefully
    this.bot.catch((err) => {
      logger.error({ err: err.message }, 'Telegram bot error');
    });

    // Start polling — returns a Promise that resolves when started
    return new Promise<void>((resolve) => {
      this.bot!.start({
        onStart: async (botInfo) => {
          logger.info(
            { username: botInfo.username, id: botInfo.id },
            'Telegram bot connected',
          );
          console.log(`\n  Telegram bot: @${botInfo.username}`);
          console.log(
            `  Send /chatid to the bot to get a chat's registration ID\n`,
          );
          await this.bot!.api.setMyCommands([
            { command: 'chatid', description: '채팅 ID 표시' },
            { command: 'ping', description: '봇 상태 확인' },
            { command: 'model', description: '현재 모델 표시 / 모델 변경' },
            { command: 'restart', description: '서비스/VPS 재시작' },
            { command: 'clear', description: '세션 초기화' },
            { command: 'context', description: '세션 상태 확인' },
          ]);
          resolve();
        },
      });
    });
  }

  private async flushMediaGroup(mediaGroupId: string): Promise<void> {
    const group = this.mediaGroupBuffer.get(mediaGroupId);
    if (!group) return;
    this.mediaGroupBuffer.delete(mediaGroupId);

    const ctx = group.ctx;
    const chatJid = `tg:${ctx.chat.id}`;

    // 모든 사진 다운로드를 병렬로 실행
    const photoContents = await Promise.all(
      group.messages.map(async (m) => {
        if (!m.fileId || !m.fileUniqueId || !this.bot) return '[Photo]';
        const filePath = await downloadMediaFile(
          this.bot,
          m.fileId,
          m.fileUniqueId,
          m.folder,
          'photo',
          'jpg',
        );
        if (filePath) {
          const fileName = filePath.split('/').pop()!;
          return `[Photo: /workspace/media/${fileName}]`;
        }
        return '[Photo]';
      }),
    );

    const allPhotos = photoContents.join(' ');
    const caption = group.messages.find((m) => m.caption)?.caption || '';
    const content = caption ? `${allPhotos} ${caption}` : allPhotos;

    const timestamp = new Date(ctx.message.date * 1000).toISOString();
    const senderName =
      ctx.from?.first_name ||
      ctx.from?.username ||
      ctx.from?.id?.toString() ||
      'Unknown';
    const isGroup = ctx.chat.type === 'group' || ctx.chat.type === 'supergroup';

    this.opts.onChatMetadata(
      chatJid,
      timestamp,
      undefined,
      'telegram',
      isGroup,
    );
    this.opts.onMessage(chatJid, {
      id: ctx.message.message_id.toString(),
      chat_jid: chatJid,
      sender: ctx.from?.id?.toString() || '',
      sender_name: senderName,
      content,
      timestamp,
      is_from_me: false,
    });

    logger.info(
      { mediaGroupId, photoCount: group.messages.length },
      'Media group flushed',
    );
  }

  async sendMessage(jid: string, text: string): Promise<void> {
    if (!this.bot) {
      logger.warn('Telegram bot not initialized');
      return;
    }

    try {
      const numericId = jid.replace(/^tg:/, '');

      // Telegram has a 4096 character limit per message — split if needed
      const MAX_LENGTH = 4096;
      if (text.length <= MAX_LENGTH) {
        await sendTelegramMessage(this.bot.api, numericId, text);
      } else {
        for (let i = 0; i < text.length; i += MAX_LENGTH) {
          await sendTelegramMessage(
            this.bot.api,
            numericId,
            text.slice(i, i + MAX_LENGTH),
          );
        }
      }
      logger.info({ jid, length: text.length }, 'Telegram message sent');
    } catch (err) {
      logger.error({ jid, err }, 'Failed to send Telegram message');
    }
  }

  isConnected(): boolean {
    return this.bot !== null;
  }

  ownsJid(jid: string): boolean {
    return jid.startsWith('tg:');
  }

  async disconnect(): Promise<void> {
    if (this.bot) {
      this.bot.stop();
      this.bot = null;
      logger.info('Telegram bot stopped');
    }
  }

  async setTyping(jid: string, isTyping: boolean): Promise<void> {
    if (!this.bot || !isTyping) return;
    try {
      const numericId = jid.replace(/^tg:/, '');
      await this.bot.api.sendChatAction(numericId, 'typing');
    } catch (err) {
      logger.debug({ jid, err }, 'Failed to send Telegram typing indicator');
    }
  }
}

registerChannel('telegram', (opts: ChannelOpts) => {
  const envVars = readEnvFile(['TELEGRAM_BOT_TOKEN']);
  const token =
    process.env.TELEGRAM_BOT_TOKEN || envVars.TELEGRAM_BOT_TOKEN || '';
  if (!token) {
    logger.warn('Telegram: TELEGRAM_BOT_TOKEN not set');
    return null;
  }
  return new TelegramChannel(token, opts);
});

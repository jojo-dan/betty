"""
Betty Telegram CLI — send a message and print the response.

Usage:
  cd ~/hq/projects/betty
  source tests/.venv/bin/activate
  python tests/tg_send.py "메시지 내용"
  python tests/tg_send.py "메시지 내용" --timeout 120
  python tests/tg_send.py --file photo.jpg "캡션"
  python tests/tg_send.py --file a.jpg --file b.jpg "캡션"
  python tests/tg_send.py --file photo.jpg

Exit codes:
  0 — response received (response text printed to stdout)
  1 — timeout, no response
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

from dotenv import dotenv_values
from telethon import TelegramClient

env = dotenv_values(Path(__file__).parent / ".env.telethon")
API_ID = int(env["TELETHON_API_ID"])
API_HASH = env["TELETHON_API_HASH"]
BOT_USERNAME = "re_betty_bot"
SESSION_FILE = str(Path(__file__).parent / "telethon_session")


async def wait_for_response(client, bot_entity, after_date, timeout):
    deadline = time.time() + timeout if timeout > 0 else None
    while deadline is None or time.time() < deadline:
        messages = await client.get_messages(bot_entity, limit=10)
        for msg in messages:
            if int(msg.date.timestamp()) >= int(after_date) and msg.sender_id == bot_entity.id:
                return msg
        await asyncio.sleep(3)
    return None


async def main(message, timeout: int, files=None):
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()

    bot = await client.get_entity(BOT_USERNAME)
    ts = time.time()

    if files is not None:
        if len(files) == 1:
            await client.send_file(bot, files[0], caption=message)
        else:
            await client.send_file(bot, files, caption=message)
    else:
        await client.send_message(bot, message)

    resp = await wait_for_response(client, bot, ts, timeout)

    await client.disconnect()

    if resp:
        print(resp.text)
        return 0
    else:
        sys.stderr.write(f"timeout: no response within {timeout}s\n")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send a message to Betty and print the response.")
    parser.add_argument("message", nargs="?", default=None, help="Message to send")
    parser.add_argument("--timeout", type=int, default=180, help="Seconds to wait for response (default: 180, 0 = no timeout)")
    parser.add_argument("--file", dest="files", action="append", default=None, metavar="FILE", help="File(s) to send. Can be specified multiple times for album.")
    args = parser.parse_args()

    if args.files is None and args.message is None:
        sys.stderr.write("error: provide a message and/or --file\n")
        sys.exit(1)

    exit_code = asyncio.run(main(args.message, args.timeout, args.files))
    sys.exit(exit_code)

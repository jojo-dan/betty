"""
Betty E2E Test via Telethon.

Usage:
  cd ~/hq/projects/betty
  source tests/.venv/bin/activate
  python tests/e2e_betty.py

First run requires interactive Telegram auth (phone + code).
"""

import asyncio
import os
import sys
import time
from pathlib import Path

from dotenv import dotenv_values
from telethon import TelegramClient

# Load config
env = dotenv_values(Path(__file__).parent / ".env.telethon")
API_ID = int(env["TELETHON_API_ID"])
API_HASH = env["TELETHON_API_HASH"]
BOT_USERNAME = "re_betty_bot"
SESSION_FILE = str(Path(__file__).parent / "telethon_session")
TIMEOUT = 90  # seconds to wait for bot response


async def wait_for_response(client, bot_entity, after_date, timeout=TIMEOUT):
    """Wait for a new message from the bot after a given timestamp."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        messages = await client.get_messages(bot_entity, limit=5)
        for msg in messages:
            if msg.date.timestamp() > after_date and not msg.out:
                return msg
        await asyncio.sleep(3)
    return None


async def main():
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()

    print(f"Logged in as: {(await client.get_me()).first_name}")

    bot = await client.get_entity(BOT_USERNAME)
    results = []

    # S-1: Basic response
    print("\n--- S-1: 기본 응답 테스트 ---")
    ts = time.time()
    await client.send_message(bot, "안녕! 넌 누구야?")
    print("  메시지 전송 완료. 응답 대기 중...")
    resp = await wait_for_response(client, bot, ts)
    if resp:
        print(f"  ✅ 응답 수신 ({int(time.time() - ts)}초): {resp.text[:100]}...")
        results.append(("S-1 기본 응답", True))
    else:
        print(f"  ❌ {TIMEOUT}초 내 응답 없음")
        results.append(("S-1 기본 응답", False))

    await asyncio.sleep(5)

    # S-2: Multi-turn context
    print("\n--- S-2: 멀티턴 컨텍스트 ---")
    ts = time.time()
    await client.send_message(bot, "내 이름은 조조야. 기억해줘.")
    resp1 = await wait_for_response(client, bot, ts)
    if resp1:
        print(f"  첫 응답: {resp1.text[:80]}...")
        await asyncio.sleep(5)
        ts2 = time.time()
        await client.send_message(bot, "내 이름이 뭐라고 했지?")
        resp2 = await wait_for_response(client, bot, ts2)
        if resp2 and "조조" in resp2.text:
            print(f"  ✅ 컨텍스트 유지 확인: {resp2.text[:80]}...")
            results.append(("S-2 멀티턴", True))
        elif resp2:
            print(f"  ⚠️ 응답은 있으나 컨텍스트 불확실: {resp2.text[:80]}...")
            results.append(("S-2 멀티턴", False))
        else:
            print(f"  ❌ 두번째 응답 없음")
            results.append(("S-2 멀티턴", False))
    else:
        print(f"  ❌ 첫 응답 없음")
        results.append(("S-2 멀티턴", False))

    # Summary
    print("\n=== 결과 요약 ===")
    for name, ok in results:
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  {status}: {name}")

    passed = sum(1 for _, ok in results if ok)
    print(f"\n  {passed}/{len(results)} 통과")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

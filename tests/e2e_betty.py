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
import re
import subprocess
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
DB_PATH = "/opt/betty/store/messages.db"
TIMEOUT = 300  # seconds to wait for bot response (YouTube analysis can take 4+ minutes)
FIXTURES_DIR = Path(__file__).parent / "fixtures"


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


def reset_betty_session():
    """Reset Betty's telegram_main session for test isolation."""
    print("--- 세션 초기화 (테스트 격리) ---")
    cmds = [
        "systemctl stop betty",
        f'sqlite3 {DB_PATH} "DELETE FROM sessions WHERE group_folder=\'telegram_main\';"',
        "rm -rf /opt/betty/data/sessions/telegram_main/.claude/debug/*",
        "systemctl start betty",
    ]
    for cmd in cmds:
        subprocess.run(cmd, shell=True, timeout=120)
    # Wait for betty to fully start
    time.sleep(5)
    print("  ✅ 세션 초기화 완료\n")


async def main():
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()

    print(f"Logged in as: {(await client.get_me()).first_name}")

    # Reset session before tests for isolation (prevents false positives in S-2 multi-turn)
    reset_betty_session()

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

    await asyncio.sleep(5)

    # S-R1: Reminder pipeline (2-step verification)
    print("\n--- S-R1: 리마인더 파이프라인 (2단계 검증) ---")

    # Record task count before sending reminder request
    before_count = 0
    try:
        out = subprocess.run(
            ["sqlite3", DB_PATH, "SELECT COUNT(*) FROM scheduled_tasks WHERE schedule_type='once' AND status='active';"],
            capture_output=True, text=True, timeout=5,
        )
        before_count = int(out.stdout.strip())
    except Exception:
        pass

    ts = time.time()
    await client.send_message(bot, "내일 오전 10시에 운동하라고 알려줘")
    print("  메시지 전송 완료. 응답 대기 중...")
    resp = await wait_for_response(client, bot, ts)

    sr1_step1 = False
    sr1_step2 = False

    if resp:
        print(f"  응답: {resp.text[:120]}...")
        # Step 1: 응답에 예약 시각 정보 포함 여부
        time_patterns = [r"10시", r"10:00", r"오전.*10", r"내일"]
        if any(re.search(p, resp.text) for p in time_patterns):
            print("  ✅ 1단계: 응답에 예약 시각 정보 포함")
            sr1_step1 = True
        else:
            print("  ❌ 1단계: 응답에 예약 시각 정보 미포함")

        # Step 2: DB에 새 once 태스크 존재 확인 (최대 15초 대기 — IPC 처리 지연 고려)
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                out = subprocess.run(
                    ["sqlite3", DB_PATH, "SELECT COUNT(*) FROM scheduled_tasks WHERE schedule_type='once' AND status='active';"],
                    capture_output=True, text=True, timeout=5,
                )
                after_count = int(out.stdout.strip())
                if after_count > before_count:
                    sr1_step2 = True
                    break
            except Exception:
                pass
            await asyncio.sleep(2)

        if sr1_step2:
            print(f"  ✅ 2단계: DB에 새 once 태스크 확인 ({before_count} → {after_count})")
        else:
            print(f"  ❌ 2단계: DB에 새 once 태스크 미확인 (count 변화 없음)")
    else:
        print(f"  ❌ {TIMEOUT}초 내 응답 없음")

    sr1_pass = sr1_step1 and sr1_step2
    results.append(("S-R1 리마인더", sr1_pass))

    await asyncio.sleep(5)

    # S-M1: Voice message
    print("\n--- S-M1: 음성 메시지 처리 ---")
    voice_file = FIXTURES_DIR / "sample.oga"
    ts = time.time()
    await client.send_file(bot, str(voice_file), voice_note=True)
    print("  음성 파일 전송 완료. 응답 대기 중...")
    resp = await wait_for_response(client, bot, ts, timeout=TIMEOUT)
    if resp:
        # PASS if Betty responded (content-based or fallback both acceptable)
        text = resp.text or ""
        is_placeholder_only = text.strip() == "[Voice message]"
        if not is_placeholder_only:
            print(f"  ✅ 응답 수신 ({int(time.time() - ts)}초): {text[:100]}...")
            results.append(("S-M1 음성 처리", True))
        else:
            print(f"  ❌ 플레이스홀더만 응답: {text[:100]}")
            results.append(("S-M1 음성 처리", False))
    else:
        print(f"  ❌ {TIMEOUT}초 내 응답 없음")
        results.append(("S-M1 음성 처리", False))

    await asyncio.sleep(5)

    # S-M2: Document read
    print("\n--- S-M2: 문서 파일 읽기 ---")
    doc_file = FIXTURES_DIR / "sample.txt"
    ts = time.time()
    await client.send_file(bot, str(doc_file), caption="읽어줘")
    print("  문서 파일 전송 완료. 응답 대기 중...")
    resp = await wait_for_response(client, bot, ts, timeout=TIMEOUT)
    if resp:
        text = resp.text or ""
        if "테스트 문서" in text or "Betty" in text or "확인" in text:
            print(f"  ✅ 파일 내용 포함 응답 ({int(time.time() - ts)}초): {text[:100]}...")
            results.append(("S-M2 문서 읽기", True))
        else:
            print(f"  ⚠️ 응답은 있으나 파일 내용 불확인: {text[:100]}...")
            results.append(("S-M2 문서 읽기", False))
    else:
        print(f"  ❌ {TIMEOUT}초 내 응답 없음")
        results.append(("S-M2 문서 읽기", False))

    await asyncio.sleep(5)

    # S-YT1: YouTube Shorts
    print("\n--- S-YT1: YouTube Shorts ---")
    ts = time.time()
    await client.send_message(bot, "https://youtube.com/shorts/EiYkkp7QCJc")
    print("  YouTube Shorts URL 전송 완료. 응답 대기 중...")
    resp = await wait_for_response(client, bot, ts, timeout=TIMEOUT)
    if resp:
        print(f"  ✅ 응답 수신 ({int(time.time() - ts)}초): {(resp.text or '')[:100]}...")
        results.append(("S-YT1 YouTube Shorts", True))
    else:
        print(f"  ❌ {TIMEOUT}초 내 응답 없음")
        results.append(("S-YT1 YouTube Shorts", False))

    await asyncio.sleep(5)

    # S-YT2: YouTube general (TED talk with subtitles)
    print("\n--- S-YT2: YouTube 일반 영상 (자막) ---")
    ts = time.time()
    await client.send_message(bot, "https://www.youtube.com/watch?v=arj7oStGLkU")
    print("  YouTube URL 전송 완료. 응답 대기 중...")
    resp = await wait_for_response(client, bot, ts, timeout=TIMEOUT)
    if resp:
        print(f"  ✅ 응답 수신 ({int(time.time() - ts)}초): {(resp.text or '')[:100]}...")
        results.append(("S-YT2 YouTube 일반", True))
    else:
        print(f"  ❌ {TIMEOUT}초 내 응답 없음")
        results.append(("S-YT2 YouTube 일반", False))

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

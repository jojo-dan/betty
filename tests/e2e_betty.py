"""
Betty E2E Test via Telethon.

Usage:
  cd ~/hq/projects/betty
  source tests/.venv/bin/activate
  python tests/e2e_betty.py

  # Skip teardown (DB cleanup + vault cleanup):
  python tests/e2e_betty.py --no-cleanup

First run requires interactive Telegram auth (phone + code).
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
import uuid
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
VAULT_OUTBOX = "/opt/betty/data/vault-outbox"
VAULT_OUTBOX_PROCESSED = "/opt/betty/data/vault-outbox/processed"
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


def get_processed_done_basenames():
    """Return set of UUID basenames from .done files in the processed directory.
    Reads directly from filesystem (test runs on VPS where processed/ is local)."""
    try:
        import glob
        done_files = glob.glob(f"{VAULT_OUTBOX_PROCESSED}/*.done")
        return set(os.path.basename(f).replace('.done', '') for f in done_files)
    except Exception:
        return set()


TYPE_FOLDER_MAP = {"idea": "notes", "clipping": "clippings", "guide": "notes", "learning": "notes", "journal": "daily"}


def generate_filename_py(raw, note_type="idea"):
    """Reproduce vault-watcher.sh generate_filename() logic in Python."""
    name = re.sub(r'^#+ *', '', raw)
    name = name.lower()
    name = re.sub(r'[^a-z0-9 -]', '', name)
    name = re.sub(r' +', ' ', name).strip()
    name = name.replace(' ', '-')
    name = re.sub(r'-+', '-', name)
    name = name.strip('-')
    name = name[:60]
    if not name:
        from datetime import datetime
        name = f"{note_type}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    return name


def resolve_vault_note_paths(new_done_uuids):
    """Trace back vault note paths from UUID list by reading .done/.json files.
    Reads directly from filesystem (test runs on VPS where processed/ is local)."""
    paths = []
    for uuid_str in new_done_uuids:
        try:
            with open(f"{VAULT_OUTBOX_PROCESSED}/{uuid_str}.done") as f:
                action = f.read().strip()
            if action != "create":
                continue

            with open(f"{VAULT_OUTBOX_PROCESSED}/{uuid_str}.json") as f:
                data = json.load(f)
            title_hint = data.get("title_hint", "")
            note_type = data.get("type", "idea")

            if not title_hint:
                continue

            folder = TYPE_FOLDER_MAP.get(note_type, "notes")
            note_name = generate_filename_py(title_hint, note_type)

            paths.append(f"{folder}/{note_name}.md")
            paths.append(f"{folder}/{note_name}-{uuid_str[:8]}.md")
            print(f"  [teardown] create note detected: {uuid_str} → {folder}/{note_name}.md")
        except Exception as e:
            print(f"  [teardown] ⚠️ resolve 실패 ({uuid_str}): {e}")
    return paths


def get_once_task_ids():
    """Return the set of active once-type task IDs currently in scheduled_tasks."""
    try:
        out = subprocess.run(
            ["sqlite3", DB_PATH, "SELECT id FROM scheduled_tasks WHERE schedule_type='once' AND status='active';"],
            capture_output=True, text=True, timeout=5,
        )
        ids = set(line.strip() for line in out.stdout.splitlines() if line.strip())
        return ids
    except Exception:
        return set()


def teardown(pre_task_ids, vault_note_paths, no_cleanup=False):
    """Clean up test artifacts: VPS DB tasks + vault notes via cleanup manifest."""
    if no_cleanup:
        print("\n--- teardown 스킵 (--no-cleanup) ---")
        return

    print("\n--- teardown: 테스트 산출물 정리 ---")

    # 2a. VPS DB: delete once tasks created during this test run
    post_task_ids = get_once_task_ids()
    new_task_ids = post_task_ids - pre_task_ids
    deleted_tasks = 0
    if new_task_ids:
        for task_id in new_task_ids:
            try:
                subprocess.run(
                    ["sqlite3", DB_PATH, f"DELETE FROM scheduled_tasks WHERE id='{task_id}';"],
                    capture_output=True, text=True, timeout=5,
                )
                deleted_tasks += 1
            except Exception as e:
                print(f"  ⚠️ 태스크 삭제 실패 (id={task_id}): {e}")
        print(f"  ✅ DB: {deleted_tasks}개 once 태스크 삭제 ({', '.join(new_task_ids)})")
    else:
        print(f"  DB: 정리할 새 once 태스크 없음")

    # 2b. vault-outbox cleanup manifest (delete-notes action)
    processed_paths = 0
    if vault_note_paths:
        manifest_id = str(uuid.uuid4())
        manifest = {
            "action": "delete-notes",
            "id": manifest_id,
            "paths": list(vault_note_paths),
        }
        manifest_file = f"{VAULT_OUTBOX}/{manifest_id}.json"
        try:
            subprocess.run(
                ["bash", "-c", f"echo '{json.dumps(manifest)}' > '{manifest_file}'"],
                capture_output=True, text=True, timeout=5,
            )
            processed_paths = len(vault_note_paths)
            print(f"  ✅ vault-outbox: cleanup manifest 작성 ({processed_paths}개 노트) → {manifest_file}")
        except Exception as e:
            print(f"  ⚠️ cleanup manifest 작성 실패: {e}")
    else:
        print(f"  vault: 정리할 테스트 노트 없음")

    print(f"  요약: {deleted_tasks}개 DB 태스크 삭제, {processed_paths}개 vault 노트 cleanup manifest 작성")


async def main(no_cleanup=False):
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()

    print(f"Logged in as: {(await client.get_me()).first_name}")

    # Collect pre-test once task IDs for teardown delta calculation
    pre_task_ids = get_once_task_ids()
    pre_processed_dones = get_processed_done_basenames()

    # vault notes created during this test run (populated per-scenario if applicable)
    vault_note_paths = []

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

    # Teardown: clean up test artifacts
    # vault 파이프라인 완료 대기 (비동기 — agent container → vault-outbox → vault-watcher → processed/)
    # agent container가 vault-outbox JSON을 쓰기까지 수 분 소요될 수 있음
    print("\n--- vault 파이프라인 대기 ---")
    for attempt in range(36):  # 36 * 5s = 180s max
        post_processed_dones = get_processed_done_basenames()
        if len(post_processed_dones) > len(pre_processed_dones):
            print(f"  ✅ 새 processed 파일 감지 ({(attempt + 1) * 5}초 대기)")
            break
        time.sleep(5)
        if (attempt + 1) % 6 == 0:
            print(f"  대기 중... ({(attempt + 1) * 5}초)")
    else:
        print("  ⚠️ vault 파이프라인 대기 타임아웃 (180초)")
        post_processed_dones = get_processed_done_basenames()

    # vault 노트 역추적
    new_done_uuids = post_processed_dones - pre_processed_dones
    if new_done_uuids:
        vault_note_paths = resolve_vault_note_paths(new_done_uuids)

    teardown(pre_task_ids, vault_note_paths, no_cleanup=no_cleanup)

    await client.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Betty E2E Test")
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        default=False,
        help="Skip teardown (DB task cleanup + vault cleanup manifest)",
    )
    args = parser.parse_args()
    asyncio.run(main(no_cleanup=args.no_cleanup))

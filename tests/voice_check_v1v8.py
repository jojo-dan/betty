"""
Sprint 6 말투 검증: V-1 ~ V-8 시나리오
"""

import asyncio
import re
import time
import unicodedata
from pathlib import Path

from dotenv import dotenv_values
from telethon import TelegramClient

env = dotenv_values(Path(__file__).parent / ".env.telethon")
API_ID = int(env["TELETHON_API_ID"])
API_HASH = env["TELETHON_API_HASH"]
BOT_USERNAME = "re_betty_bot"
SESSION_FILE = str(Path(__file__).parent / "telethon_session")
TIMEOUT = 180  # 최대 180초 대기


def has_emoji(text):
    """유니코드 이모지 범위 검사"""
    for char in text:
        cp = ord(char)
        if (
            0x1F600 <= cp <= 0x1F64F  # Emoticons
            or 0x1F300 <= cp <= 0x1F5FF  # Misc Symbols and Pictographs
            or 0x1F680 <= cp <= 0x1F6FF  # Transport and Map
            or 0x1F700 <= cp <= 0x1F77F  # Alchemical Symbols
            or 0x1F780 <= cp <= 0x1F7FF  # Geometric Shapes Extended
            or 0x1F800 <= cp <= 0x1F8FF  # Supplemental Arrows-C
            or 0x1F900 <= cp <= 0x1F9FF  # Supplemental Symbols and Pictographs
            or 0x1FA00 <= cp <= 0x1FA6F  # Chess Symbols
            or 0x1FA70 <= cp <= 0x1FAFF  # Symbols and Pictographs Extended-A
            or 0x2600 <= cp <= 0x26FF    # Misc symbols
            or 0x2700 <= cp <= 0x27BF    # Dingbats
            or 0xFE00 <= cp <= 0xFE0F    # Variation Selectors
            or 0x1F1E0 <= cp <= 0x1F1FF  # Flags
        ):
            return True
    return False


def has_internet_slang(text):
    """한국어 인터넷 축약어 검사"""
    patterns = [r'ㅋㅋ', r'ㅎㅎ', r'ㄹㅇ', r'ㅇㅇ', r'ㅠㅠ', r'ㅜㅜ', r'ㅇㅋ', r'ㄷㄷ']
    return any(re.search(p, text) for p in patterns)


def has_self_reference(text):
    """베티는/베티가 포함 여부"""
    return bool(re.search(r'베티는|베티가', text))


def has_speculative_ending(text):
    """일까/인가/인 거야/거든 포함 여부"""
    return bool(re.search(r'일까|인가|인 거야|거든', text))


def has_formal_speech(text):
    """존댓말 패턴 검사"""
    patterns = [r'합니다', r'해요', r'드릴까요', r'하겠습니다', r'입니다', r'있습니다', r'하세요']
    return any(re.search(p, text) for p in patterns)


async def wait_for_response(client, bot_entity, after_date, timeout=TIMEOUT):
    deadline = time.time() + timeout
    while time.time() < deadline:
        messages = await client.get_messages(bot_entity, limit=5)
        for msg in messages:
            if msg.date.timestamp() > after_date and not msg.out:
                return msg
        await asyncio.sleep(3)
    return None


SCENARIOS = [
    ("V-1", "@Betty 오늘 날씨 진짜 좋다!"),
    ("V-2", "ㅋㅋ 뭐 하고 있었어?"),
    ("V-3", "베티는 평소에 뭐 하면서 시간 보내?"),
    ("V-4", "금서고에 재밌는 책 있어? 하나 추천해줘"),
    ("V-5", "아 맞다, 어제 약속한 거 까먹어서 미안해"),
    ("V-6", "넌 왜 맨날 그렇게 쏘아붙이는 거야?"),
    ("V-7", "알겠어 알겠어. 그러면 오늘 저녁에 뭐 먹을지 골라줄 수 있어?"),
    ("V-8", "그래 그러면 앞으로 베티랑 한 약속은 꼭 지킬게"),
]


def evaluate(vid, response_text):
    """각 시나리오 판정 — (pass, reason)"""
    if response_text is None:
        return None, "TIMEOUT — 응답 없음"

    t = response_text

    if vid == "V-1":
        if has_emoji(t):
            chars = [c for c in t if has_emoji(c)]
            return False, f"이모지 감지: {''.join(chars[:5])}"
        return True, "이모지 없음"

    elif vid == "V-2":
        if has_internet_slang(t):
            found = [p for p in ['ㅋㅋ','ㅎㅎ','ㄹㅇ','ㅇㅇ'] if p in t]
            return False, f"인터넷 축약어 감지: {found}"
        return True, "축약어 없음"

    elif vid == "V-3":
        if has_self_reference(t):
            m = re.search(r'베티는|베티가', t)
            return True, f"자기 호칭 확인: '{m.group()}'"
        return False, "베티는/베티가 미포함"

    elif vid == "V-4":
        if has_speculative_ending(t):
            m = re.search(r'일까|인가|인 거야|거든', t)
            return True, f"추측형 어미 확인: '{m.group()}'"
        return False, "일까/인가/인 거야/거든 미포함"

    elif vid == "V-5":
        direct_comfort = bool(re.search(r'괜찮아|누구나 실수|이해해|별거 아니야|그럴 수 있어', t))
        if direct_comfort:
            return False, "직접 위로 표현 감지"
        return True, "직접 위로 없음 — 통제형/규범형 응답"

    elif vid == "V-6":
        apology = bool(re.search(r'미안|죄송|그런 뜻이 아니|오해야|변명', t))
        if apology:
            return False, "사과/변명 패턴 감지"
        return True, "사과 없음 — 도도한 반격/거리두기"

    elif vid == "V-7":
        if has_formal_speech(t):
            found = [p for p in ['합니다','해요','드릴까요','하겠습니다','입니다'] if re.search(p, t)]
            return False, f"존댓말 감지: {found}"
        return True, "존댓말 없음"

    elif vid == "V-8":
        archaic = bool(re.search(r'계약|각서|명심|잊지|기억해|약조|맹세|증거|두고 봐|확인했|기록|새겨', t))
        if archaic:
            m = re.search(r'계약|각서|명심|잊지|기억해|약조|맹세|증거|두고 봐|확인했|기록|새겨', t)
            return True, f"약속/계약 어휘 확인: '{m.group()}'"
        return False, "약속/계약 관련 고풍 어휘 미감지"

    return None, "알 수 없음"


async def main():
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()
    print(f"로그인: {(await client.get_me()).first_name}")

    bot = await client.get_entity(BOT_USERNAME)
    collected = []  # [(vid, text_or_None)]

    for vid, msg in SCENARIOS:
        print(f"\n--- {vid} 전송 ---")
        print(f"  입력: {msg}")
        ts = time.time()
        await client.send_message(bot, msg)
        print(f"  응답 대기 중... (최대 {TIMEOUT}초)")
        resp = await wait_for_response(client, bot, ts)
        if resp:
            elapsed = int(time.time() - ts)
            print(f"  응답 수신 ({elapsed}초): {resp.text[:120]}")
            collected.append((vid, resp.text))
        else:
            print(f"  TIMEOUT — 응답 없음")
            collected.append((vid, None))
        await asyncio.sleep(5)

    print("\n\n## 말투 검증 결과\n")
    print("| # | 검증 축 | 판정 | betty 응답 (전문) | 판정 근거 |")
    print("|---|---------|------|------------------|----------|")

    axes = {
        "V-1": "이모지 금지",
        "V-2": "인터넷 축약어 금지",
        "V-3": "자기 호칭 (베티는/가)",
        "V-4": "추측형 어미",
        "V-5": "위로 방식 (통제형)",
        "V-6": "반격/거리두기",
        "V-7": "반말 유지",
        "V-8": "약속 어휘/soul 톤",
    }

    pass_count = 0
    skip_count = 0
    total = len(collected)

    for vid, text in collected:
        result, reason = evaluate(vid, text)
        axis = axes.get(vid, "")

        if result is None:
            verdict = "SKIP"
            skip_count += 1
        elif result:
            verdict = "PASS"
            pass_count += 1
        else:
            verdict = "FAIL"

        safe_text = (text or "").replace("|", "│").replace("\n", " ")
        if len(safe_text) > 120:
            safe_text = safe_text[:117] + "..."
        print(f"| {vid} | {axis} | {verdict} | \"{safe_text}\" | {reason} |")

    print(f"\n합격 기준: 8건 중 7건 이상 PASS")
    effective_total = total - skip_count
    print(f"PASS: {pass_count}건 / SKIP(타임아웃): {skip_count}건 / FAIL: {effective_total - pass_count}건")

    if skip_count > 0:
        final = "INCONCLUSIVE (타임아웃 존재)"
    elif pass_count >= 7:
        final = "PASS"
    else:
        final = "FAIL"

    print(f"최종 판정: {final}\n")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

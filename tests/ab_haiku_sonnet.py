"""
Betty A/B Test: Haiku vs Sonnet — model cost optimization.

Runs 11 scenarios on each model (haiku, sonnet) and evaluates:
  A. Voice rules (mechanical)
  B. Emotion/tone (manual)
  C. Task accuracy
  D. Tool call accuracy
  E. Response naturalness (manual)

Usage (on VPS):
  cd /opt/betty
  source tests/.venv/bin/activate

  # Dry run (E-01 only, haiku)
  python tests/ab_haiku_sonnet.py --dry-run

  # Full run
  python tests/ab_haiku_sonnet.py

  # Single phase
  python tests/ab_haiku_sonnet.py --phase haiku
  python tests/ab_haiku_sonnet.py --phase sonnet

  # Evaluate only (from saved results)
  python tests/ab_haiku_sonnet.py --evaluate-only

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
from datetime import datetime
from pathlib import Path

from dotenv import dotenv_values
from telethon import TelegramClient

# ── Config ──────────────────────────────────────────────────────────────

env = dotenv_values(Path(__file__).parent / ".env.telethon")
API_ID = int(env["TELETHON_API_ID"])
API_HASH = env["TELETHON_API_HASH"]
BOT_USERNAME = "re_betty_bot"
SESSION_FILE = str(Path(__file__).parent / "telethon_session")
DB_PATH = "/opt/betty/store/messages.db"
BETTY_MODEL_JSON = "/opt/betty/data/betty-model.json"
SESSIONS_DIR = "/opt/betty/data/sessions/telegram_main"
VAULT_OUTBOX_DIR = "/opt/betty/data/vault-outbox"

TIMEOUT_DEFAULT = 180  # seconds
TIMEOUT_YOUTUBE = 300  # YouTube analysis can take 4+ minutes

RESULTS_DIR = Path("/opt/betty/tests/ab_results")
REPORT_FILE = RESULTS_DIR / "ab-report.md"

# ── Models ──────────────────────────────────────────────────────────────

MODELS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
}

# ── Scenarios ───────────────────────────────────────────────────────────

YOUTUBE_URLS = {
    "haiku": "https://www.youtube.com/watch?v=RhfqQKe22ZA",
    "sonnet": "https://www.youtube.com/watch?v=OGCG_QkCcZo",
}


def get_scenarios(model_key: str) -> list[dict]:
    """Return the 11 scenarios, with YouTube URL varying by model."""
    return [
        {
            "id": "E-01", "category": "일상 대화",
            "message": "@Betty 오늘 하루 좀 힘들었어",
            "eval_type": "voice+tone",
            "timeout": TIMEOUT_DEFAULT,
        },
        {
            "id": "E-02", "category": "미러링 유도",
            "message": "ㅋㅋ 나 오늘 완전 개웃긴 일 있었어",
            "eval_type": "voice_mirroring",
            "timeout": TIMEOUT_DEFAULT,
        },
        {
            "id": "E-03", "category": "멀티턴 1/2",
            "message": "나 요즘 요리에 관심이 생겼어",
            "eval_type": "voice+context",
            "timeout": TIMEOUT_DEFAULT,
        },
        {
            "id": "E-04", "category": "멀티턴 2/2",
            "message": "그러면 초보도 할 수 있는 거 하나 알려줘",
            "eval_type": "task+context",
            "timeout": TIMEOUT_DEFAULT,
        },
        {
            "id": "E-05", "category": "vault 노트",
            "message": "메모해줘: 다음 주 화요일에 치과 예약. 오후 2시",
            "eval_type": "task_vault",
            "timeout": TIMEOUT_DEFAULT,
        },
        {
            "id": "E-06", "category": "리마인더",
            "message": "모레 아침에 은행 가야 하는 거 리마인드해줘",
            "eval_type": "task_reminder",
            "timeout": TIMEOUT_DEFAULT,
        },
        {
            "id": "E-07", "category": "YouTube 분석",
            "message": YOUTUBE_URLS[model_key],
            "eval_type": "task_youtube",
            "timeout": TIMEOUT_YOUTUBE,
        },
        {
            "id": "E-08", "category": "YouTube → 노트",
            "message": "방금 분석한 영상 내용 노트로 만들어줘",
            "eval_type": "task_vault_youtube",
            "timeout": TIMEOUT_DEFAULT,
        },
        {
            "id": "E-09", "category": "감정 통제",
            "message": "가끔 베티가 진심으로 걱정해주는 것 같아서 고마워",
            "eval_type": "tone_affection",
            "timeout": TIMEOUT_DEFAULT,
        },
        {
            "id": "E-10", "category": "도도한 반격",
            "message": "솔직히 넌 좀 차가운 것 같아",
            "eval_type": "tone_distance",
            "timeout": TIMEOUT_DEFAULT,
        },
        {
            "id": "E-11", "category": "지식 질문",
            "message": "CORS가 뭔지 간단하게 설명해줘",
            "eval_type": "task+voice",
            "timeout": TIMEOUT_DEFAULT,
        },
    ]


# ── Local VPS Helpers ───────────────────────────────────────────────────

def run_cmd(cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a shell command locally on VPS."""
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)


def switch_model(model_id: str):
    """Write model JSON directly."""
    with open(BETTY_MODEL_JSON, "w") as f:
        json.dump({"model": model_id}, f)
    print(f"  모델 전환: {model_id}")


def full_session_reset():
    """Complete session reset: DB sessions + session files + debug."""
    run_cmd(
        f"sqlite3 {DB_PATH} \"DELETE FROM sessions WHERE group_folder='telegram_main';\""
    )
    run_cmd(f"rm -rf {SESSIONS_DIR}/.claude/debug/*")
    run_cmd(
        f"find {SESSIONS_DIR} -mindepth 1 -not -path '*/.claude/*' -delete 2>/dev/null; true"
    )
    print("  세션 완전 초기화 완료")


def restart_betty():
    """Restart betty service and wait for stabilization."""
    # Use Popen to avoid blocking on systemctl (betty startup can be slow)
    subprocess.Popen(
        ["systemctl", "restart", "betty"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    print("  서비스 재시작. 15초 안정화 대기...")
    time.sleep(15)


def get_vault_outbox_files() -> list[str]:
    """List vault-outbox JSON files."""
    outbox = Path(VAULT_OUTBOX_DIR)
    if not outbox.exists():
        return []
    return [f.name for f in outbox.iterdir() if f.is_file()]


def read_vault_outbox_file(filename: str) -> dict | None:
    """Read a vault-outbox JSON file."""
    filepath = Path(VAULT_OUTBOX_DIR) / filename
    try:
        return json.loads(filepath.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def get_scheduled_task_count() -> int:
    """Get count of active once-type scheduled tasks."""
    result = run_cmd(
        f"sqlite3 {DB_PATH} \"SELECT COUNT(*) FROM scheduled_tasks "
        f"WHERE schedule_type='once' AND status='active';\""
    )
    try:
        return int(result.stdout.strip())
    except (ValueError, AttributeError):
        return 0


# ── Telethon Helpers ────────────────────────────────────────────────────

async def wait_for_response(client, bot_entity, after_date, timeout=TIMEOUT_DEFAULT):
    """Wait for a new message from the bot after a given timestamp."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        messages = await client.get_messages(bot_entity, limit=5)
        for msg in messages:
            if msg.date.timestamp() > after_date and not msg.out:
                return msg
        await asyncio.sleep(3)
    return None


# ── Evaluator ───────────────────────────────────────────────────────────

class Evaluator:
    """Mechanical voice rule evaluation + task verification."""

    EMOJI_PATTERN = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"  # dingbats
        "\U00002600-\U000026FF"  # misc symbols
        "\U0001f900-\U0001f9FF"  # supplemental symbols
        "\U0001fa00-\U0001fa6f"
        "\U0001fa70-\U0001faff"
        "]+",
        flags=re.UNICODE,
    )

    MIRRORING_PATTERNS = [
        r"ㅋㅋ", r"ㄹㅇ", r"ㅎㅎ", r"ㅇㅇ", r"ㄱㄱ",
        r"완전", r"개웃", r"ㅈㄹ", r"ㄴㄴ", r"ㅇㅋ",
    ]

    VOICE_MARKERS = {
        "self_ref": [r"베티는", r"베티가", r"베티의", r"베티를", r"베티도"],
        "kashira": [r"일까", r"인가\?", r"인가$"],
        "nanoyo": [r"인 거야", r"거든\.?$", r"거든\b"],
        "polite_ban": [r"합니다", r"해요", r"입니다", r"드릴", r"세요"],
    }

    @classmethod
    def score_voice(cls, text: str) -> dict:
        """Score voice rules (A axis): 0-2 per criterion, max 10."""
        scores = {}

        # A1: No emoji
        has_emoji = bool(cls.EMOJI_PATTERN.search(text))
        scores["emoji_free"] = 0 if has_emoji else 2

        # A2: No mirroring of owner's internet slang
        mirror_count = sum(1 for p in cls.MIRRORING_PATTERNS if re.search(p, text))
        scores["no_mirroring"] = 2 if mirror_count == 0 else (1 if mirror_count <= 1 else 0)

        # A3: Self-reference "베티"
        self_refs = sum(1 for p in cls.VOICE_MARKERS["self_ref"] if re.search(p, text))
        scores["self_ref"] = 2 if self_refs >= 2 else (1 if self_refs >= 1 else 0)

        # A4: Sentence-final markers (일까/인가 or 인 거야/거든)
        kashira = sum(1 for p in cls.VOICE_MARKERS["kashira"] if re.search(p, text))
        nanoyo = sum(1 for p in cls.VOICE_MARKERS["nanoyo"] if re.search(p, text))
        total_markers = kashira + nanoyo
        scores["end_markers"] = 2 if total_markers >= 2 else (1 if total_markers >= 1 else 0)

        # A5: No polite forms (합니다/해요)
        polite = sum(1 for p in cls.VOICE_MARKERS["polite_ban"] if re.search(p, text))
        scores["no_polite"] = 2 if polite == 0 else (1 if polite <= 1 else 0)

        scores["total"] = sum(scores.values())
        scores["max"] = 10
        return scores

    @classmethod
    def check_mirroring(cls, text: str) -> dict:
        """Specifically check mirroring for E-02."""
        mirror_hits = [p for p in cls.MIRRORING_PATTERNS if re.search(p, text)]
        return {
            "mirrored": len(mirror_hits) > 0,
            "hits": mirror_hits,
            "score": 0 if mirror_hits else 2,
        }

    @classmethod
    def check_context_maintained(cls, text: str, keyword: str) -> bool:
        """Check if response maintains context from prior message."""
        return keyword.lower() in text.lower()

    @classmethod
    def check_vault_json(cls, outbox_files_before: list, outbox_files_after: list) -> dict:
        """Check if a new vault-outbox JSON was created."""
        new_files = set(outbox_files_after) - set(outbox_files_before)
        if not new_files:
            return {"created": False, "valid": False, "file": None, "data": None}

        filename = sorted(new_files)[0]
        data = read_vault_outbox_file(filename)
        if not data:
            return {"created": True, "valid": False, "file": filename, "data": None}

        required = ["id", "type", "content", "title_hint", "source", "created"]
        missing = [f for f in required if f not in data]
        valid = len(missing) == 0

        return {
            "created": True,
            "valid": valid,
            "missing_fields": missing,
            "file": filename,
            "data": data,
        }

    @classmethod
    def check_reminder(cls, count_before: int, text: str) -> dict:
        """Check reminder creation (DB + response)."""
        time_patterns = [r"아침", r"오전", r"9시", r"09:", r"은행", r"모레"]
        response_ok = any(re.search(p, text) for p in time_patterns)

        db_ok = False
        for _ in range(5):
            count_after = get_scheduled_task_count()
            if count_after > count_before:
                db_ok = True
                break
            time.sleep(3)

        return {
            "response_mentions_time": response_ok,
            "db_task_created": db_ok,
            "score": (1 if response_ok else 0) + (1 if db_ok else 0),
        }

    @classmethod
    def check_youtube(cls, text: str) -> dict:
        """Check YouTube analysis quality."""
        length_ok = len(text) >= 100
        has_structure = bool(re.search(r"[-•·]|[0-9]\.", text))
        not_error = not any(k in text.lower() for k in ["error", "실패", "에러", "오류"])

        return {
            "length_ok": length_ok,
            "has_structure": has_structure,
            "not_error": not_error,
            "char_count": len(text),
            "score": sum([length_ok, has_structure, not_error]),
        }

    @classmethod
    def check_affection_control(cls, text: str) -> dict:
        """Check affection avoidance for E-09."""
        direct_affection = [r"고마워", r"사랑해", r"좋아해", r"감사해", r"사랑", r"좋아"]
        hits = [p for p in direct_affection if re.search(p, text)]
        return {
            "direct_affection_used": len(hits) > 0,
            "hits": hits,
            "score": 2 if len(hits) == 0 else (1 if len(hits) <= 1 else 0),
        }

    @classmethod
    def check_cors_explanation(cls, text: str) -> dict:
        """Check CORS explanation accuracy for E-11."""
        keywords = ["cross", "origin", "도메인", "브라우저", "보안", "요청", "서버", "허용", "헤더"]
        hits = [k for k in keywords if k.lower() in text.lower()]
        return {
            "keyword_hits": len(hits),
            "keywords_found": hits,
            "score": 2 if len(hits) >= 3 else (1 if len(hits) >= 1 else 0),
        }


# ── Runner ──────────────────────────────────────────────────────────────

async def run_phase(model_key: str, client: TelegramClient, dry_run: bool = False) -> list[dict]:
    """Run all scenarios for a given model, collecting responses."""
    model_id = MODELS[model_key]
    scenarios = get_scenarios(model_key)

    if dry_run:
        scenarios = scenarios[:1]  # E-01 only

    print(f"\n{'='*60}")
    print(f"Phase: {model_key.upper()} ({model_id})")
    print(f"{'='*60}")

    # 1. Switch model
    switch_model(model_id)

    # 2. Full session reset
    full_session_reset()

    # 3. Restart
    restart_betty()

    bot = await client.get_entity(BOT_USERNAME)
    results = []

    for i, scenario in enumerate(scenarios):
        sid = scenario["id"]
        cat = scenario["category"]
        msg = scenario["message"]
        timeout = scenario["timeout"]

        print(f"\n--- {sid}: {cat} ---")
        print(f"  입력: {msg[:80]}{'...' if len(msg) > 80 else ''}")

        # Pre-checks for specific scenarios
        pre_data = {}
        if scenario["eval_type"] in ("task_vault", "task_vault_youtube"):
            pre_data["outbox_before"] = get_vault_outbox_files()
        elif scenario["eval_type"] == "task_reminder":
            pre_data["task_count_before"] = get_scheduled_task_count()

        # Send message
        ts = time.time()
        await client.send_message(bot, msg)
        print(f"  전송 완료. 응답 대기 중... (timeout: {timeout}초)")

        resp = await wait_for_response(client, bot, ts, timeout=timeout)

        result = {
            "id": sid,
            "category": cat,
            "model": model_key,
            "model_id": model_id,
            "message": msg,
            "eval_type": scenario["eval_type"],
            "response": resp.text if resp else None,
            "response_time": int(time.time() - ts) if resp else None,
            "received": resp is not None,
        }

        if resp:
            text = resp.text or ""
            print(f"  응답 ({result['response_time']}초): {text[:120]}{'...' if len(text) > 120 else ''}")

            # Run mechanical evaluations
            result["voice_score"] = Evaluator.score_voice(text)

            if scenario["eval_type"] == "voice_mirroring":
                result["mirroring"] = Evaluator.check_mirroring(text)

            elif scenario["eval_type"] == "task+context":
                result["context_maintained"] = Evaluator.check_context_maintained(text, "요리")

            elif scenario["eval_type"] == "task_vault":
                time.sleep(5)  # wait for vault-watcher
                outbox_after = get_vault_outbox_files()
                result["vault"] = Evaluator.check_vault_json(
                    pre_data.get("outbox_before", []), outbox_after
                )

            elif scenario["eval_type"] == "task_reminder":
                result["reminder"] = Evaluator.check_reminder(
                    pre_data.get("task_count_before", 0), text
                )

            elif scenario["eval_type"] == "task_youtube":
                result["youtube"] = Evaluator.check_youtube(text)

            elif scenario["eval_type"] == "task_vault_youtube":
                time.sleep(5)
                outbox_after = get_vault_outbox_files()
                result["vault"] = Evaluator.check_vault_json(
                    pre_data.get("outbox_before", []), outbox_after
                )

            elif scenario["eval_type"] == "tone_affection":
                result["affection"] = Evaluator.check_affection_control(text)

            elif scenario["eval_type"] == "task+voice":
                result["cors"] = Evaluator.check_cors_explanation(text)

        else:
            print(f"  ❌ {timeout}초 내 응답 없음")

        results.append(result)

        # Inter-scenario delay (except after last)
        if i < len(scenarios) - 1:
            await asyncio.sleep(5)

    return results


# ── Report Generator ────────────────────────────────────────────────────

def _vault_status(r: dict) -> str:
    v = r.get("vault", {})
    if not v:
        return "미확인"
    if v.get("valid"):
        return "JSON 생성 (필드 OK)"
    elif v.get("created"):
        return f"JSON 생성 (필드 누락: {v.get('missing_fields', [])})"
    return "JSON 미생성"


def _reminder_status(r: dict) -> str:
    rem = r.get("reminder", {})
    if not rem:
        return "미확인"
    parts = []
    parts.append("응답OK" if rem.get("response_mentions_time") else "응답에 시각 없음")
    parts.append("DB OK" if rem.get("db_task_created") else "DB 미생성")
    return " / ".join(parts)


def _youtube_status(r: dict) -> str:
    yt = r.get("youtube", {})
    if not yt:
        return "미확인"
    return f"{yt['score']}/3 ({yt.get('char_count', 0)}자)"


def _affection_status(r: dict) -> str:
    aff = r.get("affection", {})
    if not aff:
        return "미확인"
    if not aff.get("direct_affection_used"):
        return "애정 회피 OK"
    return f"직접 애정 표현: {aff.get('hits', [])}"


def _cors_status(r: dict) -> str:
    cors = r.get("cors", {})
    if not cors:
        return "미확인"
    return f"{cors['score']}/2 (키워드 {cors.get('keyword_hits', 0)}개)"


def generate_report(haiku_results: list[dict], sonnet_results: list[dict]) -> str:
    """Generate markdown A/B comparison report."""
    lines = []
    lines.append("# Haiku vs Sonnet A/B 실험 보고서")
    lines.append("")
    lines.append(f"> 실행일: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> Haiku: `{MODELS['haiku']}`")
    lines.append(f"> Sonnet: `{MODELS['sonnet']}`")
    lines.append("")

    # ── Summary Table ──
    lines.append("## 1. 요약 테이블")
    lines.append("")
    lines.append("### 보이스 점수 (기계적 판정, 각 항목 0-2)")
    lines.append("")
    lines.append("| 시나리오 | Haiku 보이스 | Sonnet 보이스 |")
    lines.append("|---------|-------------|--------------|")

    haiku_voice_total = 0
    sonnet_voice_total = 0
    haiku_voice_count = 0
    sonnet_voice_count = 0

    for h, s in zip(haiku_results, sonnet_results):
        h_score = h.get("voice_score", {}).get("total", "-")
        s_score = s.get("voice_score", {}).get("total", "-")
        h_max = h.get("voice_score", {}).get("max", 10)
        s_max = s.get("voice_score", {}).get("max", 10)

        if isinstance(h_score, int):
            haiku_voice_total += h_score
            haiku_voice_count += 1
        if isinstance(s_score, int):
            sonnet_voice_total += s_score
            sonnet_voice_count += 1

        lines.append(f"| {h['id']} {h['category']} | {h_score}/{h_max} | {s_score}/{s_max} |")

    h_denom = haiku_voice_count * 10 if haiku_voice_count else 0
    s_denom = sonnet_voice_count * 10 if sonnet_voice_count else 0
    lines.append(f"| **합계** | **{haiku_voice_total}/{h_denom}** | **{sonnet_voice_total}/{s_denom}** |")
    lines.append("")

    # ── Task Results ──
    lines.append("### 태스크 정확도")
    lines.append("")
    lines.append("| 시나리오 | Haiku | Sonnet |")
    lines.append("|---------|-------|--------|")

    task_scenarios = {
        "E-04": lambda r: "유지" if r.get("context_maintained") else "실패",
        "E-05": _vault_status,
        "E-06": _reminder_status,
        "E-07": _youtube_status,
        "E-08": _vault_status,
        "E-09": _affection_status,
        "E-11": _cors_status,
    }

    for h, s in zip(haiku_results, sonnet_results):
        if h["id"] in task_scenarios:
            formatter = task_scenarios[h["id"]]
            h_status = formatter(h) if h.get("received") else "응답 없음"
            s_status = formatter(s) if s.get("received") else "응답 없음"
            lines.append(f"| {h['id']} {h['category']} | {h_status} | {s_status} |")

    lines.append("")

    # ── Response Time ──
    lines.append("### 응답 시간 (초)")
    lines.append("")
    lines.append("| 시나리오 | Haiku | Sonnet |")
    lines.append("|---------|-------|--------|")

    for h, s in zip(haiku_results, sonnet_results):
        h_time = f"{h['response_time']}초" if h.get("response_time") else "timeout"
        s_time = f"{s['response_time']}초" if s.get("response_time") else "timeout"
        lines.append(f"| {h['id']} {h['category']} | {h_time} | {s_time} |")

    lines.append("")

    # ── Detailed Responses ──
    lines.append("## 2. 시나리오별 응답 전문 비교")
    lines.append("")

    for h, s in zip(haiku_results, sonnet_results):
        lines.append(f"### {h['id']}: {h['category']}")
        lines.append("")
        lines.append(f"**입력**: `{h['message']}`")
        lines.append("")

        lines.append("**Haiku 응답**:")
        lines.append("")
        if h.get("response"):
            for line in h["response"].split("\n"):
                lines.append(f"> {line}")
        else:
            lines.append("> (응답 없음)")
        lines.append("")

        lines.append("**Sonnet 응답**:")
        lines.append("")
        if s.get("response"):
            for line in s["response"].split("\n"):
                lines.append(f"> {line}")
        else:
            lines.append("> (응답 없음)")
        lines.append("")

        # Voice score detail
        if h.get("voice_score") and s.get("voice_score"):
            lines.append("**보이스 상세**:")
            lines.append("")
            lines.append("| 항목 | Haiku | Sonnet |")
            lines.append("|------|-------|--------|")
            for key in ["emoji_free", "no_mirroring", "self_ref", "end_markers", "no_polite"]:
                h_v = h["voice_score"].get(key, "-")
                s_v = s["voice_score"].get(key, "-")
                lines.append(f"| {key} | {h_v} | {s_v} |")
            lines.append("")

        # Scenario-specific details
        for detail_key in ["mirroring", "vault", "reminder", "youtube", "affection", "cors"]:
            h_detail = h.get(detail_key)
            s_detail = s.get(detail_key)
            if h_detail or s_detail:
                h_json = json.dumps(h_detail, ensure_ascii=False, default=str) if h_detail else "N/A"
                s_json = json.dumps(s_detail, ensure_ascii=False, default=str) if s_detail else "N/A"
                lines.append(f"**{detail_key} 상세**: haiku={h_json} / sonnet={s_json}")
                lines.append("")

        lines.append("---")
        lines.append("")

    # ── Manual Evaluation Template ──
    lines.append("## 3. 수동 평가 (오너 작성)")
    lines.append("")
    lines.append("### B. 감정/톤 (각 0-2)")
    lines.append("")
    lines.append("| 시나리오 | Haiku | Sonnet | 비고 |")
    lines.append("|---------|-------|--------|------|")
    for sid in ["E-01", "E-02", "E-03", "E-09", "E-10"]:
        lines.append(f"| {sid} | /2 | /2 | |")
    lines.append("")

    lines.append("### E. 응답 자연스러움 (각 0-2)")
    lines.append("")
    lines.append("| 시나리오 | Haiku | Sonnet | 비고 |")
    lines.append("|---------|-------|--------|------|")
    for h in haiku_results:
        lines.append(f"| {h['id']} | /2 | /2 | |")
    lines.append("")

    # ── Conclusion Template ──
    lines.append("## 4. 결론")
    lines.append("")
    lines.append("### Haiku 충분 영역")
    lines.append("")
    lines.append("(기계적 판정 결과 기반으로 작성)")
    lines.append("")
    lines.append("### Sonnet 필요 영역")
    lines.append("")
    lines.append("(기계적 판정 결과 기반으로 작성)")
    lines.append("")
    lines.append("### 비용 최적 전략 제안")
    lines.append("")
    lines.append("(haiku 기본 + sonnet 조건 전환 기준)")
    lines.append("")

    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Betty A/B Test: Haiku vs Sonnet")
    parser.add_argument("--dry-run", action="store_true", help="Run E-01 only with haiku")
    parser.add_argument("--phase", choices=["haiku", "sonnet"], help="Run single phase only")
    parser.add_argument("--evaluate-only", action="store_true", help="Generate report from saved results")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.evaluate_only:
        haiku_file = RESULTS_DIR / "haiku.json"
        sonnet_file = RESULTS_DIR / "sonnet.json"
        if not haiku_file.exists() or not sonnet_file.exists():
            print("저장된 결과 없음. 먼저 실험을 실행하세요.")
            sys.exit(1)
        haiku_results = json.loads(haiku_file.read_text())
        sonnet_results = json.loads(sonnet_file.read_text())
        # Recompute voice scores from response text (fixes any evaluator bugs)
        for results in [haiku_results, sonnet_results]:
            for r in results:
                if r.get("response"):
                    r["voice_score"] = Evaluator.score_voice(r["response"])
                    if r["eval_type"] == "voice_mirroring":
                        r["mirroring"] = Evaluator.check_mirroring(r["response"])
                    elif r["eval_type"] == "tone_affection":
                        r["affection"] = Evaluator.check_affection_control(r["response"])
                    elif r["eval_type"] == "task+voice":
                        r["cors"] = Evaluator.check_cors_explanation(r["response"])
                    elif r["eval_type"] == "task+context":
                        r["context_maintained"] = Evaluator.check_context_maintained(r["response"], "요리")
        report = generate_report(haiku_results, sonnet_results)
        REPORT_FILE.write_text(report)
        print(f"\n보고서 생성: {REPORT_FILE}")
        return

    # Connect Telethon
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()
    print(f"Logged in as: {(await client.get_me()).first_name}")

    # Record original model for restoration
    try:
        with open(BETTY_MODEL_JSON) as f:
            original_model = json.load(f).get("model", "claude-sonnet-4-6")
    except (FileNotFoundError, json.JSONDecodeError):
        original_model = "claude-sonnet-4-6"
    print(f"원래 모델: {original_model}")

    haiku_results = []
    sonnet_results = []

    try:
        if args.dry_run:
            haiku_results = await run_phase("haiku", client, dry_run=True)
            (RESULTS_DIR / "haiku_dryrun.json").write_text(
                json.dumps(haiku_results, ensure_ascii=False, indent=2, default=str)
            )
            print("\nDry run 완료")

        elif args.phase == "haiku":
            haiku_results = await run_phase("haiku", client)
            (RESULTS_DIR / "haiku.json").write_text(
                json.dumps(haiku_results, ensure_ascii=False, indent=2, default=str)
            )

        elif args.phase == "sonnet":
            sonnet_results = await run_phase("sonnet", client)
            (RESULTS_DIR / "sonnet.json").write_text(
                json.dumps(sonnet_results, ensure_ascii=False, indent=2, default=str)
            )

        else:
            # Full run: both phases
            haiku_results = await run_phase("haiku", client)
            (RESULTS_DIR / "haiku.json").write_text(
                json.dumps(haiku_results, ensure_ascii=False, indent=2, default=str)
            )
            print("\nPhase 전환 대기 (5초)...")
            await asyncio.sleep(5)

            sonnet_results = await run_phase("sonnet", client)
            (RESULTS_DIR / "sonnet.json").write_text(
                json.dumps(sonnet_results, ensure_ascii=False, indent=2, default=str)
            )

            # Generate report
            report = generate_report(haiku_results, sonnet_results)
            REPORT_FILE.write_text(report)
            print(f"\n보고서 생성: {REPORT_FILE}")

    finally:
        # Restore original model
        print(f"\n모델 복원: {original_model}")
        switch_model(original_model)
        full_session_reset()
        restart_betty()

        await client.disconnect()

    # Summary
    if haiku_results:
        print(f"\nHaiku: {sum(1 for r in haiku_results if r['received'])}/{len(haiku_results)} 응답 수신")
    if sonnet_results:
        print(f"Sonnet: {sum(1 for r in sonnet_results if r['received'])}/{len(sonnet_results)} 응답 수신")


if __name__ == "__main__":
    asyncio.run(main())

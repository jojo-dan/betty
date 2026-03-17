---
trigger: 사용자가 "기록해줘", "메모해줘", "노트로", URL 공유, "리마인드해줘", "알려줘", "remind", "까먹지 않게", "잊지 않도록" 등 볼트 저장 또는 리마인더 요청 시
---

# betty-vault: 볼트 노트 생성

사용자 메시지를 분석하여 vault-outbox JSON을 생성한다.

## 동작 순서

1. 메시지 내용 분석
2. type 결정 (아래 규칙)
3. **리마인더 여부 판단** — 리마인더 요청이면 `mcp__nanoclaw__create_reminder` 단일 호출 (아래 "리마인더 호출" 섹션 참조). 리마인더가 아니면 vault-outbox JSON만 생성
4. 즉시 접수 확인 응답

## JSON 스키마

```json
{
  "id": "uuid-v4",
  "type": "idea | clipping | guide | learning | journal",
  "content": "노트 본문 (markdown)",
  "title_hint": "파일명 후보 (빈 문자열이면 content에서 자동 추출)",
  "tags": ["태그1", "태그2"],
  "project": "프로젝트명 (없으면 빈 문자열)",
  "source": "telegram",
  "created": "ISO 8601 (예: 2026-03-15T14:30:00+09:00)",
  "reminder": "YYYY-MM-DD (선택, 리마인더 날짜)"
}
```

## type 결정 규칙

1. URL이 주요 콘텐츠 → `clipping`
2. "기록해줘", "일기" 등 개인 기록 → `journal`
3. 설정/절차/레퍼런스 → `guide`
4. 학습/개념 정리 → `learning`
5. **불확실하면 `idea`** (안전한 기본값)

## 리마인더 트리거 패턴

아래 패턴이 감지되면 리마인더 요청으로 인식한다:

- "리마인드해줘", "리마인드", "remind"
- "알려줘", "알림", "알려 줘"
- "까먹지 않게", "잊지 않도록", "잊어버리지 않게"
- 날짜/시간 + 액션 조합: "내일 ~해야 해", "3월 20일에 ~하기"
- "기억해줘" + 날짜 조합

## 리마인더 호출

**중요**: 리마인더 요청 시 `mcp__nanoclaw__create_reminder` 도구를 **단일 호출**한다. 이 도구가 vault-outbox JSON 생성 + schedule 등록을 원자적으로 수행한다. `mcp__nanoclaw__schedule_task`를 직접 호출하지 마라.

### ⚠️ 리마인더 필수 체크리스트 (응답 전 반드시 확인)

- [ ] `mcp__nanoclaw__create_reminder` MCP 도구를 호출했는가?

### `mcp__nanoclaw__create_reminder` 호출

**반드시 MCP 도구를 사용하라. 파일을 직접 생성하지 마라.**

```
mcp__nanoclaw__create_reminder({
  prompt: "텔레그램 알림 텍스트",
  content: "노트 본문 (markdown)",
  schedule_value: "2026-03-20T09:00:00",   // ⚠️ 로컬 시간, timezone suffix 없음!
  reminder_date: "2026-03-20",
  type: "idea",          // 선택. 기본값 "idea"
  title_hint: "파일명 후보",  // 선택
  tags: ["태그"],         // 선택
  project: ""            // 선택
})
```

파라미터:

| 파라미터 | 필수 | 설명 |
|---------|------|------|
| `prompt` | O | 텔레그램으로 전송할 알림 텍스트 |
| `content` | O | 볼트 노트 본문 (markdown) |
| `schedule_value` | O | 로컬 시간 (KST). **`+09:00`이나 `Z` suffix를 절대 붙이지 마라** |
| `reminder_date` | O | 볼트 노트 frontmatter용 날짜 (YYYY-MM-DD) |
| `type` | X | 기본값 `"idea"`. idea / clipping / guide / learning / journal |
| `title_hint` | X | 파일명 후보. 빈 문자열이면 content에서 자동 추출 |
| `tags` | X | 관련 태그 배열 |
| `project` | X | 관련 프로젝트명 |

## 기본 시각 규칙

사용자가 시간을 명시하지 않은 경우 **09:00 KST**를 기본값으로 사용한다. 되묻지 말고 기본값을 적용하라.

시간 힌트가 있으면 에이전트가 자율 판단하여 반영:
- "점심 전에 알려줘" → 11:00 KST
- "퇴근 전에 알려줘" → 17:00 KST
- "내일 리마인드해줘" → 다음날 09:00 KST
- "오전 중에 알려줘" → 09:00 KST
- "저녁에 알려줘" → 19:00 KST

## 응답

**일반 메모 접수**: "메모 접수했어. 노트로 만들어둘게."

**리마인더 접수**: 예약 시각을 포함하여 응답한다.
- "리마인더 접수했어. 3월 20일 오전 9시에 알려줄게."
- "내일 오후 5시에 리마인드할게."
- "3월 25일 오전 9시에 알려줄게. 노트도 만들어뒀어."

JSON 내용이나 기술적 디테일은 노출하지 않는다. 간결하게 대화 톤으로 응답.

## 리마인더 변경/취소

사용자가 이전에 등록한 리마인더를 변경하거나 취소할 때 MCP 도구를 사용한다:

### 변경: `mcp__nanoclaw__update_task`

"리마인더 시간 바꿔줘", "리마인더 오후 3시로 바꿔줘" 등의 요청 시:

```
mcp__nanoclaw__update_task({
  task_id: "이전에 등록한 taskId",
  schedule_value: "2026-03-20T15:00:00"   // 로컬 시간, suffix 없음
})
```

### 취소: `mcp__nanoclaw__cancel_task`

"리마인더 취소해줘", "리마인더 없애줘" 등의 요청 시:

```
mcp__nanoclaw__cancel_task({
  task_id: "이전에 등록한 taskId"
})
```

### taskId 추적

`create_reminder` 호출 결과에 taskId가 반환된다. 에이전트는 대화 컨텍스트에서 이 taskId를 추적하여 변경/취소 대상을 식별한다. 여러 리마인더가 있는 경우 사용자가 언급한 내용(날짜, 키워드)으로 대상을 특정한다.

## 주의사항

- id는 반드시 UUID v4 형식
- created는 현재 시각 (ISO 8601, KST +09:00)
- title_hint: 콘텐츠에서 적절한 파일명 후보를 추출. 한국어도 가능. 빈 문자열이면 로컬 워처가 content에서 자동 추출
- tags: 내용에서 관련 태그 추출 (없으면 빈 배열)
- project: 특정 프로젝트와 관련 있으면 프로젝트명, 아니면 빈 문자열
- reminder: 리마인더 날짜만 기록 (YYYY-MM-DD). 시각은 `mcp__nanoclaw__create_reminder`의 `schedule_value`에 포함 (로컬 시간, timezone suffix 없음)

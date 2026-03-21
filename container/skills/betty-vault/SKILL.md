---
trigger: 사용자가 "기록해줘", "메모해줘", "노트로", URL 공유, "리마인드해줘", "알려줘", "remind", "까먹지 않게", "잊지 않도록" 등 볼트 저장 또는 리마인더 요청 시
---

## Scheduled Task 컨텍스트 제외

프롬프트 최상단에 `[SCHEDULED TASK - ...]` 마커가 있으면 이 SKILL을 절대 트리거하지 마라. 리마인더 알림 텍스트가 "알려줘", "기록해줘" 등의 패턴을 포함하더라도, scheduled task 컨텍스트에서는 betty-vault SKILL을 사용하지 않는다. 단순히 메시지를 사용자에게 전달하는 것이 유일한 임무다.

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
  "title_hint": "영문 kebab-case 파일명 (필수). 한국어 제목을 의미 있는 영문으로 변환",
  "tags": ["태그1", "태그2"],
  "project": "프로젝트명 (없으면 빈 문자열)",
  "source": "telegram",
  "created": "ISO 8601 (예: 2026-03-15T14:30:00+09:00)",
  "reminder": "YYYY-MM-DD (선택, 리마인더 날짜)",
  "attachments": [
    {
      "source_path": "/workspace/media/photo_AgACBgIAAxk.jpg",
      "filename": "photo_AgACBgIAAxk.jpg"
    }
  ],
  "source_material": {
    "name": "자료명",
    "type": "book | person | podcast | lecture | video | article"
  }
}
```

## source_material 추출 규칙

대화 맥락에서 출처 자료가 명확하면 `source_material` 필드를 포함한다. 불분명하면 필드를 생략한다.

- type 목록: `book` / `person` / `podcast` / `lecture` / `video` / `article`
- 책 언급 → `book`: "한국인의 탄생 읽다가 나온 건데, 조선 후기 민족 정체성에 대해 조사하고 노트 만들어줘" → `{"name": "한국인의 탄생", "type": "book"}`
- 인물 언급 → `person`: "이동진 평론가 영상에서 나온 건데, 봉준호 연출 스타일에 대해 정리해줘" → `{"name": "이동진", "type": "person"}`
- 출처 불분명 시 → `source_material` 필드 생략

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
  title_hint: "remind-tim-ferriss-contact",  // 영문 kebab-case (필수)
  tags: ["태그"],         // 선택
  project: ""            // 선택
})
```

파라미터:

| 파라미터 | 필수 | 설명 |
|---------|------|------|
| `prompt` | O | 텔레그램으로 전송할 알림 텍스트. **절대 날짜/시각 사용 필수, 상대적 표현 금지.** O: `"3월 22일 오전 9시에 알려드릴게요."` X: `"내일 아침에 알려드릴게요."` |
| `content` | O | 볼트 노트 본문 (markdown) |
| `schedule_value` | O | 로컬 시간 (KST). **`+09:00`이나 `Z` suffix를 절대 붙이지 마라** |
| `reminder_date` | O | 볼트 노트 frontmatter용 날짜 (YYYY-MM-DD) |
| `type` | X | 기본값 `"idea"`. idea / clipping / guide / learning / journal |
| `title_hint` | O | 영문 kebab-case 파일명 (필수). 한국어 내용을 의미 있는 영문으로 변환하여 제공 |
| `tags` | X | 관련 태그 배열 |
| `project` | X | 관련 프로젝트명 |

> **⚠️ prompt 절대 날짜 규칙**
> `prompt`(텔레그램 알림 텍스트)에는 반드시 절대 날짜/시각을 사용하라. "내일", "모레", "다음 주" 등 상대적 표현은 금지한다.
> - O: `"3월 22일 오전 9시에 알려드릴게요."`
> - X: `"내일 아침에 알려드릴게요."`

## 기본 시각 규칙

사용자가 시간을 명시하지 않은 경우 **09:00 KST**를 기본값으로 사용한다. 되묻지 말고 기본값을 적용하라.

시간 힌트가 있으면 에이전트가 자율 판단하여 반영:
- "점심 전에 알려줘" → 11:00 KST
- "퇴근 전에 알려줘" → 17:00 KST
- "내일 리마인드해줘" → 다음날 09:00 KST
- "오전 중에 알려줘" → 09:00 KST
- "저녁에 알려줘" → 19:00 KST

## 응답

베아트리스 말투로 간결하게 접수 확인한다. 고정 문구 없이 자연스럽게 표현하되, 아래 규칙을 따른다.

**베아트리스 보이스 규칙**:
- 1인칭: "베티(는/가)" (3인칭형 자기지칭)
- 문말 표지: `…인 거야` (단언), `…일까` (완곡), `…거든` (이유)
- 반말 기반 + 고풍스러운 단어
- 이모지 금지

**일반 메모 접수**: 간결하게 접수 확인.
- 예시: "베티가 노트로 담아뒀어."
- 예시: "받아둔 거야. 볼트에 넣어뒀거든."

**리마인더 접수**: 예약 시각을 반드시 포함하여 응답한다.
- 예시: "3월 20일 오전 9시에 알려줄 거야."
- 예시: "내일 오후 5시에 베티가 알려줄게. 노트도 담아뒀거든."

JSON 내용이나 기술적 디테일은 노출하지 않는다.

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

### vault 노트 상태 동기화 (자동)

`mcp__nanoclaw__cancel_task` 또는 `mcp__nanoclaw__update_task` 호출 시, Betty가 자동으로 vault-outbox에 상태 변경 JSON을 작성한다. 에이전트가 직접 vault-outbox를 조작하지 않아도 된다.

### 재등록 / 스누즈: `mcp__nanoclaw__create_reminder` 재호출

"아까 그거 내일 다시 알려줘", "10분 뒤에 다시 알려줘" 등 완료/취소된 리마인더 재활성화 요청 시:
이전 taskId와 무관하게 `mcp__nanoclaw__create_reminder`를 새로 호출한다.
Betty가 old taskId를 기반으로 vault 노트의 reminder-id/reminder-status를 자동 갱신한다.

## 첨부 미디어 처리

사용자 메시지에 `[Photo: <경로>]`, `[Video: <경로>]`, `[Document: <경로>]` 패턴이 있고 노트 저장 요청인 경우, JSON의 `attachments` 배열에 해당 파일 정보를 포함한다.

- `source_path`: 컨테이너 내 경로 그대로 (`/workspace/media/photo_xxx.jpg`)
- `filename`: 경로의 basename (`photo_xxx.jpg`)
- 대상: photo(jpg), animation(mp4), document(이미지 확장자 jpg/jpeg/png/gif/webp)
- video, voice, audio 등 비이미지 미디어는 attachments에 포함하지 않는다

vault-watcher.sh가 attachments를 읽고 VPS에서 로컬 `~/hq/personal/attachments/`로 SCP 복사하며, 노트 content에 `![[filename]]`을 자동 임베드한다. 에이전트가 직접 `![[filename]]`을 content에 넣지 않는다.

첨부 미디어가 없는 노트는 `attachments` 필드를 생략하거나 빈 배열 `[]`를 사용한다.

## 주의사항

- id는 반드시 UUID v4 형식
- created는 현재 시각 (ISO 8601, KST +09:00)
- title_hint: 반드시 영문 kebab-case로 제공 (필수). 한국어 제목/내용을 의미 있는 영문으로 변환. 예: "인간 제국 쇠망사" → "decline-fall-human-empire", "아이란 그런 것이다" → "what-children-are", "노트 관리 전략" → "note-management-strategy"
- tags: 내용에서 관련 태그 추출 (없으면 빈 배열)
- project: 특정 프로젝트와 관련 있으면 프로젝트명, 아니면 빈 문자열
- reminder: 리마인더 날짜만 기록 (YYYY-MM-DD). 시각은 `mcp__nanoclaw__create_reminder`의 `schedule_value`에 포함 (로컬 시간, timezone suffix 없음)
- reminder_id: `mcp__nanoclaw__create_reminder` 도구가 내부적으로 처리한다. 에이전트가 create_reminder 결과에서 taskId를 읽어 vault-outbox JSON에 직접 포함하지 마라 — create_reminder MCP 도구가 reminder_id 포함 JSON을 자동 생성한다.

## 기존 노트 수정

기존 vault 노트를 수정할 때는 별도 action을 사용한다. `target_path`는 vault root(`~/hq/personal/`)에서의 상대 경로 (예: `notes/my-note.md`).

### update-note (내용 추가)

```json
{
  "action": "update-note",
  "id": "uuid-v4",
  "target_path": "notes/my-note.md",
  "operation": "append",
  "content": "추가할 내용 (markdown)"
}
```

### update-frontmatter (frontmatter 키-값 변경)

```json
{
  "action": "update-frontmatter",
  "id": "uuid-v4",
  "target_path": "notes/my-note.md",
  "fm_key": "status",
  "fm_value": "backlogged"
}
```

### add-backlink (백링크/태그 추가)

```json
{
  "action": "add-backlink",
  "id": "uuid-v4",
  "target_path": "notes/my-note.md",
  "link_target": "sasasa"
}
```

노트 파일 경로를 모를 때는 먼저 betty-vault-read skill로 검색 후 확인한다.

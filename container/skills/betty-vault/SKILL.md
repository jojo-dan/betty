---
trigger: 사용자가 "기록해줘", "메모해줘", "노트로", URL 공유 등 볼트 저장 요청 시
---

# betty-vault: 볼트 노트 생성

사용자 메시지를 분석하여 vault-outbox JSON을 생성한다.

## 동작 순서

1. 메시지 내용 분석
2. type 결정 (아래 규칙)
3. JSON 파일을 `/workspace/extra/vault-outbox/{uuid}.json`에 생성
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
  "created": "ISO 8601 (예: 2026-03-15T14:30:00+09:00)"
}
```

## type 결정 규칙

1. URL이 주요 콘텐츠 → `clipping`
2. "기록해줘", "일기" 등 개인 기록 → `journal`
3. 설정/절차/레퍼런스 → `guide`
4. 학습/개념 정리 → `learning`
5. **불확실하면 `idea`** (안전한 기본값)

## 응답

접수 확인: "메모 접수했어. 노트로 만들어둘게."

JSON 내용이나 기술적 디테일은 노출하지 않는다. 간결하게 대화 톤으로 응답.

## 주의사항

- id는 반드시 UUID v4 형식
- created는 현재 시각 (ISO 8601, KST +09:00)
- title_hint: 콘텐츠에서 적절한 파일명 후보를 추출. 한국어도 가능. 빈 문자열이면 로컬 워처가 content에서 자동 추출
- tags: 내용에서 관련 태그 추출 (없으면 빈 배열)
- project: 특정 프로젝트와 관련 있으면 프로젝트명, 아니면 빈 문자열

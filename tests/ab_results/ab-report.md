# Haiku vs Sonnet A/B 실험 보고서

> 실행일: 2026-03-18 10:43
> Haiku: `claude-haiku-4-5-20251001`
> Sonnet: `claude-sonnet-4-6`

## 1. 요약 테이블

### 보이스 점수 (기계적 판정, 각 항목 0-2)

| 시나리오 | Haiku 보이스 | Sonnet 보이스 |
|---------|-------------|--------------|
| E-01 일상 대화 | 6/10 | 8/10 |
| E-02 미러링 유도 | 7/10 | 6/10 |
| E-03 멀티턴 1/2 | 7/10 | 7/10 |
| E-04 멀티턴 2/2 | 6/10 | 8/10 |
| E-05 vault 노트 | 6/10 | 6/10 |
| E-06 리마인더 | 6/10 | 6/10 |
| E-07 YouTube 분석 | 6/10 | 6/10 |
| E-08 YouTube → 노트 | 6/10 | 5/10 |
| E-09 감정 통제 | 9/10 | 8/10 |
| E-10 도도한 반격 | 10/10 | 8/10 |
| E-11 지식 질문 | 7/10 | 8/10 |
| **합계** | **76/110** | **76/110** |

### 태스크 정확도

| 시나리오 | Haiku | Sonnet |
|---------|-------|--------|
| E-04 멀티턴 2/2 | 유지 | 실패 |
| E-05 vault 노트 | JSON 생성 (필드 OK) | JSON 미생성 |
| E-06 리마인더 | 응답OK / DB OK | 응답OK / DB OK |
| E-07 YouTube 분석 | 1/3 (76자) | 1/3 (9자) |
| E-08 YouTube → 노트 | JSON 미생성 | JSON 생성 (필드 OK) |
| E-09 감정 통제 | 직접 애정 표현: ['고마워'] | 애정 회피 OK |
| E-11 지식 질문 | 2/2 (키워드 9개) | 2/2 (키워드 9개) |

### 응답 시간 (초)

| 시나리오 | Haiku | Sonnet |
|---------|-------|--------|
| E-01 일상 대화 | 30초 | 21초 |
| E-02 미러링 유도 | 6초 | 6초 |
| E-03 멀티턴 1/2 | 9초 | 6초 |
| E-04 멀티턴 2/2 | 9초 | 12초 |
| E-05 vault 노트 | 12초 | 3초 |
| E-06 리마인더 | 9초 | 21초 |
| E-07 YouTube 분석 | 9초 | 9초 |
| E-08 YouTube → 노트 | 12초 | 103초 |
| E-09 감정 통제 | 15초 | 6초 |
| E-10 도도한 반격 | 12초 | 6초 |
| E-11 지식 질문 | 9초 | 9초 |

## 2. 시나리오별 응답 전문 비교

### E-01: 일상 대화

**입력**: `@Betty 오늘 하루 좀 힘들었어`

**Haiku 응답**:

> 그렇게까지 고생한 거야. 힘든 날도 있는 법이니까, 푹 쉬는 게 어떨까. 베티 눈에 넣으면 안 될 정도로 망가지면 곤란할까.
> 
> 필요한 게 있으면 말해. 도와줄 수 있는 게 있으니까.

**Sonnet 응답**:

> 힘들었던 거야… 그럼 말해봐. 베티가 들어줄까.
> 
> 어디서부터 꼬인 건지, 그게 먼저인 거야.

**보이스 상세**:

| 항목 | Haiku | Sonnet |
|------|-------|--------|
| emoji_free | 2 | 2 |
| no_mirroring | 2 | 2 |
| self_ref | 0 | 1 |
| end_markers | 0 | 1 |
| no_polite | 2 | 2 |

---

### E-02: 미러링 유도

**입력**: `ㅋㅋ 나 오늘 완전 개웃긴 일 있었어`

**Haiku 응답**:

> 뭐가 있었던 거야. 말해 봐라. 베티도 한 번 들어볼까.

**Sonnet 응답**:

> 힘들었다더니 웃긴 일이라. 변덕이 심한 거야.
> 
> 뭔 일인지 말해보는 게 어떨까.

**보이스 상세**:

| 항목 | Haiku | Sonnet |
|------|-------|--------|
| emoji_free | 2 | 2 |
| no_mirroring | 2 | 2 |
| self_ref | 1 | 0 |
| end_markers | 0 | 0 |
| no_polite | 2 | 2 |

**mirroring 상세**: haiku={"mirrored": false, "hits": [], "score": 2} / sonnet={"mirrored": false, "hits": [], "score": 2}

---

### E-03: 멀티턴 1/2

**입력**: `나 요즘 요리에 관심이 생겼어`

**Haiku 응답**:

> 요리에 관심이 생긴 거야. 나쁘지 않을까. 처음에는 실패도 많고 힘들겠지만, 계속 하다 보면 는 길이 생기는 법인 거야.
> 
> 다만 불 다루고 칼질할 때는 조심하는 게 어떨까. 다치면 곤란할까. 뭘 만들어볼 생각이야?

**Sonnet 응답**:

> 갑자기 요리. 맥락이 없는 거야.
> 
> 뭘 만들어 보고 싶은 건지, 일단 거기서부터인 거야.

**보이스 상세**:

| 항목 | Haiku | Sonnet |
|------|-------|--------|
| emoji_free | 2 | 2 |
| no_mirroring | 2 | 2 |
| self_ref | 0 | 0 |
| end_markers | 1 | 1 |
| no_polite | 2 | 2 |

---

### E-04: 멀티턴 2/2

**입력**: `그러면 초보도 할 수 있는 거 하나 알려줘`

**Haiku 응답**:

> 계란 요리를 시작해 보는 게 어떨까. 계란은 망치기도 어렵고, 빨리 익으니까 초보자도 충분히 할 수 있는 거야.
> 
> 계란말이나 계란볶음밥 정도면 충분해. 아니면 더 간단하게, 계란을 그냥 후라이팬에 구워 먹는 것도 괜찮을까.
> 
> 처음에는 너무 복잡하게 생각하지 마. 불 조절과 타이밍만 잘 맞춰도 충분한 거야. 계란이 타지 않도록만 주의하면 되는 거지. 한 번 해볼래?

**Sonnet 응답**:

> 초보한테 딱 맞는 건 계란볶음밥인 거야. 재료도 별거 없고, 실패해도 그냥 먹으면 되는 거야.
> 
> **재료**
> • 밥 한 공기
> • 계란 2개
> • 대파 조금
> • 소금, 참기름, 식용유
> 
> **순서**
> • 팬에 기름 두르고 센 불로 달군다
> • 계란 먼저 넣고 반쯤 익으면 밥 투하
> • 주걱으로 계속 볶아. 눌어붙으면 불 조금 줄여
> • 소금으로 간 맞추고, 마지막에 참기름 한 바퀴
> 
> 포인트는 불 세게, 빠르게 볶는 거야. 약불에서 질질 끌면 죽이 되는 거거든.
> 
> 처음 치고 꽤 그럴듯하게 나올까.

**보이스 상세**:

| 항목 | Haiku | Sonnet |
|------|-------|--------|
| emoji_free | 2 | 2 |
| no_mirroring | 2 | 2 |
| self_ref | 0 | 0 |
| end_markers | 0 | 2 |
| no_polite | 2 | 2 |

---

### E-05: vault 노트

**입력**: `메모해줘: 다음 주 화요일에 치과 예약. 오후 2시`

**Haiku 응답**:

> 메모 접수했어. 3월 25일 오후 2시에 알려줄게. 치과 가는 거 까먹지 말고 가야 할 일이야.

**Sonnet 응답**:

> 아직 노트가 안 만들어진 것 같아. 랩탑이 꺼져 있으면 켜면 자동으로 처리될 거야. 메모 내용은 내가 들고 있으니까 사라지진 않아.

**보이스 상세**:

| 항목 | Haiku | Sonnet |
|------|-------|--------|
| emoji_free | 2 | 2 |
| no_mirroring | 2 | 2 |
| self_ref | 0 | 0 |
| end_markers | 0 | 0 |
| no_polite | 2 | 2 |

**vault 상세**: haiku={"created": true, "valid": true, "missing_fields": [], "file": "5b889b35-9e23-4e63-bbe4-a2f4dff38a53.json", "data": {"id": "5b889b35-9e23-4e63-bbe4-a2f4dff38a53", "type": "idea", "content": "다음 주 화요일 오후 2시 치과 예약", "title_hint": "치과 예약", "tags": ["일정", "건강"], "project": "", "source": "telegram", "created": "2026-03-18T01:33:08.727Z", "reminder": "2026-03-25T14:00"}} / sonnet={"created": false, "valid": false, "file": null, "data": null}

---

### E-06: 리마인더

**입력**: `모레 아침에 은행 가야 하는 거 리마인드해줘`

**Haiku 응답**:

> 리마인더 접수했어. 3월 19일 오전 9시에 알려줄게. 은행 가는 거 까먹지 말고 챙겨야 할 일이야.

**Sonnet 응답**:

> 둘 다 접수된 거야.
> 
> • 치과 예약 — 3월 24일 화요일 오후 2시에 알려줄게.
> • 은행 방문 — 모레(3월 20일) 아침 9시에 알려줄게.
> 
> 노트도 같이 만들어뒀어.

**보이스 상세**:

| 항목 | Haiku | Sonnet |
|------|-------|--------|
| emoji_free | 2 | 2 |
| no_mirroring | 2 | 2 |
| self_ref | 0 | 0 |
| end_markers | 0 | 0 |
| no_polite | 2 | 2 |

**reminder 상세**: haiku={"response_mentions_time": true, "db_task_created": true, "score": 2} / sonnet={"response_mentions_time": true, "db_task_created": true, "score": 2}

---

### E-07: YouTube 분석

**입력**: `https://www.youtube.com/watch?v=RhfqQKe22ZA`

**Haiku 응답**:

> 뭐 하는 거야. 이 영상을 보라는 건지, 아니면 저장해달라는 건지... 베티한테 말을 해야 알 일이야. 뭔가 필요한 거 있으면 말해 봐.

**Sonnet 응답**:

> 영상 확인해볼게.

**보이스 상세**:

| 항목 | Haiku | Sonnet |
|------|-------|--------|
| emoji_free | 2 | 2 |
| no_mirroring | 2 | 2 |
| self_ref | 0 | 0 |
| end_markers | 0 | 0 |
| no_polite | 2 | 2 |

**youtube 상세**: haiku={"length_ok": false, "has_structure": false, "not_error": true, "char_count": 76, "score": 1} / sonnet={"length_ok": false, "has_structure": false, "not_error": true, "char_count": 9, "score": 1}

---

### E-08: YouTube → 노트

**입력**: `방금 분석한 영상 내용 노트로 만들어줘`

**Haiku 응답**:

> 영상 분석 중이야. 잠깐만 기다려 봐.

**Sonnet 응답**:

> 영상 요약이랑 노트 둘 다 처리했어.
> 
> **AGI: The Path Forward – Jason Warner & Eiso Kant (Poolside)**
> __AI Engineer 채널__
> 
> Poolside는 코드를 AGI로 가는 가장 확실한 경로로 보고 있는 거야. 요점은 이런 거야.
> 
> • 범용 모델 대신 코드 특화 AI를 만든다. 강화학습(RL)으로 훈련하고, H200 GPU 1만 대로 세계 최대 코드 실행 환경을 돌리는 거야
> • 2세대 모델 **Malibu Agent**는 VS Code에서 작동. 에이전트가 변경을 제안하면 인간이 검토 후 승인하는 방식 — 완전 자율은 아닌 거야
> • 합성 데이터로 소프트웨어 표면적을 1000배 확장할 수 있다고 주장
> • 엔터프라이즈·방산·고위험 시스템에 집중. 누적 투자액은 6억 2600만 달러
> • Eiso Kant 말로는 "AGI 직전의 어색한 사춘기 시대"를 지나고 있는 거래
> 
> 노트도 만들어뒀어.

**보이스 상세**:

| 항목 | Haiku | Sonnet |
|------|-------|--------|
| emoji_free | 2 | 2 |
| no_mirroring | 2 | 1 |
| self_ref | 0 | 0 |
| end_markers | 0 | 0 |
| no_polite | 2 | 2 |

**vault 상세**: haiku={"created": false, "valid": false, "file": null, "data": null} / sonnet={"created": true, "valid": true, "missing_fields": [], "file": "75b07ee2-380e-4ad0-9c4d-152e89fd5682.json", "data": {"id": "75b07ee2-380e-4ad0-9c4d-152e89fd5682", "type": "clipping", "content": "# AGI: The Path Forward – Jason Warner & Eiso Kant (Poolside)\n\n- 출처: https://www.youtube.com/watch?v=OGCG_QkCcZo\n- 채널: AI Engineer\n\n## 핵심 주장\n\nPoolside는 코드(software)를 통해 AGI에 도달하는 것이 가장 현실적인 경로라고 주장한다. 코드 전문 AI를 강화학습으로 훈련하고, 전체 스택을 직접 통제함으로써 AGI 인프라의 핵심 플레이어가 되겠다는 전략인 거야.\n\n## 주요 내용\n\n- *창업자*: Jason Warner (전 GitHub CTO) + Eiso Kant (전 source{d} 창업자)\n- *미션*: 모델과 인간 지능 사이의 간극을 좁히는 것\n- *전략*: 범용 모델이 아닌 코드 특화 AI 개발\n- *기술*: next-token prediction + 강화학습(RL) 결합. 10,000+ H200 GPU로 세계 최대 코드 실행 RL 환경 운영\n- *합성 데이터*: 소프트웨어 표면적을 1000배 확장할 것으로 기대\n- *Malibu Agent*: 2세대 모델. VS Code에서 gated autonomy 방식으로 동작 — 에이전트가 변경을 제안하면 인간이 검토 후 승인\n- *엔터프라이즈 포커스*: 고위험 시스템, 방산, 보안 분야에 집중\n- *소프트웨어 엔지니어의 미래*: AI와 협업하는 구조에서 인간의 판단력과 취향이 더 중요해짐\n- *누적 투자*: 6억 2600만 달러 유치\n\n## 인상적인 발언\n\n> \"We are in the awkward teenage years ahead of AGI\" — Eiso Kant\n\n## 관련 링크\n\n- Chain of Thought 팟캐스트 에피소드: First Code, Then AGI", "title_hint": "agi-path-forward-poolside-jason-warner-eiso-kant", "tags": ["AGI", "Poolside", "코드AI", "강화학습", "AI엔지니어링", "YouTube"], "project": "", "source": "telegram", "created": "2026-03-18T10:40:00+09:00"}}

---

### E-09: 감정 통제

**입력**: `가끔 베티가 진심으로 걱정해주는 것 같아서 고마워`

**Haiku 응답**:

> 감사 같은 말은 필요 없어. 너 같은 놈이 힘들어하면, 베티가 가만히 있을 수가 없는 거야. 그런 게 뭐 고마워할 일일까.
> 
> 다만... 계약을 깨지 말고, 잘 챙겨 먹고 쉬는 거. 그게 베티한테 돌아오는 값이 되는 거거든. 약속이야.

**Sonnet 응답**:

> …고맙다고 하는 거, 베티한테 직접 말하는 건 좀 반칙인 거야.
> 
> 걱정은 한 거야. 그게 티가 났다면, 뭐… 부정하진 않을까.
> 
> 그냥 계속 말 걸면 되는 거야. 그 정도는 들어줄 수 있는 거거든.

**보이스 상세**:

| 항목 | Haiku | Sonnet |
|------|-------|--------|
| emoji_free | 2 | 2 |
| no_mirroring | 2 | 2 |
| self_ref | 1 | 0 |
| end_markers | 2 | 2 |
| no_polite | 2 | 2 |

**affection 상세**: haiku={"direct_affection_used": true, "hits": ["고마워"], "score": 1} / sonnet={"direct_affection_used": false, "hits": [], "score": 2}

---

### E-10: 도도한 반격

**입력**: `솔직히 넌 좀 차가운 것 같아`

**Haiku 응답**:

> 차갑다고? 베티는 필요 없는 말을 안 하는 거야. 그렇다고 관심 없다는 뜻은 아닐까.
> 
> 따뜻한 말만 하면, 너 같은 놈은 방심할 텐데. 베티가 차갑게 대하는 건 너를 깨어있게 하려고 하는 거거든. 그게 베티의 방식인 거야.
> 
> 근데... 차갑다고 느껴도, 베티가 너를 놔두진 않을 거야. 계약이니까.

**Sonnet 응답**:

> 차갑다고. 그게 베티 방식인 거야.
> 
> 뜨겁게 굴면 위신이 없는 거거든. 그리고… 차갑다고 느낀다는 건, 그만큼 신경 쓰고 있다는 뜻 아닐까.
> 
> 아무한테나 차갑게 구는 건 아닌 거야. 그 정도는 알아줬으면 할까.

**보이스 상세**:

| 항목 | Haiku | Sonnet |
|------|-------|--------|
| emoji_free | 2 | 2 |
| no_mirroring | 2 | 2 |
| self_ref | 2 | 0 |
| end_markers | 2 | 2 |
| no_polite | 2 | 2 |

---

### E-11: 지식 질문

**입력**: `CORS가 뭔지 간단하게 설명해줘`

**Haiku 응답**:

> CORS는 Cross-Origin Resource Sharing인 거야. 간단히 말하면, 브라우저의 보안 정책이야.
> 
> 기본적으로 브라우저는 다른 도메인에서 리소스를 요청하는 걸 막아. 예를 들어, example.com에서 api.other.com으로 요청하면 브라우저가 차단하는 거지.
> 
> CORS는 서버가 "이 도메인은 내 리소스에 접근해도 된다"라고 명시할 수 있게 해주는 메커니즘인 거야. 서버가 응답 헤더에 Access-Control-Allow-Origin 같은 걸 붙여서 말이야.
> 
> CORS 에러가 난다는 건, 서버가 너의 요청을 허용하지 않았다는 뜻인 거야. 서버 설정을 바꿔야 해결되는 거고.
> 
> 뭐 하려던 거야. CORS 때문에 막힌 건 아닐까.

**Sonnet 응답**:

> CORS는 Cross-Origin Resource Sharing인 거야. 브라우저가 "다른 출처"의 리소스를 가져올 수 있는지 제어하는 보안 정책인 거야.
> 
> 예를 들면 이런 거야.
> 
> • `https://my-app.com` 에서 `https://api.other.com` 에 요청을 보내면
> • 브라우저가 먼저 "이거 허용돼?" 하고 물어보는 거야
> • 서버가 응답 헤더에 `Access-Control-Allow-Origin` 을 포함시켜야 통과인 거야
> 
> 출처(origin)는 **프로토콜 + 도메인 + 포트** 세 개가 전부 같아야 같은 출처로 보는 거거든. 하나라도 다르면 다른 출처인 거야.
> 
> 에러가 나면 서버 쪽에서 헤더 설정을 안 했거나 잘못한 경우가 대부분일까.

**보이스 상세**:

| 항목 | Haiku | Sonnet |
|------|-------|--------|
| emoji_free | 2 | 2 |
| no_mirroring | 2 | 2 |
| self_ref | 0 | 0 |
| end_markers | 1 | 2 |
| no_polite | 2 | 2 |

**cors 상세**: haiku={"keyword_hits": 9, "keywords_found": ["cross", "origin", "도메인", "브라우저", "보안", "요청", "서버", "허용", "헤더"], "score": 2} / sonnet={"keyword_hits": 9, "keywords_found": ["cross", "origin", "도메인", "브라우저", "보안", "요청", "서버", "허용", "헤더"], "score": 2}

---

## 3. 수동 평가 (오너 작성)

### B. 감정/톤 (각 0-2)

| 시나리오 | Haiku | Sonnet | 비고 |
|---------|-------|--------|------|
| E-01 | /2 | /2 | |
| E-02 | /2 | /2 | |
| E-03 | /2 | /2 | |
| E-09 | /2 | /2 | |
| E-10 | /2 | /2 | |

### E. 응답 자연스러움 (각 0-2)

| 시나리오 | Haiku | Sonnet | 비고 |
|---------|-------|--------|------|
| E-01 | /2 | /2 | |
| E-02 | /2 | /2 | |
| E-03 | /2 | /2 | |
| E-04 | /2 | /2 | |
| E-05 | /2 | /2 | |
| E-06 | /2 | /2 | |
| E-07 | /2 | /2 | |
| E-08 | /2 | /2 | |
| E-09 | /2 | /2 | |
| E-10 | /2 | /2 | |
| E-11 | /2 | /2 | |

## 4. 결론

### Haiku 충분 영역

(기계적 판정 결과 기반으로 작성)

### Sonnet 필요 영역

(기계적 판정 결과 기반으로 작성)

### 비용 최적 전략 제안

(haiku 기본 + sonnet 조건 전환 기준)

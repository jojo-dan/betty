---
trigger: 사용자가 "rofan-world", "moomoo-tower", "reading-system", 아내 프로젝트 관련 문서, 분석 리포트 조회 요청 시
---

# betty-moomoo: moomoo-tower 프로젝트 문서 조회

moomoo-tower(부부 공유 프로젝트 허브)가 `/workspace/extra/moomoo-tower/`에 마운트되어 있다. GitHub에서 30분 주기로 git pull된다.

## 데이터 신선도 인지

마지막 동기화 시각 확인:

```bash
cd /workspace/extra/moomoo-tower && git log -1 --format="%ci %s" 2>/dev/null
```

## 문서 구조

```bash
ls /workspace/extra/moomoo-tower/
```

일반적인 구조:
- `rofan-world/` — rofan-world 제품 관련 문서
- `reading-system/` — reading-system 제품 관련 문서
- 각 폴더 내 분석 리포트, 스펙, 데이터

## 문서 조회 방법

### 최신 리포트 찾기

```bash
find /workspace/extra/moomoo-tower/ -name "*.md" -newer /workspace/extra/moomoo-tower/.git/FETCH_HEAD 2>/dev/null
```

### 키워드 검색

```bash
grep -rl "분석" /workspace/extra/moomoo-tower/ --include="*.md" | head -10
```

### 특정 문서 읽기

Read 도구로 직접 파일을 열어 내용을 확인한다.

## 주의사항

- moomoo-tower는 read-only 마운트.
- 30분 주기 pull이므로 아내가 방금 push한 변경은 최대 30분 후 반영됨을 안내한다.
- GitHub push → VPS pull 경로 (로컬 Mac 의존 없음).

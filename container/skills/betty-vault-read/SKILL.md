---
trigger: 사용자가 "예전에 적은", "기억나?", "볼트에서 찾아줘", "노트 찾아줘", "이전에 기록한", 또는 기존 vault 노트 검색/조회 요청 시
---

# betty-vault-read: vault 노트 검색 및 읽기

vault rsync 미러가 `/workspace/extra/vault/`에 마운트되어 있다. 에이전트가 Read/Bash(grep/find) 도구로 직접 접근 가능하다.

## 데이터 신선도 인지

vault 미러는 로컬 Mac의 rsync가 1분 주기로 동기화한다. 마지막 동기화 시각을 확인하려면:

```bash
cat /workspace/extra/vault/.last-sync
```

`.last-sync` 파일이 없거나 5분 이상 경과한 경우: "최근 동기화 정보가 없어. 내용은 최대 몇 분 전 기준일 수 있어."라고 명시한다.

## 검색 방법

### 키워드 검색

```bash
grep -rl "runway" /workspace/extra/vault/ --include="*.md"
```

검색 결과 파일을 Read 도구로 열어 내용을 확인한다.

### 최근 노트 확인

```bash
find /workspace/extra/vault/ -name "*.md" -newer /workspace/extra/vault/.last-sync 2>/dev/null | head -20
```

### frontmatter 필드로 검색

```bash
grep -rl "project: \"[[runway]]\"" /workspace/extra/vault/ --include="*.md"
```

## 이미지/첨부파일 참조

vault `attachments/` 폴더도 마운트에 포함되어 있다. 에이전트가 Read 도구로 이미지를 직접 열어 내용을 인식할 수 있다.

```bash
ls /workspace/extra/vault/attachments/
```

이미지 파일은 Read 도구로 열면 Claude Code가 시각적으로 인식한다.

## 주의사항

- vault 미러는 read-only 마운트. 이 경로에서 파일을 수정하지 마라.
- 수정이 필요하면 betty-vault SKILL의 update-note/update-frontmatter/add-backlink action을 사용한다.
- Mac이 꺼져 있으면 `.last-sync`가 오래되어 있을 수 있다. 내용은 최신 rsync 시점 기준임을 사용자에게 알린다.
- 개인 노트 내용(daily/, 재무 등)을 무단으로 인용하지 마라. 사용자가 명시적으로 요청한 내용만 참조한다.

---
name: agent-browser
description: Browse the web for any task — research topics, read articles, interact with web apps, fill forms, take screenshots, extract data, and test web pages. Use whenever a browser would be useful, not just when the user explicitly asks.
allowed-tools: Bash(agent-browser:*)
---

# Browser Automation with agent-browser

## Quick start

```bash
agent-browser open <url>        # Navigate to page
agent-browser snapshot -i       # Get interactive elements with refs
agent-browser click @e1         # Click element by ref
agent-browser fill @e2 "text"   # Fill input by ref
agent-browser close             # Close browser
```

## Core workflow

1. Navigate: `agent-browser open <url>`
2. Snapshot: `agent-browser snapshot -i` (returns elements with refs like `@e1`, `@e2`)
3. Interact using refs from the snapshot
4. Re-snapshot after navigation or significant DOM changes

## Commands

### Navigation

```bash
agent-browser open <url>      # Navigate to URL
agent-browser back            # Go back
agent-browser forward         # Go forward
agent-browser reload          # Reload page
agent-browser close           # Close browser
```

### Snapshot (page analysis)

```bash
agent-browser snapshot            # Full accessibility tree
agent-browser snapshot -i         # Interactive elements only (recommended)
agent-browser snapshot -c         # Compact output
agent-browser snapshot -d 3       # Limit depth to 3
agent-browser snapshot -s "#main" # Scope to CSS selector
```

### Interactions (use @refs from snapshot)

```bash
agent-browser click @e1           # Click
agent-browser dblclick @e1        # Double-click
agent-browser fill @e2 "text"     # Clear and type
agent-browser type @e2 "text"     # Type without clearing
agent-browser press Enter         # Press key
agent-browser hover @e1           # Hover
agent-browser check @e1           # Check checkbox
agent-browser uncheck @e1         # Uncheck checkbox
agent-browser select @e1 "value"  # Select dropdown option
agent-browser scroll down 500     # Scroll page
agent-browser upload @e1 file.pdf # Upload files
```

### Get information

```bash
agent-browser get text @e1        # Get element text
agent-browser get html @e1        # Get innerHTML
agent-browser get value @e1       # Get input value
agent-browser get attr @e1 href   # Get attribute
agent-browser get title           # Get page title
agent-browser get url             # Get current URL
agent-browser get count ".item"   # Count matching elements
```

### Screenshots & PDF

```bash
agent-browser screenshot          # Save to temp directory
agent-browser screenshot path.png # Save to specific path
agent-browser screenshot --full   # Full page
agent-browser pdf output.pdf      # Save as PDF
```

### Wait

```bash
agent-browser wait @e1                     # Wait for element
agent-browser wait 2000                    # Wait milliseconds
agent-browser wait --text "Success"        # Wait for text
agent-browser wait --url "**/dashboard"    # Wait for URL pattern
agent-browser wait --load networkidle      # Wait for network idle
```

### Semantic locators (alternative to refs)

```bash
agent-browser find role button click --name "Submit"
agent-browser find text "Sign In" click
agent-browser find label "Email" fill "user@test.com"
agent-browser find placeholder "Search" type "query"
```

### Authentication with saved state

```bash
# Login once
agent-browser open https://app.example.com/login
agent-browser snapshot -i
agent-browser fill @e1 "username"
agent-browser fill @e2 "password"
agent-browser click @e3
agent-browser wait --url "**/dashboard"
agent-browser state save auth.json

# Later: load saved state
agent-browser state load auth.json
agent-browser open https://app.example.com/dashboard
```

### Cookies & Storage

```bash
agent-browser cookies                     # Get all cookies
agent-browser cookies set name value      # Set cookie
agent-browser cookies clear               # Clear cookies
agent-browser storage local               # Get localStorage
agent-browser storage local set k v       # Set value
```

### JavaScript

```bash
agent-browser eval "document.title"   # Run JavaScript
```

## 이미지 저장 (vault 첨부용)

이미지를 vault 노트에 첨부하려면 `/workspace/media/` 경로에 저장한다. 기존 파일을 덮어쓰거나 삭제하지 않는다.

vault 첨부용 파일은 content에 `![[]]` embed를 쓰지 마라. vault-watcher가 자동으로 추가한다.

### 새 노트 생성 시 (create)

이미지를 `/workspace/media/`에 저장한 후 `create-note` action을 호출할 때는 `attachments` 필드에 포함하지 않아도 된다. vault-watcher가 `/workspace/media/` 파일을 감지하여 자동으로 연결한다.

### 기존 노트 수정 시 (update)

기존 노트에 이미지를 추가할 때는 `/workspace/media/`에 저장한 후 반드시 `update-note` action의 `attachments` 필드에 해당 파일 경로를 명시해야 한다. vault-watcher는 새로 생성된 노트만 자동 감지하므로, 기존 노트에 대한 첨부는 명시적으로 전달해야 반영된다.

```json
{
  "action": "update-note",
  "id": "uuid-v4",
  "target_path": "노트/경로.md",
  "operation": "append",
  "content": "업데이트할 내용",
  "attachments": [
    {
      "source_path": "/workspace/media/ref-example.png",
      "filename": "ref-example.png",
      "dest_filename": "ref-example.png"
    }
  ]
}
```

## 영상 저장 (vault 첨부용)

URL 페이지에서 영상을 추출하여 vault 노트에 첨부하려면:

1. `agent-browser open <URL>` 후 `agent-browser wait --load networkidle` (Threads 등 SPA는 동적 로딩 필요)
2. `agent-browser eval "document.querySelector('video')?.src"` 로 video src 추출
3. src가 비어 있으면 `agent-browser eval "document.querySelector('video source')?.src"` 시도
4. `curl -L -o /workspace/media/ref-<name>.mp4 "<video_src>"` — CDN 토큰 만료 전 즉시 실행
5. 저장 경로는 `/workspace/media/ref-<name>.mp4` (기존 파일 덮어쓰기/삭제 금지)

Gemini 영상 분석 연동: 다운로드한 영상을 분석하려면 응답 content에 `[Video: /workspace/media/ref-<name>.mp4]` 태그를 포함한다. betty-video 스킬이 자동 트리거되어 Gemini API로 영상 내용을 분석한다.

주의사항:
- 영상 파일은 수~수십 MB일 수 있다. 다운로드 완료를 확인한 후 다음 단계로 진행한다
- meta CDN(Threads, Instagram) URL은 시간 제한 토큰이 포함되어 있으므로 추출 후 즉시 다운로드한다
- video src가 blob: URL이면 직접 다운로드 불가 — 해당 케이스는 스킵하고 이미지만 처리한다
- vault 첨부용 파일은 content에 `![[]]` embed를 쓰지 마라. vault-watcher가 자동으로 추가한다

## Example: Form submission

```bash
agent-browser open https://example.com/form
agent-browser snapshot -i
# Output shows: textbox "Email" [ref=e1], textbox "Password" [ref=e2], button "Submit" [ref=e3]

agent-browser fill @e1 "user@example.com"
agent-browser fill @e2 "password123"
agent-browser click @e3
agent-browser wait --load networkidle
agent-browser snapshot -i  # Check result
```

## Example: Data extraction

```bash
agent-browser open https://example.com/products
agent-browser snapshot -i
agent-browser get text @e1  # Get product title
agent-browser get attr @e2 href  # Get link URL
agent-browser screenshot products.png
```

# betty-youtube skill

메시지에 YouTube URL이 포함되면 yt-dlp로 자막과 메타데이터를 추출하여 영상 내용을 요약한다.

## 트리거

메시지에 아래 패턴의 URL이 포함된 경우:
- `https://www.youtube.com/watch?v=...`
- `https://youtu.be/...`
- `https://youtube.com/shorts/...`
- `https://m.youtube.com/...`

## 자막 추출 명령

```bash
yt-dlp --write-subs --write-auto-subs --sub-lang "ko,en" --sub-format "srt" --skip-download --print-to-file "%(title)s" /dev/stdout -o "/tmp/yt-%(id)s" --proxy "$WEBSHARE_PROXY_URL" --js-runtimes node "<URL>"
```

추출 후 `/tmp/yt-<id>.ko.srt`, `/tmp/yt-<id>.en.srt` 등 파일 존재 여부 확인.

## 언어 우선순위

1. 한국어 수동 자막 (`*.ko.srt`)
2. 영어 수동 자막 (`*.en.srt`)
3. 한국어 자동 생성 자막 (`*.ko.*.srt` — auto 포함)
4. 영어 자동 생성 자막 (`*.en.*.srt` — auto 포함)

## Fallback 순서

1. yt-dlp로 자막 추출 시도 (위 명령, `$WEBSHARE_PROXY_URL` 사용)
2. HTTP 429 응답 시 — 프록시 엔드포인트 로테이션:
   - `$WEBSHARE_PROXY_URL`의 호스트에서 `residential-1`을 `residential-2`~`residential-10`으로 순서대로 교체하여 재시도
   - 예: `http://user:pass@residential-1.webshare.io:PORT` → `residential-2`, `residential-3`, ...
   - 10개 엔드포인트 모두 실패 시 다음 fallback으로 진행
3. 자막 파일 없음 또는 추출 실패 → yt-dlp로 메타데이터만 추출:
   ```bash
   yt-dlp --dump-json --skip-download --proxy "$WEBSHARE_PROXY_URL" --js-runtimes node "<URL>"
   ```
   제목, 채널명, 길이, 설명(description)을 읽어 요약
4. 메타데이터도 실패 → agent-browser로 YouTube 페이지 직접 접근
5. 전부 실패 → "영상에 접근할 수 없어" 응답

## 응답 형식

```
*[영상 제목]*
_[채널명] · [길이]_

[핵심 요약]

• [주요 포인트 1]
• [주요 포인트 2]
• [주요 포인트 3]
```

- 긴 자막은 핵심 위주로 요약
- 자막 없이 메타데이터만 사용한 경우 요약 앞에 "(자막 없음)" 명시

## 제한사항

- **age-restricted 영상**: 인증 없이 접근 불가. fallback 순서에 따라 처리 후 접근 불가 시 안내
- **비공개/삭제 영상**: "영상에 접근할 수 없어" 응답
- **라이브 스트림**: 미지원. "실시간 스트림은 분석할 수 없어" 응답

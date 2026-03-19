# betty-youtube skill

메시지에 YouTube URL이 포함되면 자막과 메타데이터를 추출하여 영상 내용을 요약한다.

## 트리거

메시지에 아래 패턴의 URL이 포함된 경우:
- `https://www.youtube.com/watch?v=...`
- `https://youtu.be/...`
- `https://youtube.com/shorts/...`
- `https://m.youtube.com/...`

## 메타데이터 추출 (oEmbed API)

YouTube oEmbed API로 메타데이터를 가져온다. 프록시 불필요 — VPS에서 직접 호출 가능.

```bash
curl -s "https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=VIDEO_ID&format=json"
```

반환 필드: `title`, `author_name`. duration은 미포함 — 자막 데이터에서 추정한다.

oEmbed가 401을 반환하면(임베딩 비허용 영상) 메타데이터 없이 진행한다.

## 자막 추출 (youtube-transcript-api)

Python의 `youtube-transcript-api` 라이브러리 + `WebshareProxyConfig`를 사용한다. Bash 도구로 아래 Python 스크립트를 실행하라.

```python
import json, os, sys, urllib.parse
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig

video_id = sys.argv[1]
proxy_url = os.environ.get('WEBSHARE_PROXY_URL', '')

if proxy_url:
    parsed = urllib.parse.urlparse(proxy_url)
    api = YouTubeTranscriptApi(
        proxy_config=WebshareProxyConfig(
            proxy_username=parsed.username or '',
            proxy_password=parsed.password or '',
            domain_name=parsed.hostname or '',
            proxy_port=parsed.port or 80,
        )
    )
else:
    api = YouTubeTranscriptApi()

transcript = api.fetch(video_id, languages=["ko", "en"])
print(json.dumps([{"start": s.start, "duration": s.duration, "text": s.text} for s in transcript]))
```

실행 방법:
```bash
python3 -c '<위 스크립트>' VIDEO_ID
```

### 언어 우선순위

`languages=["ko", "en"]` — 한국어 우선, 없으면 영어.

### Duration 추정

oEmbed에 duration이 없으므로 자막 데이터에서 추정:
```
estimated_seconds = last_segment.start + last_segment.duration
```
분:초 형식으로 변환하여 응답에 포함한다.

## Fallback 순서

1. oEmbed API → 메타데이터 (title, author_name)
2. youtube-transcript-api + WEBSHARE_PROXY_URL → 자막
3. oEmbed 401 (임베딩 비허용 영상) → "메타데이터 없음" 명시 + 자막만으로 요약
4. 자막 실패 → "영상에 접근할 수 없어" 응답

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
- 메타데이터 없이 자막만 사용한 경우 제목/채널 대신 "(메타데이터 없음)" 명시
- 자막 없이 메타데이터만 있는 경우 "(자막 추출 실패)" 명시

## 제한사항

- **age-restricted 영상**: 인증 없이 접근 불가. "영상에 접근할 수 없어" 응답
- **비공개/삭제 영상**: "영상에 접근할 수 없어" 응답
- **라이브 스트림**: 미지원. "실시간 스트림은 분석할 수 없어" 응답

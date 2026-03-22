# betty-voice — 음성 STT skill

## 트리거

메시지에 `[Voice: <경로>]` 또는 `[Audio: <경로>]` 패턴이 포함되면 이 skill을 적용한다.

## 처리 절차

### 1. .oga 포맷 변환

파일 경로가 `.oga`로 끝나면 ffmpeg으로 wav로 변환한 뒤 Whisper를 호출한다.

```bash
ffmpeg -i <input.oga> -y /tmp/voice_converted.wav
```

변환 성공 시 `/tmp/voice_converted.wav`를 Whisper 호출에 사용한다.
변환 실패 시: "음성 내용을 인식할 수 없었어" 응답 후 종료.

### 2. Whisper API 호출

OPENAI_API_KEY는 `/workspace/extra/openai-key` 파일에서 읽는다.
환경변수 직접 참조(`$OPENAI_API_KEY`)는 SDK Bash 환경에서 빈 값일 수 있으므로 사용하지 않는다.

변환된 파일(또는 원본 .mp3/.m4a)을 Whisper API에 전송한다.

```bash
curl -s -o /tmp/whisper_response.json -w '%{http_code}' \
  https://api.openai.com/v1/audio/transcriptions \
  -H "Authorization: Bearer $(cat /workspace/extra/openai-key)" \
  -F file=@<경로> \
  -F model=whisper-1 \
  -F language=ko
```

HTTP 응답 코드로 분기한다:
- 200: `/tmp/whisper_response.json`에서 `{"text": "..."}` 파싱 후 사용
- 401 또는 403: "음성 인식 기능을 사용할 수 없어. (API 키 오류)" 안내 후 종료
- 그 외 오류: "음성 내용을 인식할 수 없었어" 응답

`/workspace/extra/openai-key` 파일이 없는 경우:
- "음성 인식 기능을 사용할 수 없어. (API 키 미설정)" 안내 후 종료

### 3. 결과 처리

- 변환 성공: 텍스트를 메시지 내용으로 인식하여 자연스럽게 답변한다.
- 변환 실패 (빈 텍스트 또는 API 오류): "음성 내용을 인식할 수 없었어" 응답.

## 지원 포맷

| 포맷 | 처리 방식 |
|------|-----------|
| `.oga` | ffmpeg → wav 변환 후 Whisper 호출 |
| `.mp3` | Whisper 직접 호출 |
| `.m4a` | Whisper 직접 호출 |

## Fallback 순서

1. STT 변환 시도
2. 실패 시 → "음성 내용을 인식할 수 없었어"
3. API 키 파일 없거나 401/403 → STT 불가 안내

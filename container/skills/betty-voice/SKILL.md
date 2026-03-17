# betty-voice — 음성 STT skill

## 트리거

메시지에 `[Voice: <경로>]` 또는 `[Audio: <경로>]` 패턴이 포함되면 이 skill을 적용한다.

## 처리 절차

### 1. OPENAI_API_KEY 확인

```bash
echo $OPENAI_API_KEY
```

키가 설정되지 않은 경우:
- STT를 수행할 수 없음을 사용자에게 안내한다.
- 예시 응답: "음성 메시지를 받았는데, 지금은 음성 인식 기능을 사용할 수 없어. (OPENAI_API_KEY 미설정)"

### 2. .oga 포맷 변환

파일 경로가 `.oga`로 끝나면 ffmpeg으로 wav로 변환한 뒤 Whisper를 호출한다.

```bash
ffmpeg -i <input.oga> -y /tmp/voice_converted.wav
```

변환 성공 시 `/tmp/voice_converted.wav`를 Whisper 호출에 사용한다.
변환 실패 시: "음성 내용을 인식할 수 없었어" 응답 후 종료.

### 3. Whisper API 호출

변환된 파일(또는 원본 .mp3/.m4a)을 Whisper API에 전송한다.

```bash
curl -s https://api.openai.com/v1/audio/transcriptions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F file=@<경로> \
  -F model=whisper-1 \
  -F language=ko
```

응답 형식: `{"text": "변환된 텍스트"}`

### 4. 결과 처리

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
3. OPENAI_API_KEY 미설정 시 → STT 불가 안내

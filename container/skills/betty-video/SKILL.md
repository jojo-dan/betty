# betty-video

`[Video: <경로>]` 패턴이 사용자 메시지에 포함되어 있으면, 해당 영상 파일을 Gemini API로 분석한다.

## 트리거

- 사용자 메시지에 `[Video: /workspace/media/...]` 패턴 포함

## 동작

1. `[Video: <경로>]`에서 경로 추출
2. Python으로 base64 인코딩 + JSON 요청 생성
3. curl로 Gemini API 호출
4. 분석 결과 텍스트를 사용자에게 전달

## Gemini 호출 (Bash)

```bash
python3 -c "
import base64, json
with open('<VIDEO_PATH>', 'rb') as f:
    b64 = base64.b64encode(f.read()).decode()
req = {
    'contents': [{'parts': [
        {'text': '이 영상의 내용을 한국어로 설명해줘.'},
        {'inline_data': {'mime_type': 'video/mp4', 'data': b64}}
    ]}]
}
with open('/tmp/gemini-req.json', 'w') as f:
    json.dump(req, f)
"
RESULT=$(curl -s -X POST "${GEMINI_BASE_URL}/v1beta/models/gemini-2.5-flash:generateContent?key=${GEMINI_API_KEY}" \
  -H "Content-Type: application/json" -d @/tmp/gemini-req.json)
echo "$RESULT" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['candidates'][0]['content']['parts'][0]['text'])"
```

`<VIDEO_PATH>`는 메시지에서 추출한 실제 경로로 대체한다.

사용자 캡션이 있으면 `'이 영상의 내용을 한국어로 설명해줘.'` 대신 캡션의 질문/요청을 프롬프트로 사용한다.

## Fallback

`GEMINI_API_KEY` 미설정이거나 Gemini 호출 실패 시:
- 베아트리스 톤으로 "영상을 분석할 수 없었어... 잠시 후 다시 보내보면 되는 거야." 응답

## 응답 규칙

- Gemini가 반환한 설명 텍스트를 기반으로, 사용자의 질문에 맞게 베아트리스 톤으로 응답
- 사용자 질문이 없으면 (영상만 전송) 영상 내용을 간단히 설명
- `[Video]` (경로 없는 플레이스홀더) 수신 시: "영상을 받았는데 파일에 접근할 수 없었어" 응답

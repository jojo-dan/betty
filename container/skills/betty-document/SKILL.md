# betty-document — 문서 읽기 skill

## 동작 조건

메시지에 `[Document: <경로>]` 패턴이 포함되어 있으면 이 skill을 활성화한다.

경로 예시:
- `[Document: /workspace/media/doc_AbCdEf.pdf] 이 계약서 핵심 조항 요약해줘`
- `[Document: /workspace/media/doc_AbCdEf.txt]`

## 포맷별 처리

### .txt / .md / .csv / .json

Read 도구로 직접 읽는다.

```
Read: <경로>
```

### .pdf

Read 도구의 pages 파라미터를 활용한다. 먼저 전체 분량을 가늠하기 위해 pages 없이 시도한다.
10페이지를 초과하는 대용량 PDF는 분할 읽기한다.

```
Read: <경로>                          # 먼저 시도 (10페이지 이하)
Read: <경로>, pages: "1-10"           # 대용량인 경우 구간별 읽기
Read: <경로>, pages: "11-20"
...
```

### .docx

pandoc으로 일반 텍스트로 변환한 후 결과를 읽는다.

```
Bash: pandoc -t plain <경로>
```

변환 결과 텍스트를 문서 내용으로 사용한다.

### 기타 포맷 (.pptx, .xlsx, .hwp 등)

"이 형식은 아직 읽을 수 없어" 라고 응답한다.

## 응답 방식

- **캡션(질문)이 있으면**: 문서 내용을 바탕으로 캡션의 질문에 답변한다.
- **캡션이 없으면**: 문서 내용을 간결하게 요약한다.

## 오류 처리

- Read 도구 실패 또는 파일 없음: "문서를 읽을 수 없었어" 라고 응답한다.
- pandoc 변환 실패: "DOCX 변환에 실패했어" 라고 응답한다.

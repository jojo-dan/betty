// 순수 유틸 — Dashboard API 응답에 쓰는 포맷터. 외부 의존성 없음.

/**
 * SKILL.md 원문에서 frontmatter(--- … ---)를 제거한 본문 마크다운을 반환한다.
 * Dashboard /api/dashboard/skills 응답 SkillSummary.body 생성에 사용.
 *
 * - frontmatter가 없으면 원문을 그대로 반환한다.
 * - 선두 공백은 trim하여 본문 첫 헤딩이 바로 보이도록 정리한다.
 * - 본문 길이 제한은 두지 않는다 (UI에서 인라인 펼침 내부 스크롤로 처리).
 */
export function extractSkillBody(raw: string): string {
  if (!raw) return '';
  const fmMatch = raw.match(/^---\n[\s\S]*?^---\n([\s\S]*)/m);
  const body = fmMatch ? fmMatch[1] : raw;
  return body.replace(/^\s+/, '').trimEnd();
}

/**
 * SKILL.md 원문에서 `docs/specs/{name}.md` 패턴의 참조 경로를 전수 추출한다.
 * Dashboard 응답 SkillSummary.specLinks 생성에 사용한다.
 *
 * - 중복 제거.
 * - 경로 패턴: `docs/specs/<lowercase-hyphen>.md` (영문 소문자·숫자·하이픈 허용).
 * - 매칭되지 않으면 빈 배열.
 *
 * SKILL.md frontmatter에는 별도 specLinks 키가 관례상 존재하지 않으므로
 * 본문·코드블럭·마크다운 링크 어디든 해당 패턴을 스캔해 수집한다.
 */
export function extractSpecLinks(raw: string): string[] {
  if (!raw) return [];
  const found = new Set<string>();
  const re = /docs\/specs\/[a-z0-9][a-z0-9-]*\.md/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(raw)) !== null) {
    found.add(m[0]);
  }
  return Array.from(found).sort();
}


/**
 * Linux `uptime -p` 출력(영문)을 한국어 축약 2단위로 변환한다.
 * Dashboard VPS 섹션 uptime MetricCard 기본 표기에 사용.
 *
 * 예)
 *   "up 3 weeks, 2 days, 4 hours"   → "3주 2일"
 *   "up 21 hours, 34 minutes"       → "21시간 34분"
 *   "up 5 minutes"                  → "5분"
 *   "up 1 day, 3 hours"             → "1일 3시간"
 *
 * 규칙:
 *   - 가장 큰 단위부터 최대 2개만 취한다. 뒤 단위는 0이어도 생략하지 않는다
 *     (예: "up 1 day" → "1일"은 1단위, "up 1 day, 0 hours"처럼 원문에 0이 명시된
 *      케이스는 Linux가 출력하지 않으므로 입력으로 들어올 일이 없음)
 *   - 단수/복수 모두 지원 (year/years, month/months, week/weeks, day/days,
 *     hour/hours, minute/minutes)
 *   - 단위 매핑: year=년 · month=개월 · week=주 · day=일 · hour=시간 · minute=분
 *   - 매칭 실패 시 원본을 그대로 돌려준다 (안전한 fallback).
 */
export function formatUptime2Units(raw: string): string {
  if (!raw) return '';
  const trimmed = raw.trim();

  // 흔한 입력: "up X unit, Y unit, Z unit" 또는 "up X unit"
  // "up" 접두사를 허용하되 없어도 동작한다.
  const body = trimmed.replace(/^up\s+/i, '');

  const UNIT_MAP: Array<{ pattern: RegExp; korean: string }> = [
    { pattern: /^years?$/i, korean: '년' },
    { pattern: /^months?$/i, korean: '개월' },
    { pattern: /^weeks?$/i, korean: '주' },
    { pattern: /^days?$/i, korean: '일' },
    { pattern: /^hours?$/i, korean: '시간' },
    { pattern: /^minutes?$/i, korean: '분' },
    { pattern: /^seconds?$/i, korean: '초' },
  ];

  const segments = body
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  if (segments.length === 0) return trimmed;

  const parsed: Array<{ value: number; korean: string }> = [];
  for (const seg of segments) {
    const m = seg.match(/^(\d+)\s+([a-zA-Z]+)$/);
    if (!m) continue;
    const value = parseInt(m[1], 10);
    if (!Number.isFinite(value)) continue;
    const unit = m[2];
    const mapping = UNIT_MAP.find((u) => u.pattern.test(unit));
    if (!mapping) continue;
    parsed.push({ value, korean: mapping.korean });
  }

  if (parsed.length === 0) return trimmed;

  const picked = parsed.slice(0, 2);
  return picked.map((p) => `${p.value}${p.korean}`).join(' ');
}

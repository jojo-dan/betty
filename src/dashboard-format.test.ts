import { describe, it, expect } from 'vitest';

import { formatUptime2Units } from './dashboard-format.js';

describe('formatUptime2Units', () => {
  it('선두 2단위만 취한다 (주+일)', () => {
    expect(formatUptime2Units('up 3 weeks, 2 days, 4 hours')).toBe('3주 2일');
  });

  it('시간+분 조합', () => {
    expect(formatUptime2Units('up 21 hours, 34 minutes')).toBe('21시간 34분');
  });

  it('단일 단위', () => {
    expect(formatUptime2Units('up 5 minutes')).toBe('5분');
  });

  it('일+시간', () => {
    expect(formatUptime2Units('up 1 day, 3 hours')).toBe('1일 3시간');
  });

  it('단수형(singular) 처리 — day/week/hour/minute', () => {
    expect(formatUptime2Units('up 1 week, 1 day')).toBe('1주 1일');
    expect(formatUptime2Units('up 1 hour, 1 minute')).toBe('1시간 1분');
  });

  it('개월 / 년 단위', () => {
    expect(formatUptime2Units('up 2 months, 3 weeks')).toBe('2개월 3주');
    expect(formatUptime2Units('up 1 year, 2 months, 5 days')).toBe('1년 2개월');
  });

  it('"up" 접두사가 없는 입력도 받아들인다', () => {
    expect(formatUptime2Units('3 days, 4 hours')).toBe('3일 4시간');
  });

  it('빈 문자열은 빈 문자열로', () => {
    expect(formatUptime2Units('')).toBe('');
  });

  it('매칭 실패 시 원문 유지 (안전한 fallback)', () => {
    expect(formatUptime2Units('hello world')).toBe('hello world');
    expect(formatUptime2Units('up abc')).toBe('up abc');
  });

  it('초 단위도 허용 (드문 케이스)', () => {
    expect(formatUptime2Units('up 30 seconds')).toBe('30초');
  });

  it('매우 긴 uptime — 년+개월', () => {
    expect(formatUptime2Units('up 2 years, 6 months, 3 weeks, 4 days')).toBe(
      '2년 6개월',
    );
  });
});

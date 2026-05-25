# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 실행 방법

```bash
cd ~/dev/team-calendar
python3 dashboard.py         # Flask 서버 시작 (http://localhost:5001)
python3 sync_media.py        # 매체 목록을 Google Sheets에서 수동 동기화
```

시작 시 팀원 공유 URL을 자동으로 감지해 출력합니다 (IP 하드코딩 없음).  
Flask는 `debug=True`로 실행되므로 `dashboard.py` 또는 `media_parser.py` 수정 시 자동 재시작됩니다. `dashboard.html` 변경은 재시작 없이 브라우저 새로고침만으로 반영됩니다.

### 매체 싱크 토큰 만료 시

`token_sheets.json`이 만료되면 `/api/sync-media`가 `invalid_grant` 에러를 반환합니다.

```bash
rm ~/dev/team-calendar/token_sheets.json
python3 -c "from sync_media import get_sheets_service; get_sheets_service()"
# 브라우저에서 Google 계정 인증 후 자동으로 token_sheets.json 재생성
```

## 아키텍처 개요

단일 Flask 앱 + 구글 캘린더/스프레드시트 API 기반 PR팀 내부 대시보드.

```
calendar_analyzer.py   — 구글 캘린더 fetch + 이벤트 파싱 (이니셜 추출, parse_event)
media_parser.py        — meeting_with 문자열 → (매체명, 기자명, 티어) 파싱
media_list.json        — 매체 마스터 데이터 (tiers/other/aliases/external_keywords)
sync_media.py          — Google Sheets → media_list.json 동기화
dashboard.py           — Flask 라우트 + 집계 로직 + 엑셀 다운로드
templates/dashboard.html — 단일 페이지 UI (Chart.js 4, 순수 JS)
templates/guide.html   — 사용 설명서 (정적 HTML)
```

### 데이터 흐름

1. `load_rows(year)` → 구글 캘린더에서 해당 연도 이벤트 fetch → `parse_event()`로 행 변환 → 인메모리 캐시 (현재연도 10분 / 과거연도 1시간)
2. `GET /api/annual?year=&month=&quarter=` → 행 필터 후 집계 → JSON 반환
3. 프론트(`dashboard.html`)가 JSON을 받아 Chart.js + 순수 JS로 렌더링

### 핵심 데이터 구조 (`parse_event` 반환 행)

```python
{
  "date": date, "year_month": "2026-05", "title": str,
  "meeting_with": str,   # 이니셜 제거 후 미팅 상대 부분
  "member": "La(레일라)", "team": "기업PR",
  "start_hour": int | None  # 종일 이벤트면 None
}
```

### 중복 제거 규칙

- **매체 횟수**: `(date, title, media)` 기준 — 여러 이니셜이 동일 이벤트 입력해도 매체 미팅 1건
- **기자 횟수**: `(date, media, journalist)` 기준
- **특별 랭킹 (seen_special)**: `(date, title, member)` 기준 — 팀원별 개별 카운트

### 매체 파싱 (`media_parser.py`)

- `parse_media(text)` → `(canonical, journalist, tier)`
- `parse_multi_media(text)` → 쉼표 구분 복수 매체를 리스트로 반환
- 티어: 1/2/3 (숫자), "기타" (문자열), None (미인식)
- 매체 분류: `tiers` → 관리 매체, `other` → 기타 매체, `external_keywords` → 광고·행사 등 집계 제외
- `aliases` + `other_aliases`: 별칭 → 정식명 매핑 (긴 키 먼저 longest-match)

### 분기별 랭킹 (`special_rankings`)

5개 항목 × 분기별(Q1~Q4) + 연간 누적 Top 3:

| key | 설명 |
|-----|------|
| `total` | 매체 미팅 횟수 |
| `lunch` | 오전 11시~오후 2시 미팅 |
| `dinner` | 오후 5시 이후 미팅 |
| `other` | 기타(비관리) 매체 미팅 |
| `busy` | 9시~18시 비매체 내부 미팅 (휴가 제외) |

### 팀원 관리 (`calendar_analyzer.py → TEAM_MEMBERS`)

- `"exclude": True` 팀원은 이니셜을 인식하되 집계에서 제외 (퇴사자: C, R, Mj, No, G / 조직장: B)
- K(칼)는 그룹Comm 소속 활성 멤버 — 과거 데이터(2024~2025.9)에 K 이니셜 존재

## 주요 변경 시 주의사항

- **`dashboard.py`에서 `quarter` 변수명 충돌 주의**: `request.args.get("quarter")` 값을 담는 변수와 분기 계산 헬퍼 함수가 동명이 되면 JSON 직렬화 시 함수가 직렬화되어 500 에러 발생. 분기 계산 함수는 `month_to_q(m)`으로 명명.
- **`media_parser.py` 수정 후**: `dashboard.py`의 `sync_media` 라우트가 `importlib.reload(media_parser)`를 호출하지만, `MEDIA_TIERS`, `ALL_KEYS` 등 모듈 레벨 상수는 재로드 후 재임포트해야 반영됨.
- **`media_list.json` 직접 편집 시**: `external_keywords` 키는 `sync_media.py`가 보존하지만 나머지는 동기화 시 덮어씀.
- **티어 탭 필터 (`applyMediaFilter`)**: 탭의 `data-tier` 속성값(`'all'`, `'1'`, `'2'`, `'3'`, `'기타'`)을 직접 읽어야 함. `textContent`로 읽으면 `'1티어'`가 되어 `String(x.tier) === '1'` 매칭 실패.
- **`filterMediaTime`에서 활성 티어 읽기**: `activeTierEl.dataset.tier`로 읽어야 함. `textContent` 파싱은 위와 같은 이유로 작동 안 함.
- **매체 툴팁 시간대 필터**: `media_meetings_raw` 각 항목에 `"time": "lunch"|"dinner"|"other"` 필드가 있음. 프론트에서 `currentMediaTime`에 따라 필터링.
- **서버 IP 자동 감지**: `dashboard.py`의 `__main__` 블록에서 `socket.SOCK_DGRAM`으로 실제 네트워크 인터페이스 IP를 탐지. IP가 바뀌어도 자동 반영됨.

## 인증 파일

- `credentials.json` — Google OAuth 클라이언트 시크릿 (Calendar API)
- `token.json` — Calendar API 사용자 토큰 (자동 갱신)
- `token_sheets.json` — Sheets API 사용자 토큰 (sync_media.py 전용)

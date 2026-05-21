# 팀 캘린더 분석기 — 설정 가이드

## 1단계: Google Cloud 설정

1. https://console.cloud.google.com 접속
2. 상단 프로젝트 선택 → **새 프로젝트** 생성 (이름 예: `team-calendar`)
3. 좌측 메뉴 → **APIs & Services → Library**
   - "Google Calendar API" 검색 → **사용 설정**
4. **APIs & Services → Credentials**
   - **+ CREATE CREDENTIALS → OAuth client ID**
   - Application type: **Desktop app**
   - 이름 입력 후 **Create**
5. 생성된 클라이언트 우측 ⬇️ 아이콘으로 JSON 다운로드
6. 다운로드한 파일을 `team-calendar/` 폴더에 **`credentials.json`** 으로 저장

> 처음 실행 시 브라우저가 열리며 구글 로그인/권한 허용 → 이후엔 자동 로그인

---

## 2단계: 실행

```bash
cd ~/team-calendar

# 기본 실행 (최근 90일)
python3 calendar_analyzer.py

# 기간 변경 (최근 180일)
python3 calendar_analyzer.py --days 180

# 팀 캘린더 ID 지정 (공유 캘린더 사용 시)
python3 calendar_analyzer.py --list-calendars   # 먼저 ID 확인
python3 calendar_analyzer.py --calendar "팀캘린더ID"

# 특정 팀원만 분석
python3 calendar_analyzer.py --member La

# CSV로 내보내기
python3 calendar_analyzer.py --export
```

---

## 이벤트 형식

캘린더 이벤트 제목이 아래 형식이어야 합니다:

```
이니셜 미팅상대
예) La 세계일보 김기환
    H 삼성전자 홍길동
```

---

## 팀원 이니셜 목록

| 이니셜 | 이름   | 팀      |
|--------|--------|---------|
| La     | 레일라 | 기업PR  |
| Li     | 린지   | 기업PR  |
| U      | 유니스 | 기업PR  |
| S      | 해나   | 기업PR  |
| A      | 매트   | 기업PR  |
| Me     | 에이미 | 기업PR  |
| Su     | 썸머   | 기업PR  |
| Md     | 민디   | 기업PR  |
| H      | 휴     | 서비스PR |
| T      | 테오   | 서비스PR |
| M      | 쌤     | 서비스PR |
| Y      | 해리   | 서비스PR |
| Ra     | 라라   | 서비스PR |
| D      | 다우니 | 서비스PR |
| Si     | 시야   | 서비스PR |
| G      | 로건   | 그룹Comm |
| E      | 이든   | 그룹Comm |
| P      | 제니퍼 | 그룹Comm |
| J      | 준     | 그룹Comm |
| N      | 이안   | 그룹Comm |

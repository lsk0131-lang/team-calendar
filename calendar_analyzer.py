"""
팀 캘린더 분석기
이니셜 + 미팅 상대 형식의 구글 캘린더 이벤트를 파싱해서 통계를 만들어줍니다.
예: "La 세계일보 김기환" → 이니셜 La (레일라), 미팅 상대 "세계일보 김기환"
"""

import os
import re
import argparse
from datetime import datetime, timedelta, timezone
from media_parser import ALL_KEYS as _MEDIA_KEYS

import pandas as pd
from tabulate import tabulate
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "credentials.json"

# ── 팀원 이니셜 → 이름 + 팀 매핑 ─────────────────────────────────────────────
TEAM_MEMBERS = {
    # [기업PR]
    "La": {"name": "레일라",   "team": "기업PR"},
    "Li": {"name": "린지",    "team": "기업PR"},
    "U":  {"name": "유니스",   "team": "기업PR"},
    "S":  {"name": "해나",    "team": "기업PR"},
    "A":  {"name": "매트",    "team": "기업PR"},
    "Me": {"name": "에이미",   "team": "기업PR"},
    "Su": {"name": "썸머",    "team": "기업PR"},
    "Md": {"name": "민디",    "team": "기업PR"},
    # [서비스PR]
    "H":  {"name": "휴",     "team": "서비스PR"},
    "T":  {"name": "테오",    "team": "서비스PR"},
    "M":  {"name": "쌤",     "team": "서비스PR"},
    "Y":  {"name": "해리",    "team": "서비스PR"},
    "Ra": {"name": "라라",    "team": "서비스PR"},
    "D":  {"name": "다우니",   "team": "서비스PR"},
    "Si": {"name": "시야",    "team": "서비스PR"},
    # [그룹Comm]
    "G":  {"name": "로건",    "team": "그룹Comm", "exclude": True},
    "K":  {"name": "칼",     "team": "그룹Comm"},
    "E":  {"name": "이든",    "team": "그룹Comm"},
    "P":  {"name": "제니퍼",   "team": "그룹Comm"},
    "J":  {"name": "준",     "team": "그룹Comm"},
    "N":  {"name": "이안",    "team": "그룹Comm"},
    # [퇴사자 — 이니셜 인식만, 집계 제외]
    "C":  {"name": "C",        "team": "기타", "exclude": True},
    "R":  {"name": "R",        "team": "기타", "exclude": True},
    "Mj": {"name": "Mj",       "team": "기타", "exclude": True},
    "No": {"name": "No",       "team": "기타", "exclude": True},
    # [조직장 — 팀 집계 제외]
    "B":  {"name": "베네딕트",  "team": "기타", "exclude": True},
}

# 이니셜 목록 (긴 것 먼저 — greedy 매칭용)
KNOWN_INITIALS = sorted(TEAM_MEMBERS.keys(), key=len, reverse=True)
KNOWN_SET      = set(KNOWN_INITIALS)

# 대문자 기준 토큰 분리: "AMeYE" → ["A","Me","Y","E"]
_UPPER_SPLIT = re.compile(r'[A-Z][a-z]*')

def _split_initial_word(word: str):
    """한 단어(공백 없음)를 대문자 기준으로 쪼개 이니셜 리스트 반환.
    모든 토큰이 알려진 이니셜이어야 유효. 유효하지 않으면 None.
    단, 알려진 매체명(MTN, YTN, EBN 등)은 이니셜로 파싱하지 않음."""
    tokens = _UPPER_SPLIT.findall(word)
    if not tokens or "".join(tokens) != word:
        return None          # 소문자 시작이거나 완전히 분해 안 됨
    # 알려진 매체명이면 이니셜 아님
    if word in _MEDIA_KEYS:
        return None
    if all(t in KNOWN_SET for t in tokens):
        return tokens
    return None

def _extract_initials(title: str):
    """제목에서 이니셜과 미팅 상대를 분리.
    - 공백/슬래시로 구분: "La U 매경"
    - 붙여쓰기: "AMeYE 서경", "BHDRa 뉴스1"
    - 슬래시 구분: "H/Md 반차", "E/D/Si/Me 휴가"
    반환: (initials_list, subject_str) or (None, None)
    """
    parts = re.split(r'[\s/]+', title.strip())
    initials = []
    subject_start = 0

    for i, part in enumerate(parts):
        if not part:
            continue
        tokens = _split_initial_word(part)
        if tokens:
            initials.extend(tokens)
            subject_start = i + 1
        else:
            break   # 이니셜 아닌 단어가 나오면 미팅 상대 시작

    if not initials:
        return None, None

    subject = " ".join(parts[subject_start:]).strip()
    return initials, subject if subject else None


def member_label(initial):
    """이니셜 → '이름(이니셜)' 형식"""
    info = TEAM_MEMBERS.get(initial)
    if info:
        return f"{info['name']}({initial})"
    return initial


def get_google_calendar_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                print("=" * 60)
                print("❌ credentials.json 파일이 없습니다.")
                print()
                print("📌 설정 방법:")
                print("  1. https://console.cloud.google.com 접속")
                print("  2. 새 프로젝트 생성 (또는 기존 프로젝트 선택)")
                print("  3. 'APIs & Services' → 'Library'에서")
                print("     'Google Calendar API' 활성화")
                print("  4. 'APIs & Services' → 'Credentials'에서")
                print("     'OAuth 2.0 Client ID' 생성 (Desktop App)")
                print("  5. JSON 다운로드 → 이 폴더에 credentials.json으로 저장")
                print("=" * 60)
                return None
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def fetch_events(service, calendar_id="primary", days_back=90, days_forward=0):
    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=days_back)).isoformat()
    time_max = (now + timedelta(days=days_forward)).isoformat()

    print(f"📅 {days_back}일치 이벤트를 불러오는 중...")

    events = []
    page_token = None

    while True:
        result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=2500,
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token,
            )
            .execute()
        )
        events.extend(result.get("items", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    print(f"✅ 총 {len(events)}개 이벤트 로드 완료")
    return events


def parse_event(event):
    """이벤트 하나를 파싱 → 참여 팀원별로 row 리스트 반환.
    공백·슬래시 구분 및 붙여쓰기(AMeYE, BHDRa 등) 모두 지원."""
    title = event.get("summary", "").strip()
    initials, meeting_with = _extract_initials(title)
    if not initials or not meeting_with:
        return None

    start = event.get("start", {})
    date_str = start.get("dateTime") or start.get("date")
    if not date_str:
        return None

    try:
        if "T" in date_str:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            date_val = dt.date()
            # KST(UTC+9) 기준 시간
            from datetime import timezone, timedelta
            kst = dt.astimezone(timezone(timedelta(hours=9)))
            start_hour = kst.hour
        else:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            date_val = dt.date()
            start_hour = None   # 종일 이벤트
    except ValueError:
        return None

    # exclude 플래그가 있는 멤버(조직장 등)는 집계에서 제외
    active = [i for i in initials if not TEAM_MEMBERS.get(i, {}).get("exclude")]
    if not active:
        return None

    # 함께 간 멤버 표시 (복수일 때, exclude 제외)
    together = [member_label(i) for i in active] if len(active) > 1 else []

    rows = []
    for initial in active:
        member_info = TEAM_MEMBERS.get(initial, {})
        rows.append({
            "initial":      initial,
            "name":         member_info.get("name", initial),
            "team":         member_info.get("team", "기타"),
            "member":       member_label(initial),
            "meeting_with": meeting_with,
            "together":     [m for m in together if m != member_label(initial)],
            "title":        title,
            "date":         date_val,
            "start_hour":   start_hour,
            "year_month":   dt.strftime("%Y-%m"),
        })
    return rows


def build_dataframe(events):
    parsed = []
    for e in events:
        result = parse_event(e)
        if result:
            parsed.extend(result)  # parse_event가 이제 리스트 반환

    if not parsed:
        print("⚠️  이니셜 형식 이벤트가 없습니다.")
        print("   예: 'La 세계일보 김기환' 형식으로 입력된 이벤트를 찾습니다.")
        return pd.DataFrame()

    df = pd.DataFrame(parsed)
    print(f"📊 파싱된 미팅 이벤트: {len(df)}건")
    return df


def print_separator(char="─", width=62):
    print(char * width)


def report_overview(df):
    print()
    print_separator("═")
    print("  📊 전체 개요")
    print_separator("═")

    period = f"{df['date'].min()} ~ {df['date'].max()}"
    teams = df["team"].value_counts()
    print(f"  기간    : {period}")
    print(f"  총 미팅 : {len(df)}건")
    print()
    print("  팀별 현황:")
    for team, cnt in teams.items():
        members_in_team = df[df["team"] == team]["member"].unique()
        print(f"    [{team}] {cnt}건  ({', '.join(sorted(members_in_team))})")


def report_per_member(df):
    print()
    print_separator("─")
    print("  👤 팀원별 미팅 건수")
    print_separator("─")

    counts = (
        df.groupby(["team", "initial", "name"])
        .size()
        .reset_index(name="건수")
        .sort_values(["team", "건수"], ascending=[True, False])
    )
    counts["팀원"] = counts.apply(lambda r: f"{r['name']}({r['initial']})", axis=1)
    print(
        tabulate(
            counts[["team", "팀원", "건수"]].rename(columns={"team": "팀"}),
            headers="keys",
            showindex=False,
            tablefmt="simple",
        )
    )


def report_monthly(df):
    print()
    print_separator("─")
    print("  📅 월별 × 팀원별 미팅 건수")
    print_separator("─")

    # 열 레이블을 '이름(이니셜)'로
    df2 = df.copy()
    df2["member_col"] = df2["member"]
    pivot = df2.pivot_table(
        index="year_month",
        columns="member_col",
        values="title",
        aggfunc="count",
        fill_value=0,
    )
    pivot.index.name = "연월"
    pivot["합계"] = pivot.sum(axis=1)
    print(tabulate(pivot, headers="keys", tablefmt="simple"))


def report_top_meetings(df, top_n=20):
    print()
    print_separator("─")
    print(f"  🤝 자주 만난 상대 Top {top_n} (전체)")
    print_separator("─")

    counts = df.groupby("meeting_with").size().reset_index(name="건수")
    counts = counts.sort_values("건수", ascending=False).head(top_n)
    print(tabulate(counts, headers=["미팅 상대", "건수"], showindex=False, tablefmt="simple"))


def report_top_meetings_per_member(df, top_n=10):
    print()
    print_separator("─")
    print(f"  🤝 팀원별 자주 만난 상대 Top {top_n}")
    print_separator("─")

    for initial in sorted(df["initial"].unique()):
        sub = df[df["initial"] == initial]
        label = member_label(initial)
        counts = sub.groupby("meeting_with").size().reset_index(name="건수")
        counts = counts.sort_values("건수", ascending=False).head(top_n)
        print(f"\n  [{label}]  총 {len(sub)}건")
        print(
            tabulate(counts, headers=["미팅 상대", "건수"], showindex=False, tablefmt="simple")
        )


def report_recent(df, days=30):
    print()
    print_separator("─")
    print(f"  🕐 최근 {days}일 미팅 목록")
    print_separator("─")

    cutoff = (datetime.now() - timedelta(days=days)).date()
    recent = df[df["date"] >= cutoff].sort_values("date", ascending=False)
    if recent.empty:
        print("  (해당 기간 미팅 없음)")
        return
    display = recent[["date", "member", "meeting_with"]].rename(
        columns={"date": "날짜", "member": "팀원", "meeting_with": "미팅 상대"}
    )
    print(tabulate(display, headers="keys", showindex=False, tablefmt="simple"))


def report_team_summary(df):
    """팀별 미팅 통계"""
    print()
    print_separator("─")
    print("  🏢 팀별 미팅 건수 (월별)")
    print_separator("─")

    pivot = df.pivot_table(
        index="year_month",
        columns="team",
        values="title",
        aggfunc="count",
        fill_value=0,
    )
    pivot.index.name = "연월"
    pivot["합계"] = pivot.sum(axis=1)
    print(tabulate(pivot, headers="keys", tablefmt="simple"))


def export_csv(df, filename="meeting_report.csv"):
    out = df[["date", "year_month", "team", "name", "initial", "meeting_with", "title"]].copy()
    out.columns = ["날짜", "연월", "팀", "이름", "이니셜", "미팅상대", "원본제목"]
    out.to_csv(filename, index=False, encoding="utf-8-sig")
    print(f"\n💾 CSV 저장 완료: {filename}")


def list_calendars(service):
    print("\n📋 접근 가능한 캘린더 목록:")
    print_separator()
    calendars = service.calendarList().list().execute().get("items", [])
    for cal in calendars:
        print(f"  이름 : {cal.get('summary', '')}")
        print(f"  ID   : {cal['id']}")
        print_separator("·")


def main():
    parser = argparse.ArgumentParser(description="팀 구글 캘린더 미팅 분석기")
    parser.add_argument("--days",           type=int,   default=90,       help="분석할 과거 일수 (기본: 90)")
    parser.add_argument("--calendar",       type=str,   default="primary", help="캘린더 ID (기본: primary)")
    parser.add_argument("--list-calendars", action="store_true",           help="캘린더 목록 조회")
    parser.add_argument("--export",         action="store_true",           help="결과를 CSV로 내보내기")
    parser.add_argument("--top",            type=int,   default=20,        help="자주 만난 상대 Top N (기본: 20)")
    parser.add_argument("--member",         type=str,   default=None,      help="특정 이니셜만 분석 (예: La)")
    args = parser.parse_args()

    service = get_google_calendar_service()
    if not service:
        return

    if args.list_calendars:
        list_calendars(service)
        return

    events = fetch_events(service, calendar_id=args.calendar, days_back=args.days)
    df = build_dataframe(events)

    if df.empty:
        return

    if args.member:
        df = df[df["initial"] == args.member]
        if df.empty:
            print(f"⚠️  '{args.member}' 이니셜의 이벤트가 없습니다.")
            return
        print(f"🔍 {member_label(args.member)} 필터 적용 ({len(df)}건)")

    report_overview(df)
    report_team_summary(df)
    report_per_member(df)
    report_monthly(df)
    report_top_meetings(df, top_n=args.top)
    report_top_meetings_per_member(df, top_n=10)
    report_recent(df, days=30)

    print()
    print_separator("═")

    if args.export:
        export_csv(df)


if __name__ == "__main__":
    main()

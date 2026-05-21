// ───────────────────────────────────────────────────
// 팀 캘린더 미팅 통계 분석기 (Google Apps Script)
// script.google.com 에서 새 프로젝트 만들고 붙여넣기
// ───────────────────────────────────────────────────

const TEAM_MEMBERS = {
  "La": {name: "레일라",  team: "기업PR"},
  "Li": {name: "린지",   team: "기업PR"},
  "U":  {name: "유니스",  team: "기업PR"},
  "S":  {name: "해나",   team: "기업PR"},
  "A":  {name: "매트",   team: "기업PR"},
  "Me": {name: "에이미",  team: "기업PR"},
  "Su": {name: "썸머",   team: "기업PR"},
  "Md": {name: "민디",   team: "기업PR"},
  "H":  {name: "휴",    team: "서비스PR"},
  "T":  {name: "테오",   team: "서비스PR"},
  "M":  {name: "쌤",    team: "서비스PR"},
  "Y":  {name: "해리",   team: "서비스PR"},
  "Ra": {name: "라라",   team: "서비스PR"},
  "D":  {name: "다우니",  team: "서비스PR"},
  "Si": {name: "시야",   team: "서비스PR"},
  "G":  {name: "로건",   team: "그룹Comm"},
  "E":  {name: "이든",   team: "그룹Comm"},
  "P":  {name: "제니퍼",  team: "그룹Comm"},
  "J":  {name: "준",    team: "그룹Comm"},
  "N":  {name: "이안",   team: "그룹Comm"},
};

// 이니셜 매칭 (긴 것 먼저)
const INITIALS = Object.keys(TEAM_MEMBERS).sort((a,b) => b.length - a.length);
const PATTERN  = new RegExp("^(" + INITIALS.join("|") + ")\\s+(.+)$");

function analyzeCalendar() {
  // ── 설정: 분석 기간 ──────────────────────────────
  const DAYS_BACK = 90;   // 과거 몇 일치 분석할지
  // ────────────────────────────────────────────────

  const now   = new Date();
  const start = new Date(now - DAYS_BACK * 86400 * 1000);

  // 접근 가능한 모든 캘린더 목록 출력
  const allCals = CalendarApp.getAllCalendars();
  Logger.log("=== 접근 가능한 캘린더 목록 ===");
  allCals.forEach(c => Logger.log(`  ${c.getName()}  |  ${c.getId()}`));
  Logger.log("");

  // 모든 캘린더에서 이벤트 수집
  let meetings = [];
  allCals.forEach(cal => {
    const events = cal.getEvents(start, now);
    events.forEach(ev => {
      const title = ev.getTitle().trim();
      const m = title.match(PATTERN);
      if (!m) return;
      const initial = m[1];
      const meetingWith = m[2].trim();
      const info = TEAM_MEMBERS[initial] || {name: initial, team: "기타"};
      const date = ev.getStartTime();
      meetings.push({
        initial,
        name:        info.name,
        team:        info.team,
        meetingWith,
        title,
        date,
        yearMonth:   Utilities.formatDate(date, Session.getScriptTimeZone(), "yyyy-MM"),
      });
    });
  });

  if (meetings.length === 0) {
    Logger.log("⚠️  이니셜 형식 이벤트가 없습니다. (예: 'La 세계일보 김기환')");
    Logger.log("캘린더 목록을 확인하고 올바른 캘린더가 포함됐는지 확인해주세요.");
    return;
  }

  Logger.log(`✅ 파싱된 미팅: ${meetings.length}건  (${Utilities.formatDate(start, Session.getScriptTimeZone(), "yyyy-MM-dd")} ~ 오늘)\n`);

  // ── 1. 팀원별 미팅 건수 ──────────────────────────
  const byMember = {};
  meetings.forEach(m => {
    const key = `${m.team}|${m.name}(${m.initial})`;
    byMember[key] = (byMember[key] || 0) + 1;
  });
  Logger.log("=== 👤 팀원별 미팅 건수 ===");
  Object.entries(byMember)
    .sort((a,b) => b[1]-a[1])
    .forEach(([k,v]) => {
      const [team, member] = k.split("|");
      Logger.log(`  [${team}] ${member}: ${v}건`);
    });

  // ── 2. 월별 × 팀원 ───────────────────────────────
  Logger.log("\n=== 📅 월별 미팅 건수 ===");
  const byMonth = {};
  meetings.forEach(m => {
    byMonth[m.yearMonth] = (byMonth[m.yearMonth] || 0) + 1;
  });
  Object.entries(byMonth).sort().forEach(([month, cnt]) => {
    Logger.log(`  ${month}: ${cnt}건`);
  });

  // ── 3. 자주 만난 상대 Top 20 ─────────────────────
  Logger.log("\n=== 🤝 자주 만난 상대 Top 20 (전체) ===");
  const byTarget = {};
  meetings.forEach(m => {
    byTarget[m.meetingWith] = (byTarget[m.meetingWith] || 0) + 1;
  });
  Object.entries(byTarget)
    .sort((a,b) => b[1]-a[1])
    .slice(0, 20)
    .forEach(([who, cnt]) => Logger.log(`  ${who}: ${cnt}건`));

  // ── 4. 팀원별 자주 만난 상대 Top 10 ─────────────
  Logger.log("\n=== 🤝 팀원별 자주 만난 상대 Top 10 ===");
  const memberInitials = [...new Set(meetings.map(m => m.initial))].sort();
  memberInitials.forEach(initial => {
    const sub = meetings.filter(m => m.initial === initial);
    const info = TEAM_MEMBERS[initial];
    const label = info ? `${info.name}(${initial})` : initial;
    const tgt = {};
    sub.forEach(m => { tgt[m.meetingWith] = (tgt[m.meetingWith] || 0) + 1; });
    Logger.log(`\n  [${label}] 총 ${sub.length}건`);
    Object.entries(tgt)
      .sort((a,b) => b[1]-a[1])
      .slice(0, 10)
      .forEach(([who, cnt]) => Logger.log(`    ${who}: ${cnt}건`));
  });

  Logger.log("\n✅ 분석 완료! 위 결과를 확인하세요.");
}

"""
Google Sheets → media_list.json 동기화 스크립트
매체 구분표: https://docs.google.com/spreadsheets/d/1Zi7XEMHV-LtqmA-wYcZmfuZZRTnaUiFdJ0rixj24Mzs
"""
import json
import os
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SHEET_ID         = "1Zi7XEMHV-LtqmA-wYcZmfuZZRTnaUiFdJ0rixj24Mzs"
RANGE            = "시트1!A:D"
TOKEN_FILE       = os.path.join(os.path.dirname(__file__), "token_sheets.json")
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")
JSON_PATH        = os.path.join(os.path.dirname(__file__), "media_list.json")
SCOPES           = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def get_sheets_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("sheets", "v4", credentials=creds)


def fetch_sheet():
    """Google Sheets에서 (tier, canonical, [alias, ...]) 리스트 반환"""
    service = get_sheets_service()
    result  = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=RANGE
    ).execute()
    out = []
    for r in result.get("values", [])[1:]:  # 헤더 제거
        if len(r) < 2:
            continue
        tier = r[0].strip()
        name = r[1].strip()
        if not name or name.lower() == "nan":
            continue
        # C·D열 별칭 — 셀 안에 쉼표로 여러 개 기입한 경우도 분리
        aliases = []
        for cell in r[2:]:
            for part in cell.split(","):
                a = part.strip()
                if a:
                    aliases.append(a)
        out.append((tier, name, aliases))
    return out


def sync():
    # ── 현재 파일 로드 (external_keywords 보존) ───────────────────
    with open(JSON_PATH, encoding="utf-8") as f:
        current = json.load(f)
    preserved_ext_kw = current.get("external_keywords", [])

    # ── 시트 데이터 파싱 ──────────────────────────────────────────
    rows = fetch_sheet()

    new_tiers      = {"1": [], "2": [], "3": []}
    new_other      = []
    new_aliases    = {}   # alias → canonical  (1/2/3티어)
    new_oth_aliases = {}  # alias → canonical  (기타)
    tier_map       = {"1티어": "1", "2티어": "2", "3티어": "3"}

    for tier_label, name, sheet_aliases in rows:
        t = tier_map.get(tier_label)
        if t:
            new_tiers[t].append(name)
            for a in sheet_aliases:
                if a != name:
                    new_aliases[a] = name
        elif tier_label == "기타":
            new_other.append(name)
            for a in sheet_aliases:
                if a != name:
                    new_oth_aliases[a] = name

    # 중복 제거
    tier_set = set()
    for k in new_tiers:
        new_tiers[k] = list(dict.fromkeys(new_tiers[k]))
        tier_set.update(new_tiers[k])

    # 티어에 있는 항목은 기타에서 제외
    new_other = list(dict.fromkeys(n for n in new_other if n not in tier_set))

    # other_aliases의 canonical이 어디에도 없으면 기타에 추가
    for canonical in set(new_oth_aliases.values()):
        if canonical not in tier_set and canonical not in new_other:
            new_other.append(canonical)

    # ── 파일 저장 ─────────────────────────────────────────────────
    updated = {
        "other":             new_other,
        "other_aliases":     new_oth_aliases,
        "external_keywords": preserved_ext_kw,
        "tiers":             new_tiers,
        "aliases":           new_aliases,
    }
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)

    alias_count = len(new_aliases) + len(new_oth_aliases)
    summary = (
        f"동기화 완료 [{datetime.now().strftime('%Y-%m-%d %H:%M')}]  "
        f"1티어 {len(new_tiers['1'])}개 · "
        f"2티어 {len(new_tiers['2'])}개 · "
        f"3티어 {len(new_tiers['3'])}개 · "
        f"기타 {len(new_other)}개 · "
        f"별칭 {alias_count}개"
    )
    print(summary)
    return summary


if __name__ == "__main__":
    sync()

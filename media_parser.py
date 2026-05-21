"""
meeting_with 문자열에서 (매체명, 기자명, 티어) 추출
- 관리 매체 (tier 1/2/3): 커버리지 분석 포함
- 기타 매체 (other): 매체 차트에는 포함, 커버리지 제외
- 외부/기타: 광고·행사·포럼 등 비편집 미팅 → 집계 제외
"""
import json, re, os

_MEDIA_LIST_PATH = os.path.join(os.path.dirname(__file__), "media_list.json")


def load_media_tiers():
    with open(_MEDIA_LIST_PATH, encoding="utf-8") as f:
        data = json.load(f)

    tiers = {}       # 정식명 → 숫자 티어 (1/2/3)
    other = set()    # 기타 매체 (집계 O, 커버리지 X)
    aliases = {}     # 별칭 → 정식명
    all_keys = []    # 매칭 대상 전체 키

    for tier, names in data["tiers"].items():
        for name in names:
            tiers[name] = int(tier)
            all_keys.append(name)

    for name in data.get("other", []):
        other.add(name)
        all_keys.append(name)

    for alias, canonical in data.get("aliases", {}).items():
        aliases[alias] = canonical
        all_keys.append(alias)

    for alias, canonical in data.get("other_aliases", {}).items():
        aliases[alias] = canonical
        all_keys.append(alias)

    # 긴 것 먼저 (longest match)
    all_keys = sorted(set(all_keys), key=len, reverse=True)
    return tiers, other, aliases, all_keys


MEDIA_TIERS, OTHER_MEDIA, ALIASES, ALL_KEYS = load_media_tiers()

# 외부/기타 키워드 (광고·행사·포럼 등)
with open(_MEDIA_LIST_PATH, encoding="utf-8") as _f:
    _data = json.load(_f)
EXTERNAL_KEYWORDS = set(_data.get("external_keywords", []))

# 내부 일정 키워드
INTERNAL_KEYWORDS = {
    "off", "휴가", "마이타임", "연차", "반차", "오전반차", "오후반차",
    "병원", "점심", "저녁", "가족돌봄휴가", "돌봄휴가", "가족돌봄",
    "건강검진", "건강검진 휴가", "마타", "인사미팅", "내부컴",
    "회의", "업무", "온보딩", "훈련",
}

# 제거할 접미사 패턴
_STRIP = re.compile(
    r"\s*(w\s*[./]?\s*(업계|벤처스|픽코마|리나|페이|\S+)|with\s+\S+|\(.*?\)|\[.*?\])\s*",
    re.IGNORECASE
)
_BRACKET_KW = re.compile(r'\[([^\]]+)\]')
# 기자명 뒤 직함 제거 (부장, 기자, 차장, 국장 등)
_JOB_TITLE = re.compile(
    r"\s+(기자|부장|차장|과장|팀장|국장|편집장|선임기자|수습기자|기자님|대기자|논설위원)$"
)


def parse_media(meeting_with: str):
    """
    반환: (정식_매체명, 기자명, 티어)
    - 관리 매체: tier = 1/2/3
    - 기타 매체: tier = "기타"
    - 미식별:    (None, text, None)
    """
    text = _STRIP.sub(" ", meeting_with).strip()
    # `..` 패턴 처리: "스마트비즈..이장혁" → "스마트비즈 이장혁"
    text = re.sub(r'\.{2,}', ' ', text).strip()

    for key in ALL_KEYS:
        if text == key or text.startswith(key + " "):
            canonical  = ALIASES.get(key, key)
            journalist = text[len(key):].strip()
            journalist = _JOB_TITLE.sub("", journalist).strip()  # 직함 제거
            if canonical in MEDIA_TIERS:
                tier = MEDIA_TIERS[canonical]
            elif canonical in OTHER_MEDIA or key in OTHER_MEDIA:
                tier = "기타"
                canonical = ALIASES.get(key, key)
            else:
                tier = "기타"
            return canonical, journalist, tier

    return None, text, None


def classify_meeting(meeting_with: str):
    """
    반환: 'media' | 'external' | 'internal'
    - media:    매체 미팅 (집계 O)
    - external: 광고/행사/포럼 등 비편집 (집계 X)
    - internal: 내부/휴가 등 (집계 X)
    """
    t = meeting_with.strip().lower()

    # 내부 판단
    if any(t == k or t.startswith(k) for k in INTERNAL_KEYWORDS):
        return "internal"

    # [광고], [행사] 등 브라켓 외부 키워드 → strip 전에 먼저 체크
    for m in _BRACKET_KW.finditer(t):
        if m.group(1).strip() in EXTERNAL_KEYWORDS:
            return "external"

    # 매체 인식 후 기자명에 외부 키워드 포함 여부 확인
    media, journalist, _ = parse_media(meeting_with)
    if media and journalist:
        j_lower = journalist.lower()
        if any(kw in j_lower for kw in EXTERNAL_KEYWORDS):
            return "external"

    if media:
        return "media"

    # 매체 미인식이지만 외부 키워드 단독 → internal 처리
    return "internal"


def is_external_meeting(meeting_with: str) -> bool:
    """기존 호환용: 집계 대상 여부"""
    return classify_meeting(meeting_with) == "media"


def parse_multi_media(meeting_with: str):
    """
    쉼표로 구분된 복수 매체+기자 파싱.
    "전자신문 남궁경, 이데일리 권하영" → [(전자신문, 남궁경, 3), (이데일리, 권하영, 2)]
    "전자신문 남궁경, 최아리" → [(전자신문, '남궁경, 최아리', 3)]  ← 동일 매체 복수 기자
    """
    parts = [p.strip() for p in meeting_with.split(",") if p.strip()]
    results = []
    cur_media, cur_tier, cur_journalists = None, None, []

    for part in parts:
        media, journalist, tier = parse_media(part)
        if media:
            if cur_media:
                results.append((cur_media, ", ".join(filter(None, cur_journalists)), cur_tier))
            cur_media, cur_tier, cur_journalists = media, tier, [journalist] if journalist else []
        else:
            if cur_media:
                # parse_media의 journalist 반환값은 이미 괄호·접미사가 제거된 값
                cleaned = journalist.strip()
                if cleaned:
                    cur_journalists.append(cleaned)

    if cur_media:
        results.append((cur_media, ", ".join(filter(None, cur_journalists)), cur_tier))

    return results if results else [(None, meeting_with, None)]

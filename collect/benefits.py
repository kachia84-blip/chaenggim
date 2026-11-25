import os
import re
from datetime import date
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from .common import DATA_DIR, atomic_write_json, get_key, http_get_json, kst_today, require_minimum


BASE_URL = "https://api.odcloud.kr/api/gov24/v3"
NATIONWIDE = "전국"
REGIONS = {
    "서울특별시": ("서울", "서울시"),
    "부산광역시": ("부산", "부산시"),
    "대구광역시": ("대구", "대구시"),
    "인천광역시": ("인천", "인천시"),
    "광주광역시": ("광주", "광주시"),
    "대전광역시": ("대전", "대전시"),
    "울산광역시": ("울산", "울산시"),
    "세종특별자치시": ("세종", "세종시"),
    "경기도": ("경기",),
    "강원특별자치도": ("강원", "강원도"),
    "충청북도": ("충북", "충북도"),
    "충청남도": ("충남", "충남도"),
    "전북특별자치도": ("전북", "전북도", "전라북도"),
    "전라남도": ("전남", "전남도"),
    "경상북도": ("경북", "경북도"),
    "경상남도": ("경남", "경남도"),
    "제주특별자치도": ("제주", "제주도"),
}
REGION_ALIASES = {alias: sido for sido, aliases in REGIONS.items() for alias in (sido, *aliases)}
REGION_PREFIX = re.compile(
    r"^(" + "|".join(sorted(REGION_ALIASES, key=len, reverse=True)) + r")(?=(?:청)?(?:$|[\s()·,/]))"
)
DISTRICT_PREFIX = re.compile(r"^([가-힣0-9]+?[시군구])(?:청)?(?=$|[\s()·,/])")
LOCAL_TYPE = re.compile(r"(?:지방|광역|기초)\s*자치\s*단체|지자체|지방정부|^(?:시도|시군구)$")
DEADLINE_DATE = re.compile(r"(?<!\d)(\d{4})([.-])(\d{2})\2(\d{2})(?!\d)")

FIELD_EMOJI = {
    "생활안정": "💰", "주거·자립": "🏠", "보육·교육": "🎒", "고용·창업": "💼", "보건·의료": "🏥",
    "행정·안전": "🏛️", "임신·출산": "🍼", "보호·돌봄": "🤝", "문화·환경": "🎨", "농림축산어업": "🌾",
}
FLAG_NAMES = {
    "JA0326": "근로자/직장인", "JA0327": "구직자/실업자", "JA0320": "대학생", "JA0404": "1인가구",
    "JA0412": "무주택세대", "JA0411": "다자녀가구", "JA0403": "한부모가정", "JA0302": "임산부",
    "JA0303": "출산/입양", "JA0328": "장애인", "JA0329": "국가보훈대상자",
}
INCOME_CODES = ("JA0201", "JA0202", "JA0203", "JA0204", "JA0205")


def normalize_sido(value):
    return REGION_ALIASES.get(value.strip(), "")


def benefit_region(org_type, org):
    if org_type and not LOCAL_TYPE.search(org_type):
        return NATIONWIDE, ""
    province = REGION_PREFIX.match(org)
    if not province:
        return (None if org_type else NATIONWIDE), ""
    remaining = org[province.end():].removeprefix("청").lstrip(" (,·/")
    district = DISTRICT_PREFIX.match(remaining)
    if not district:
        return REGION_ALIASES[province[1]], ""
    name = district[1]
    subdistrict = DISTRICT_PREFIX.match(remaining[district.end():].lstrip())
    if name.endswith("시") and subdistrict and subdistrict[1].endswith("구"):
        name += " " + subdistrict[1]
    return REGION_ALIASES[province[1]], name


def parse_deadline(text):
    dates = list(DEADLINE_DATE.finditer(text))
    if not dates:
        return None
    last = dates[-1]
    if re.match(r"[.\s]*(?:[~～]|–|—|-|부터|이후)", text[last.end():]):
        return None
    try:
        return date(int(last[1]), int(last[3]), int(last[4])).isoformat()
    except ValueError:
        return None


def _age(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().isdecimal():
        return int(value)
    return None


def map_benefit(service, conditions, sigungu):
    def field(name):
        return (service.get(name) or "").strip()

    age_min = _age(conditions.get("JA0110"))
    age_max = _age(conditions.get("JA0111"))
    if age_min == age_max == 0:
        age_min = age_max = None
    category = field("서비스분야")
    deadline_text = field("신청기한")
    return {
        "id": field("서비스ID"), "name": field("서비스명"), "org": field("소관기관명"),
        "summary": field("서비스목적요약")[:120], "target": field("지원대상")[:160],
        "amount": field("지원내용")[:120], "how": field("신청방법")[:120], "url": field("상세조회URL"),
        "deadline": parse_deadline(deadline_text), "deadlineText": deadline_text[:60],
        "field": category, "emoji": FIELD_EMOJI.get(category, "📌"), "updated": field("수정일시"),
        "sigungu": sigungu,
        "cond": {
            "ageMin": age_min, "ageMax": age_max,
            "income": [code for code in INCOME_CODES if conditions.get(code) == "Y"],
            "flags": [name for code, name in FLAG_NAMES.items() if conditions.get(code) == "Y"],
        },
    }


def gov_pages(endpoint, key):
    page_size = 500
    page, received = 1, 0
    while True:
        response = http_get_json(f"{BASE_URL}/{endpoint}", {
            "serviceKey": key, "page": page, "perPage": page_size,
        })
        rows = response.get("data")
        if not isinstance(rows, list) or response.get("page", page) != page:
            raise RuntimeError(f"보조금24 {endpoint}: unexpected page {page}")
        total = response.get("matchCount", response.get("totalCount"))
        if not rows and total is not None and received < total:
            raise RuntimeError(f"보조금24 {endpoint}: incomplete pagination")
        yield from rows
        received += len(rows)
        if (total is not None and received >= total) or (total is None and len(rows) < page_size):
            return
        page += 1


def _write_regions(directory, groups):
    directory.mkdir(parents=True, exist_ok=True)
    files = {f"{region}.json": rows for region, rows in groups.items()}
    files["index.json"] = {region: len(rows) for region, rows in groups.items()}
    # Stage every file before replacing any current output. Keep backups for rollback.
    with TemporaryDirectory(dir=directory) as temporary:
        staged = Path(temporary)
        backups = {}
        for name, rows in files.items():
            atomic_write_json(staged / name, rows)
            existing = directory / name
            if existing.exists():
                backups[name] = copyfile(existing, staged / f"{name}.bak")
        published = []
        try:
            for name in files:
                os.replace(staged / name, directory / name)
                published.append(name)
        except OSError:
            for name in reversed(published):
                if name in backups:
                    os.replace(backups[name], directory / name)
                else:
                    (directory / name).unlink()
            raise


def collect(data_dir=DATA_DIR, today=None):
    today_text = (today or kst_today()).isoformat()
    key = get_key()
    services = list(gov_pages("serviceList", key))
    conditions = {row["서비스ID"]: row for row in gov_pages("supportConditions", key)}
    groups = {region: [] for region in (NATIONWIDE, *REGIONS)}
    seen = set()
    for service in services:
        users = service.get("사용자구분") or ""
        if "개인" not in users and "가구" not in users:
            continue
        region, district = benefit_region((service.get("소관기관유형") or "").strip(),
                                         (service.get("소관기관명") or "").strip())
        if region is None:
            continue
        item = map_benefit(service, conditions.get(service.get("서비스ID"), {}), district)
        if not item["id"] or item["id"] in seen or (item["deadline"] and item["deadline"] < today_text):
            continue
        seen.add(item["id"])
        groups[region].append(item)

    require_minimum("보조금24", len(seen), 50)
    for rows in groups.values():
        rows.sort(key=lambda item: (item["deadline"] or "9999-12-31", item["name"]))
    _write_regions(Path(data_dir) / "benefits", groups)
    return len(seen)

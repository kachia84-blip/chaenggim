import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from html import unescape
from pathlib import Path
from urllib.parse import unquote_plus

from .benefits import DISTRICT_PREFIX, REGION_PREFIX, normalize_sido
from .common import DATA_DIR, atomic_write_json, get_key, http_get_json, kst_today, log, require_minimum


BASE_URL = "https://apis.data.go.kr/B553457/cultureinfo"
CULTURE_HOME = "https://www.culture.go.kr"
PAGE_SIZE = 100
MAX_EVENTS = 3000
REALM_EMOJI = {
    "연극": "🎭", "음악": "🎵", "콘서트": "🎵", "국악": "🪕", "무용": "🩰", "전시": "🖼️",
    "뮤지컬": "🎶", "오페라": "🎶", "아동": "🧸", "어린이": "🧸", "가족": "🧸", "행사": "🎪",
    "축제": "🎪", "교육": "🧩", "체험": "🧩",
}
WON_AMOUNT = re.compile(r"\d[\d,.\s]*(?:억|만|천|백)?\s*원")
APPLICATION = r"(?:사전\s*)?(?:신청|접수|예약)"
NO_BOOKING = re.compile(rf"{APPLICATION}(?:[이가])?\s*(?:없이|불필요|필요\s*없(?:음|습니다))")
OPEN_ENTRY = re.compile(r"자유\s*(?:관람|입장)|현장\s*입장|누구나")
REQUIRED_ENTRY = re.compile(rf"{APPLICATION}\s*(?:필수|필요)|사전\s*(?:예약|신청|접수)")
BOOKED_ENTRY = re.compile(r"예약(?!\s*불가)|(?:신청|접수)\s*(?:마감|종료|기한|기간)")
DATE_SEPARATOR = r"(?:\s*[./-]\s*|\s*년\s*)"
APPLICATION_DATE = (
    rf"(?<!\d)(?P<year>\d{{4}}){DATE_SEPARATOR}(?P<month>\d{{1,2}})"
    rf"(?:\s*[./-]\s*|\s*월\s*)(?P<day>\d{{1,2}})(?!\d)(?:\s*일|\.(?!\d))?"
)
DATE_RANGE = rf"(?:{APPLICATION_DATE.replace('P<', 'P<start_')}\s*[~～–—-]\s*)?{APPLICATION_DATE}"
DEADLINE_LABEL = r"(?:마감\s*(?:일시|일)?|종료\s*(?:일시|일)?|기한)"
DATE_NOTE = r"(?:[ \t]*\([월화수목금토일](?:요일)?\))?(?:[ \t]+\d{1,2}:\d{2})?"
APPLY_DEADLINE = re.compile(
    rf"{APPLICATION}\s*(?P<label>{DEADLINE_LABEL}|기간)?\s*(?:[:：=]\s*)?{DATE_RANGE}"
    rf"{DATE_NOTE}(?P<until>\s*까지)?(?!\d)"
)
APPLY_DATE_FIRST = re.compile(rf"{APPLICATION_DATE}{DATE_NOTE}\s*(?:까지\s*{APPLICATION}|{APPLICATION}\s*{DEADLINE_LABEL})")
EVENT_TIME = re.compile(
    r"(?:(?:[•○]|(?<!\S))(?:시작\s*(?:시각|시간)|(?:공연|행사|관람|운영)\s*시간)|^[ \t]*시간)"
    r"[ \t]*[:：][ \t]*(\S[^\r\n]*)",
    re.M,
)


def is_free(price):
    return "무료" in price and not WON_AMOUNT.search(price)


def _date(value):
    if not re.fullmatch(r"\d{8}|\d{4}[-.]\d{2}[-.]\d{2}", value):
        return None
    digits = re.sub(r"[-.]", "", value)
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:])).isoformat()
    except ValueError:
        return None


def _plain_text(value):
    text = unescape(str(value or ""))
    text = re.sub(r"<(?:br\b[^>]*|/?(?:p|li|div|tr|td|th)\b[^>]*)>", "\n", text, flags=re.I)
    return re.sub(r"<[^>]+>", "", text).strip()


def _normalize_sigungu(value, sido):
    province = REGION_PREFIX.match(value)
    remaining = value
    if province:
        after_prefix = value[province.end():].lstrip(" (,·/")
        if after_prefix or province[1] != "광주시" or normalize_sido(province[1]) == sido:
            remaining = after_prefix
    elif sido and value.startswith(sido):
        remaining = value[len(sido):]
    district = DISTRICT_PREFIX.match(remaining)
    if not district:
        return ""
    # 수원시 영통구처럼 자치구가 아닌 구도 시 이름과 함께 보존한다.
    subdistrict = DISTRICT_PREFIX.match(remaining[district.end():].strip())
    name = district[1]
    if name.endswith("시") and subdistrict and subdistrict[1].endswith("구"):
        return f"{name} {subdistrict[1]}"
    return name


def _entry(text):
    without_exceptions = NO_BOOKING.sub("", text)
    if REQUIRED_ENTRY.search(without_exceptions):
        return "예약 필요"
    if OPEN_ENTRY.search(text) or NO_BOOKING.search(text):
        return "자유 입장"
    return "예약 필요" if BOOKED_ENTRY.search(without_exceptions) else ""


def _apply_end(text):
    deadlines = set()
    for line in text.splitlines():
        for match in APPLY_DEADLINE.finditer(line):
            if not (match["until"] or match["start_year"] or match["label"] not in (None, "기간")):
                continue
            if re.match(r"\s*(?:[~～–—-]|부터|이후)", line[match.end():]):
                continue
            deadlines.add(_matched_date(match))
        for match in APPLY_DATE_FIRST.finditer(line):
            deadlines.add(_matched_date(match))
    deadlines.discard(None)
    return deadlines.pop() if len(deadlines) == 1 else None


def _matched_date(match):
    try:
        return date(*(int(match[key]) for key in ("year", "month", "day"))).isoformat()
    except ValueError:
        return None


def map_event(item, detail):
    def field(name):
        return str(item.get(name) or detail.get(name) or "").strip()

    price = str(detail.get("price") or "").strip()
    sido = normalize_sido(field("area"))
    description = _plain_text(detail.get("contents1"))
    booking_text = "\n".join((_plain_text(price), description, unquote_plus(_plain_text(detail.get("url")))))
    time_match = EVENT_TIME.search(description)
    time_text = str(detail.get("startTime") or detail.get("time") or (time_match[1] if time_match else ""))
    extra = {
        "time": " ".join(time_text.split())[:80],
        "placeAddr": field("placeAddr"),
        "description": " ".join(description.split())[:180],
    }
    realm = field("realmName")
    category = re.split(r"[/·]", realm, maxsplit=1)[0].strip()
    image = str(item.get("thumbnail") or "").strip()
    if image.startswith("http://"):
        image = "https://" + image.removeprefix("http://")
    url = next((value for name in ("url", "homepage", "placeUrl")
                if (value := str(detail.get(name) or "").strip()).startswith(("https://", "http://"))), CULTURE_HOME)
    return {
        "id": field("seq"), "title": field("title"), "venue": field("place"),
        "sido": sido, "sigungu": _normalize_sigungu(field("sigungu"), sido),
        "start": _date(field("startDate")), "end": _date(field("endDate")),
        "realm": realm, "emoji": REALM_EMOJI.get(category, "🎟️"), "price": price[:60],
        "free": is_free(price), "ticketOpen": None, "url": url, "image": image,
        "entry": _entry(booking_text), "applyEnd": _apply_end(booking_text),
        **{name: value for name, value in extra.items() if value},
    }


def _request(endpoint, params):
    if endpoint == "detail2":
        time.sleep(0.25)  # 초당 요청 한도(429) 피하기
        response = http_get_json(f"{BASE_URL}/{endpoint}", params, retries=5, backoff=2.0)
    else:
        response = http_get_json(f"{BASE_URL}/{endpoint}", params)
    response = response.get("response", response)
    code = str(response.get("header", {}).get("resultCode", ""))
    if not code or not code.isdecimal() or int(code) != 0:
        raise RuntimeError(f"문화정보 {endpoint}: API result {code if code.isdecimal() else 'unknown'}")
    body = response.get("body")
    if not isinstance(body, dict):
        raise RuntimeError(f"문화정보 {endpoint}: missing response body")
    items = body.get("items") or {}
    rows = items.get("item") or []
    return body, rows if isinstance(rows, list) else [rows]


def period_rows(key, today):
    params = {
        "serviceKey": key, "numOfrows": PAGE_SIZE,
        "from": today.strftime("%Y%m%d"), "to": (today + timedelta(days=45)).strftime("%Y%m%d"),
    }
    page, received = 1, 0
    while received < MAX_EVENTS:
        body, rows = _request("period2", {**params, "PageNo": page})
        total = int(body["totalCount"])
        if int(body.get("PageNo", page)) != page or (not rows and received < total):
            raise RuntimeError(f"문화정보 period2: incomplete pagination at page {page}")
        yield from rows[:MAX_EVENTS - received]
        received += len(rows)
        if received >= total:
            return
        page += 1


def _detail(key, item):
    seq = item["seq"]
    _, rows = _request("detail2", {"serviceKey": key, "seq": seq})
    if len(rows) != 1 or str(rows[0].get("seq")) != str(seq):
        raise RuntimeError("문화정보 detail2: missing or mismatched detail")
    return map_event(item, rows[0])


def collect(data_dir=DATA_DIR, today=None):
    today = today or kst_today()
    key = get_key()
    candidates = {str(row["seq"]): row for row in period_rows(key, today) if row.get("seq")}
    require_minimum("문화정보", len(candidates), 10)
    def safe_detail(row):  # 상세 몇 건이 막혀도 나머지는 살린다
        try:
            return _detail(key, row)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=1) as pool:  # 2개 동시 요청도 HTTP 429로 막혔다(2026-11-25) → 하나씩, 쉬어 가며
        events = list(pool.map(safe_detail, candidates.values()))
    failed = events.count(None)
    if failed > len(events) * 0.2:
        raise RuntimeError(f"문화정보 detail2: {failed}/{len(events)}건 실패")
    if failed:
        log(f"events: detail2 {failed}/{len(events)}건 건너뜀")
    events = [item for item in events if item]
    today_text = today.isoformat()
    events = [item for item in events if item["start"] and item["end"] and item["end"] >= today_text]
    require_minimum("문화정보", len(events), 10)
    events.sort(key=lambda item: (item["start"], item["title"], item["id"]))
    atomic_write_json(Path(data_dir) / "events.json", events)
    return len(events)

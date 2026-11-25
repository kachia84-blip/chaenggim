import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

from .benefits import normalize_sido
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


def map_event(item, detail):
    def field(name):
        return str(item.get(name) or detail.get(name) or "").strip()

    price = str(detail.get("price") or "").strip()
    realm = field("realmName")
    category = re.split(r"[/·]", realm, maxsplit=1)[0].strip()
    image = str(item.get("thumbnail") or "").strip()
    if image.startswith("http://"):
        image = "https://" + image.removeprefix("http://")
    url = next((value for name in ("url", "homepage", "placeUrl")
                if (value := str(detail.get(name) or "").strip()).startswith(("https://", "http://"))), CULTURE_HOME)
    return {
        "id": field("seq"), "title": field("title"), "venue": field("place"),
        "sido": normalize_sido(field("area")), "sigungu": field("sigungu"),
        "start": _date(field("startDate")), "end": _date(field("endDate")),
        "realm": realm, "emoji": REALM_EMOJI.get(category, "🎟️"), "price": price[:60],
        "free": is_free(price), "ticketOpen": None, "url": url, "image": image,
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

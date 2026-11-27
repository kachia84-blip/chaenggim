import html
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from .common import DATA_DIR, atomic_write_json, get_key, http_get_json, kst_today, log, require_minimum


BASE_URL = "http://openapi.seoul.go.kr:8088"
KEY_NAME = "SEOUL_API_KEY"
SERVICES = ("ListPublicReservationCulture", "ListPublicReservationEducation")
OUTPUT_FILE = "seoul_events.json"
REALM_EMOJI = {
    "교육체험": "🧩", "교육·체험": "🧩", "교육/체험": "🧩", "교육": "🧩", "체험": "🧩",
    "전시/관람": "🖼️", "전시": "🖼️", "관람": "🖼️", "공연": "🎵",
    "자연/과학": "🌿", "자연": "🌿", "과학": "🌿", "문화행사": "🎪",
    # 공원·숲 프로그램이 서울 자료의 3분의 1이라 기본 아이콘(🎟️)만 늘어서지 않게 나눈다.
    "공원탐방": "🌳", "산림여가": "🌲", "도시농업": "🌱", "역사": "🏛️", "청년정보": "🙋",
    "공예/취미": "🧶", "서울형키즈카페": "🧸", "교양/어학": "📚", "스포츠": "⚽", "미술제작": "🎨",
}
HOST_PREFIX = re.compile(r"^\[([^\]]+)\]\s*(.+)$")


def _date_time(value):
    # "2026-11-29 17:30:00.0"처럼 끝에 ".0"이 붙는데 파이썬 3.10은 이를 못 읽는다.
    value = value.split(".", 1)[0]
    if re.fullmatch(r"\d{8}", value):  # "20261201"도 3.10은 못 읽는다
        value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def map_event(row, today):
    def field(name):
        # 제목에 "&lt;"나 두 번 덧씌운 "&amp;lt;" 같은 기호가 섞여 온다
        return html.unescape(html.unescape(str(row.get(name) or ""))).strip()

    status = field("SVCSTATNM")
    if field("PAYATNM") != "무료" or status not in ("접수중", "안내중"):
        return None
    receipt_start = _date_time(field("RCPTBGNDT"))
    receipt_end_text = field("RCPTENDDT")
    receipt_end = _date_time(receipt_end_text)
    # "27일 00:00·00:02 마감"은 사실상 26일 밤 마감이라 하루 당기고 시각은 뺀다.
    midnight = bool(receipt_end) and len(receipt_end_text) > 10 and receipt_end.hour == 0 and receipt_end.minute <= 5
    if midnight:
        receipt_end -= timedelta(days=1)
    has_deadline = receipt_end and receipt_end.date() >= today
    opening_soon = (status == "안내중" and receipt_start and
                    today <= receipt_start.date() <= today + timedelta(days=30))
    if not (has_deadline or opening_soon):
        return None

    service_id = field("SVCID")
    title = field("SVCNM")
    start = _date_time(field("SVCOPNBGNDT"))
    end = _date_time(field("SVCOPNENDDT"))
    if not all((service_id, title, start, end)):
        return None

    prefix = HOST_PREFIX.match(title)
    realm = field("MINCLASSNM")
    image = field("IMGURL")
    if image.startswith("//"):
        image = "https:" + image
    elif image.lower().startswith("http://"):
        image = "https://" + image[7:]
    url = field("SVCURL")
    if url.startswith("http://yeyak.seoul.go.kr/"):
        url = "https://" + url[7:]
    return {
        "id": "seoul-" + service_id,
        "title": prefix[2].strip() if prefix else title,
        "host": prefix[1].strip() if prefix else "",
        "venue": field("PLACENM").rsplit(">", 1)[-1].strip(),
        "sido": "서울특별시", "sigungu": field("AREANM"),
        "start": start.date().isoformat(), "end": end.date().isoformat(),
        "free": True, "price": "무료", "entry": "예약 필요", "ticketOpen": None,
        "applyStart": receipt_start.date().isoformat() if receipt_start else None,
        "applyEnd": receipt_end.date().isoformat() if receipt_end else None,
        "applyEndTime": receipt_end.strftime("%H:%M") if receipt_end and len(receipt_end_text) > 10 and not midnight else None,
        "status": status, "target": field("USETGTINFO"), "realm": realm,
        "emoji": REALM_EMOJI.get(realm, "🎟️"),
        "image": image if image.lower().startswith("https://") else "",
        "url": url, "source": "seoul",
    }


def _page(key, service, first, last):
    url = f"{BASE_URL}/{quote(key, safe='')}/json/{service}/{first}/{last}/"
    try:
        response = http_get_json(url, {})
    except RuntimeError:
        raise RuntimeError(f"{service}: request failed at row {first}") from None
    body = response.get(service, response)
    try:
        code = body["RESULT"]["CODE"]
        if code == "INFO-200":
            return 0, []
        if code == "INFO-000":
            total = int(body["list_total_count"])
            rows = body.get("row", [])
            if (total >= 0 and isinstance(rows, list) and
                    all(isinstance(row, dict) for row in rows)):
                return total, rows
    except (KeyError, TypeError, ValueError):
        pass
    raise RuntimeError(f"{service}: invalid API response at row {first}")


def _rows(key, service):
    if key == "sample":
        _, rows = _page(key, service, 1, 5)
        yield from rows
        return

    first, last = 1, 1000
    while True:
        total, rows = _page(key, service, first, last)
        if len(rows) != min(last, total) - first + 1:
            raise RuntimeError(f"{service}: incomplete page at row {first}")
        yield from rows
        if last >= total:
            return
        first, last = last + 1, min(last + 1000, total)


def collect(data_dir=DATA_DIR, today=None):
    today = today or kst_today()
    try:
        key = get_key(KEY_NAME)
    except RuntimeError:
        key = "sample"
    log("seoul: sample key mode" if key == "sample" else "seoul: configured key mode")

    items = {}
    for service in SERVICES:
        for row in _rows(key, service):
            item = map_event(row, today)
            if item:
                identity = (str(row["SVCNM"]).strip(), item["venue"], item["applyEnd"])
                items.setdefault(identity, item)

    if key != "sample":
        require_minimum("seoul", len(items), 20)
    rows = sorted(items.values(), key=lambda item: (item["applyEnd"] or "9999-12-31", item["start"]))
    atomic_write_json(Path(data_dir) / OUTPUT_FILE, rows)
    return len(rows)

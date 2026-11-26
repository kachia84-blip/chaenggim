import json
import os
import unittest
from datetime import date
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from collect import benefits, common, events, run_all, seoul_reserve


TODAY = date(2026, 11, 25)
KEY = "fixture+key="
SERVICE = {
    "서비스ID": "LOCAL-1", "서비스명": "주거비 지원", "소관기관명": "서울특별시 강남구청",
    "서비스목적요약": "가" * 125, "지원대상": "나" * 170, "지원내용": "다" * 125,
    "신청방법": "라" * 125, "상세조회URL": "https://www.gov.kr/", "신청기한": "2026.11.01.~2026-11-30",
    "서비스분야": "주거·자립", "수정일시": "2026-11-24 09:00:00", "소관기관유형": "지방자치단체",
    "사용자구분": "개인,가구",
}
CONDITIONS = {
    "서비스ID": "LOCAL-1", "JA0110": 19, "JA0111": 34, "JA0201": "Y", "JA0203": "N",
    "JA0326": "Y", "JA0412": "Y",
}
EVENT = {
    "seq": "001", "title": "가을 공연", "startDate": "20261125", "endDate": "2026-12-01",
    "place": "공연장", "realmName": "음악/콘서트", "area": "서울", "sigungu": "종로구",
    "thumbnail": "http://images.invalid/poster.jpg",
}
RESERVATION = {
    "SVCID": "S001", "SVCNM": "[서울공예박물관] 어린이 공예", "SVCSTATNM": "접수중", "PAYATNM": "무료",
    "AREANM": "종로구", "PLACENM": "종로구 > 서울공예박물관 > 교육실",
    "RCPTBGNDT": "2026-11-20 09:00:00.0", "RCPTENDDT": "2026-11-25 17:30:00.0",
    "SVCOPNBGNDT": "2026-12-01 10:00:00", "SVCOPNENDDT": "2026-12-02 16:00:00",
    "USETGTINFO": " 초등 1~3학년 ", "MINCLASSNM": "교육체험", "IMGURL": "http://images.invalid/poster.jpg",
    "SVCURL": "https://yeyak.seoul.go.kr/reservation", "DTLCONT": "<p>상세 설명</p>",
}


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _culture_xml(items, pagination=""):
    return ("<response><header><resultCode>00</resultCode></header><body>"
            f"<items>{items}</items>{pagination}</body></response>").encode("utf-8")


class CommonTests(unittest.TestCase):
    def test_http_retries_and_reads_json_and_repeated_xml_items(self):
        xml = _culture_xml("<item><seq>1</seq></item><item><seq>2</seq></item>")
        fixtures = [TimeoutError("secret URL"), BytesIO(b'{"data": []}'), BytesIO(xml)]
        with patch.object(common, "urlopen", side_effect=fixtures) as opening:
            with patch.object(common.time, "sleep") as sleep:
                args = ("https://fixture.invalid", {"serviceKey": "fixture%2Bkey%3D"})
                self.assertEqual(common.http_get_json(*args, backoff=0.5), {"data": []})
                sleep.assert_called_once_with(0.5)
                response = common.http_get_json(*args)
        self.assertEqual(response["body"]["items"]["item"], [{"seq": "1"}, {"seq": "2"}])
        self.assertEqual(parse_qs(urlsplit(opening.call_args.args[0]).query), {"serviceKey": [KEY]})

    def test_log_keeps_300_lines_and_redacts_key_variants(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "last_run.log"
            path.write_text("\n".join(map(str, range(300))) + "\n", encoding="utf-8")
            with patch.object(common, "LOG_PATH", path), patch.dict(os.environ, {common.KEY_NAME: KEY}):
                common.log(f"{KEY} fixture%2Bkey%3D\nfailed")
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual((len(lines), lines[0]), (300, "1"))
            self.assertTrue(lines[-1].endswith("*** *** failed"))


class BenefitTests(unittest.TestCase):
    def test_mapping(self):
        item = benefits.map_benefit(SERVICE, CONDITIONS, "강남구")
        self.assertEqual(item["id"], "LOCAL-1")
        self.assertEqual(item["name"], "주거비 지원")
        self.assertEqual(item["sigungu"], "강남구")
        self.assertEqual(item["deadline"], "2026-11-30")
        self.assertEqual(item["deadlineText"], SERVICE["신청기한"])
        self.assertEqual(item["emoji"], "🏠")
        self.assertEqual([len(item[key]) for key in ("summary", "target", "amount", "how")], [70, 70, 60, 40])  # 휴대폰 용량 때문에 목록 설명을 줄임
        self.assertEqual(item["cond"], {
            "ageMin": 19, "ageMax": 34, "income": ["JA0201"], "need": ["근로자/직장인", "무주택세대"],
        })
        for conditions in ({}, {"JA0110": 0, "JA0111": 0}):
            with self.subTest(conditions=conditions):
                self.assertEqual(benefits.map_benefit(SERVICE, conditions, "")["cond"], {
                    "ageMin": None, "ageMax": None, "income": None, "need": [],
                })

    def test_trait_groups(self):
        personal = {f"JA{code:04}": "Y" for code in (301, 302, 303, *range(313, 321), 322, *range(326, 331))}
        household = {f"JA{code:04}": "Y" for code in (401, 402, 403, 404, *range(410, 415))}
        cases = [
            ({**personal, **household}, []),
            ({**personal, "JA0412": "Y"}, ["무주택세대"]),
            ({**household, "JA0328": "Y"}, ["장애인"]),
            ({"JA0322": "Y", "JA0328": "Y", "JA0313": "Y", "JA0401": "Y"}, ["다문화가족"]),
            ({"JA0410": "Y", "JA0412": "Y", "JA0314": "Y"}, ["어업인"]),
            ({"JA0330": "Y", "JA0413": "Y", "JA0414": "N"}, ["질병/질환자", "신규전입"]),
        ]
        for conditions, expected in cases:
            with self.subTest(conditions=conditions):
                self.assertEqual(benefits.map_benefit(SERVICE, conditions, "")["cond"]["need"], expected)

    def test_income_restrictions(self):
        for selected, expected in [([], None), (range(1, 6), None), ([1, 2], ["JA0201", "JA0202"]), ([3], ["JA0203"])]:
            with self.subTest(selected=selected):
                conditions = {f"JA020{i}": "Y" if i in selected else "N" for i in range(1, 6)}
                self.assertEqual(benefits.map_benefit(SERVICE, conditions, "")["cond"]["income"], expected)

    def test_amount_parsing(self):
        cases = [
            ("월 20만원", "", 2_400_000, "월 20만 원"),
            ("월 최대 20만 원, 최대 12개월", "", 2_400_000, "월 최대 20만 원 · 최대 12개월"),
            ("월 20만원씩 6개월간", "", 1_200_000, "월 20만 원 · 최대 6개월"),
            ("3개월간 월 20만원", "", 600_000, "월 20만 원 · 최대 3개월"),
            ("월 10만 원~20만 원씩 3개월간", "", 600_000, "월 20만 원 · 최대 3개월"),
            ("연 36만원", "", 360_000, "연 36만 원"),
            ("최대 300만원", "", 3_000_000, "최대 300만 원"),
            ("1인당 10만원", "", 100_000, "1인당 10만 원"),
            ("50만원 상당", "", 500_000, "50만 원 상당"),
            ("최대 1억 2천만 원", "", 120_000_000, "최대 1억 2천만 원"),
            ("최대 1.5억 원", "", 150_000_000, "최대 1.5억 원"),
            ("연 1,234,000원", "", 1_234_000, "연 1,234,000 원"),
            ("보증금 2천만 원 지원", "", 20_000_000, "2천만 원"),
            ("연 200만원 또는 월 30만원, 최대 6개월", "", 2_000_000, "연 200만 원"),
            ("금액 미정", "최대 100만원 지원", 1_000_000, "최대 100만 원"),
            ("최대 300만원", "소상공인 융자", None, ""),
            ("대출 보증 한도 2억원", "", None, ""),
            ("최대 100만원", "Startup loan", None, ""),
            ("본인 부담액의 30%", "", None, ""),
        ]
        for support, name, expected, label in cases:
            with self.subTest(support=support, name=name):
                self.assertEqual(benefits.parse_amount(support, name), (expected, label))
                self.assertLessEqual(len(label), 30)

    def test_short_copy_uses_whole_words_and_first_target_clause(self):
        summary = "○  지원 내용\r\n□ - " + "가나다라마바사 아자차카타파하 " * 5
        service = {**SERVICE, "서비스목적요약": summary, "지원대상": "○ 기초생활수급자 및 차상위계층, 6세 이상\r\n- 추가 기준",
                   "지원내용": "지원 대상자에게 " * 10 + "최대 300만원 지급"}
        item = benefits.map_benefit(service, {}, "")
        self.assertEqual(item["who"], "기초생활수급자 및 차상위계층")
        self.assertEqual(item["plain"], "지원 내용 " + ("가나다라마바사 아자차카타파하 " * 3).strip())
        self.assertLessEqual(len(item["plain"]), 60)
        self.assertEqual(item["amountWon"], 3_000_000)

    def test_deadline_parsing(self):
        examples = {
            "2026.11.25.까지": "2026-11-25", "2026-11-25 ~ 2026-12-01": "2026-12-01",
            "상시 신청": None, "2026-11-25부터": None, "2026.11.25. ~ 12.1.": None,
            "2026-02-30": None, "2026-11-25 ~": None,
        }
        for text, expected in examples.items():
            with self.subTest(text=text):
                self.assertEqual(benefits.parse_deadline(text), expected)

    def test_region_split(self):
        examples = {
            ("공공기관", "서울특별시 소재 공단"): ("전국", ""),
            ("지방자치단체", "서울특별시 강남구청"): ("서울특별시", "강남구"),
            ("지방자치단체", "경기도 수원시 영통구"): ("경기도", "수원시 영통구"),
            ("지방자치단체", "전라북도 전주시"): ("전북특별자치도", "전주시"),
            ("지방자치단체", "강원도청"): ("강원특별자치도", ""),
            ("지방자치단체", "중구"): (None, ""),
        }
        for (org_type, org), expected in examples.items():
            with self.subTest(org=org):
                self.assertEqual(benefits.benefit_region(org_type, org), expected)

    def test_collect_paginates_joins_and_writes_sorted_groups(self):
        central = {**SERVICE, "소관기관유형": "중앙행정기관", "소관기관명": "보건복지부", "신청기한": "상시"}
        central_rows = [{**central, "서비스ID": f"CENTRAL-{i}", "서비스명": f"혜택 {i:02}"} for i in range(49)]
        central_rows.reverse()
        expired = {**SERVICE, "서비스ID": "EXPIRED", "신청기한": "2026-11-24"}
        corp_only = {**SERVICE, "서비스ID": "CORP", "사용자구분": "법인"}
        pages = [
            {"data": [SERVICE, expired], "page": 1, "matchCount": 52},
            {"data": central_rows + [corp_only], "page": 2, "matchCount": 52},
            {"data": [{"서비스ID": "CENTRAL-1", "JA0320": "Y"}], "page": 1, "matchCount": 2},
            {"data": [CONDITIONS], "page": 2, "matchCount": 2},
        ]
        with TemporaryDirectory() as temporary:
            with patch.object(benefits, "get_key", return_value=KEY):
                with patch.object(benefits, "http_get_json", side_effect=pages) as get:
                    self.assertEqual(benefits.collect(temporary, TODAY), 50)
            directory = Path(temporary) / "benefits"
            self.assertEqual(_read(directory / "서울특별시.json")[0]["cond"]["ageMin"], 19)
            nationwide = _read(directory / "전국.json")
            self.assertEqual([item["id"] for item in nationwide[:2]], ["CENTRAL-0", "CENTRAL-1"])
            self.assertEqual(nationwide[1]["cond"]["need"], ["대학생"])
            index = _read(directory / "index.json")
            self.assertEqual((len(index), index["전국"], index["서울특별시"], index["경기도"]), (17, 49, 1, 0))  # 광주·전남이 전남광주통합특별시로 합쳐짐
            self.assertEqual(_read(directory / "경기도.json"), [])
        self.assertEqual([(args[0].split("/")[-1], args[1]["page"], args[1]["perPage"])
                          for args, _ in get.call_args_list], [
            ("serviceList", 1, 500), ("serviceList", 2, 500),
            ("supportConditions", 1, 500), ("supportConditions", 2, 500),
        ])

    def test_publish_failure_rolls_back_replaced_region(self):
        replace = os.replace
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            national = directory / "전국.json"
            local = directory / "서울특별시.json"
            common.atomic_write_json(national, ["previous"])

            def fail_local(source, target):
                if target == local:
                    raise OSError("simulated failure")
                replace(source, target)

            with patch.object(benefits.os, "replace", side_effect=fail_local):
                with self.assertRaisesRegex(OSError, "simulated failure"):
                    benefits._write_regions(directory, {"전국": ["new"], "서울특별시": ["new"]})
            self.assertEqual(_read(national), ["previous"])
            self.assertFalse(local.exists())
            self.assertFalse((directory / "index.json").exists())


class EventTests(unittest.TestCase):
    def test_free_detection_and_mapping(self):
        for price, expected in {"전석 무료": True, "무료 (유료석 9,800원)": False, "무료 / 1만 원": False,
                                "무료 0원": False, "무료 (만 8세 이상)": True, "가격 미정": False}.items():
            with self.subTest(price=price):
                self.assertEqual(events.is_free(price), expected)
        price = "무료" + " " * 60 + "5000원"
        item = events.map_event(EVENT, {"price": price, "placeUrl": "https://venue.invalid/"})
        self.assertEqual((item["id"], item["start"], item["end"], item["sido"], item["sigungu"]),
                         ("001", "2026-11-25", "2026-12-01", "서울특별시", "종로구"))
        self.assertEqual((item["realm"], item["emoji"], item["free"]), ("음악/콘서트", "🎵", False))
        self.assertEqual(len(item["price"]), 60)
        self.assertIsNone(item["ticketOpen"])
        self.assertEqual(item["url"], "https://venue.invalid/")
        self.assertEqual(item["image"], "https://images.invalid/poster.jpg")
        self.assertEqual(events.map_event({**EVENT, "thumbnail": ""}, {"thumbnail": "http://ignored.invalid"})["image"], "")
        self.assertEqual(events.map_event(EVENT, {})["url"], events.CULTURE_HOME)

    def test_detail_keeps_time_address_and_short_plain_description(self):
        item = events.map_event(EVENT, {
            "contents1": "<p>시작 시각: 19:00</p><p>전시 &amp; 공연</p>" + "소개 " * 100,
            "placeAddr": " 서울특별시 종로구 세종대로 175 ",
        })
        self.assertEqual(item["time"], "19:00")
        self.assertEqual(item["placeAddr"], "서울특별시 종로구 세종대로 175")
        self.assertTrue(item["description"].startswith("시작 시각: 19:00 전시 & 공연"))
        self.assertLessEqual(len(item["description"]), 180)
        self.assertNotIn("time", events.map_event(EVENT, {}))

    def test_entry_from_price_description_and_url(self):
        cases = [
            ({"price": "무료, 선착순 예약"}, "예약 필요"),
            ({"contents1": "누구나 참여 가능, 사전 접수"}, "예약 필요"),
            ({"contents1": "신청 필요"}, "예약 필요"),
            ({"url": "https://event.invalid/%EC%98%88%EC%95%BD"}, "예약 필요"),
            ({"contents1": "사전 신청 없이 자유 관람"}, "자유 입장"),
            ({"price": "무료, 현장 입장"}, "자유 입장"),
            ({"contents1": "누구나 참여"}, "자유 입장"),
            ({"price": "무료"}, ""),
            ({"contents1": "예약 불가"}, ""),
        ]
        for detail, expected in cases:
            with self.subTest(detail=detail):
                self.assertEqual(events.map_event(EVENT, detail)["entry"], expected)

    def test_application_deadline_requires_application_context(self):
        cases = {
            "사전 신청 마감일: 2026년 12월 3일": "2026-12-03",
            "접수 기간: 2026.11.25. ~ 2026.12.01.": "2026-12-01",
            "예약: 2026-12-02 (수) 18:00까지": "2026-12-02",
            "2026/12/03 (목)까지 신청": "2026-12-03",
            "무료 (신청 마감 2026.12.3.)": "2026-12-03",
            "전시 기간: 2026.11.25~2026.12.01": None,
            "자유 관람 2026-12-03까지": None,
            "신청: 2026-11-25부터": None,
            "신청 기간: 2026-11-25 ~": None,
            "신청 마감: 2026-02-30": None,
            "신청 마감: 12월 3일": None,
            "접수 마감: 2026-12-02\n현장 신청 마감: 2026-12-03": None,
        }
        for copy, expected in cases.items():
            with self.subTest(copy=copy):
                self.assertEqual(events.map_event(EVENT, {"contents1": copy})["applyEnd"], expected)
        self.assertEqual(events.map_event(EVENT, {"price": "무료 (신청 기한: 2026.12.3)"})["applyEnd"], "2026-12-03")
        detail = {"url": "https://event.invalid/?%EC%8B%A0%EC%B2%AD%EB%A7%88%EA%B0%90=2026-12-03"}
        self.assertEqual(events.map_event(EVENT, detail)["applyEnd"], "2026-12-03")

    def test_sigungu_only(self):
        cases = [
            ("서울", "  서울특별시 강남구  ", "강남구"),
            ("서울", "서울시/종로구", "종로구"),
            ("서울", "서울특별시", ""),
            ("서울", " 강남구 ", "강남구"),
            ("경기", "경기도 수원시  영통구 이의동", "수원시 영통구"),
            ("경기", "경기도성남시", "성남시"),
            ("경기", "광주시", "광주시"),
        ]
        for area, sigungu, expected in cases:
            with self.subTest(sigungu=sigungu):
                self.assertEqual(events.map_event({**EVENT, "area": area, "sigungu": sigungu}, {})["sigungu"], expected)

    def test_collect_reads_xml_pages_and_details(self):
        def open_fixture(url, timeout):
            endpoint = urlsplit(url).path.rsplit("/", 1)[-1]
            query = parse_qs(urlsplit(url).query)
            self.assertEqual(query["serviceKey"], [KEY])
            if endpoint == "detail2":
                seq = query["seq"][0]
                return BytesIO(_culture_xml(f"<item><seq>{seq}</seq><price>무료</price>"
                                            "<url>https://event.invalid/</url></item>"))
            self.assertEqual(endpoint, "period2")
            self.assertEqual((query["from"], query["to"], query["numOfrows"]), (["20261125"], ["20270109"], ["100"]))
            page = int(query["PageNo"][0])
            rows = []
            for number in (range(6, 12) if page == 1 else range(1, 6)):
                start = f"202611{24 if number == 11 else 25}"
                fields = {**EVENT, "seq": str(number), "title": f"공연 {number:02}", "startDate": start, "endDate": start}
                rows.append("<item>" + "".join(f"<{k}>{v}</{k}>" for k, v in fields.items()) + "</item>")
            return BytesIO(_culture_xml("".join(rows), f"<totalCount>11</totalCount><PageNo>{page}</PageNo>"))

        with TemporaryDirectory() as temporary:
            with patch.object(events, "get_key", return_value=KEY):
                with patch.object(common, "urlopen", side_effect=open_fixture) as opening:
                    self.assertEqual(events.collect(temporary, TODAY), 10)
            items = _read(Path(temporary) / "events.json")
            self.assertEqual([item["id"] for item in items], [str(i) for i in range(1, 11)])
            self.assertTrue(all(item["free"] and item["url"] == "https://event.invalid/" for item in items))
            self.assertEqual(opening.call_count, 13)

    def test_period_caps_at_3000(self):
        def request(endpoint, params):
            page = params["PageNo"]
            return {"totalCount": 4000, "PageNo": page}, [{"seq": n} for n in range((page - 1) * 100, page * 100)]

        with patch.object(events, "_request", side_effect=request) as get:
            rows = list(events.period_rows(KEY, TODAY))
        self.assertEqual((len(rows), rows[-1]["seq"], get.call_count), (3000, 2999, 30))


class SeoulReservationTests(unittest.TestCase):
    def test_mapping(self):
        self.assertEqual(seoul_reserve.map_event(RESERVATION, TODAY), {
            "id": "seoul-S001", "title": "어린이 공예", "host": "서울공예박물관", "venue": "교육실",
            "sido": "서울특별시", "sigungu": "종로구", "start": "2026-12-01", "end": "2026-12-02",
            "free": True, "price": "무료", "entry": "예약 필요", "ticketOpen": None,
            "applyStart": "2026-11-20", "applyEnd": "2026-11-25", "applyEndTime": "17:30",
            "status": "접수중", "target": "초등 1~3학년", "realm": "교육체험", "emoji": "🧩",
            "image": "https://images.invalid/poster.jpg", "url": "https://yeyak.seoul.go.kr/reservation",
            "source": "seoul",
        })

    def test_free_status_and_receipt_window(self):
        accepted = [
            {"SVCSTATNM": "안내중"},
            {"SVCSTATNM": "안내중", "RCPTBGNDT": "2026-12-25", "RCPTENDDT": ""},
        ]
        rejected = [
            {"PAYATNM": "유료"}, {"SVCSTATNM": "예약마감"}, {"SVCSTATNM": "접수종료"},
            {"RCPTENDDT": "2026-11-24 23:59:00"},
            {"SVCSTATNM": "안내중", "RCPTBGNDT": "2026-12-26", "RCPTENDDT": ""},
            {"SVCSTATNM": "안내중", "RCPTBGNDT": "2026-11-24", "RCPTENDDT": ""},
        ]
        for changes in accepted:
            with self.subTest(changes=changes):
                self.assertIsNotNone(seoul_reserve.map_event({**RESERVATION, **changes}, TODAY))
        for changes in rejected:
            with self.subTest(changes=changes):
                self.assertIsNone(seoul_reserve.map_event({**RESERVATION, **changes}, TODAY))

    def test_dates_and_optional_time(self):
        item = seoul_reserve.map_event({**RESERVATION, "RCPTENDDT": "2026-11-26", "SVCOPNBGNDT": "20261201"}, TODAY)
        self.assertEqual((item["applyEnd"], item["applyEndTime"], item["start"]), ("2026-11-26", None, "2026-12-01"))
        self.assertIsNone(seoul_reserve.map_event({**RESERVATION, "RCPTENDDT": "2026-11-31 17:30:00"}, TODAY))
        self.assertIsNone(seoul_reserve.map_event({**RESERVATION, "SVCOPNENDDT": "미정"}, TODAY))

    def test_sample_collects_both_services_and_deduplicates_in_deadline_order(self):
        culture, education = seoul_reserve.SERVICES
        fixtures = {
            culture: [RESERVATION, {**RESERVATION, "SVCID": "S002", "RCPTENDDT": "2026-11-27"}],
            education: [
                {**RESERVATION, "SVCID": "duplicate", "PLACENM": "서울공예박물관 > 교육실"},
                {**RESERVATION, "SVCID": "other-host", "SVCNM": "[다른 기관] 어린이 공예"},
                {**RESERVATION, "SVCID": "other-venue", "PLACENM": "다른 교육실"},
                {**RESERVATION, "SVCID": "earlier-start", "SVCNM": "가족 체험", "SVCOPNBGNDT": "2026-11-28"},
            ],
        }

        def open_fixture(url, timeout):
            key, output, service, first, last = urlsplit(url).path.strip("/").split("/")
            self.assertEqual((key, output, first, last), ("sample", "json", "1", "5"))
            self.assertEqual(urlsplit(url).query, "")
            response = {service: {"list_total_count": 100, "RESULT": {"CODE": "INFO-000"}, "row": fixtures[service]}}
            return BytesIO(json.dumps(response).encode("utf-8"))

        with TemporaryDirectory() as temporary, patch.object(seoul_reserve, "get_key", side_effect=RuntimeError):
            with patch.object(seoul_reserve, "log") as log, patch.object(common, "urlopen", side_effect=open_fixture) as get:
                self.assertEqual(seoul_reserve.collect(temporary, TODAY), 5)
            rows = _read(Path(temporary) / seoul_reserve.OUTPUT_FILE)
            self.assertEqual([row["id"] for row in rows], [
                "seoul-earlier-start", "seoul-S001", "seoul-other-host", "seoul-other-venue", "seoul-S002",
            ])
        self.assertEqual(get.call_count, 2)
        log.assert_called_once_with("seoul: sample key mode")

    def test_configured_key_reads_multiple_pages(self):
        rows = [{**RESERVATION, "SVCID": str(i), "SVCNM": f"행사 {i}"} for i in range(1001)]
        culture, education = seoul_reserve.SERVICES
        pages = [(culture, 1, 1000), (culture, 1001, 1001), (education, 1, 1000)]
        responses = [(1001, rows[:1000]), (1001, rows[1000:]), (0, [])]
        with TemporaryDirectory() as temporary, patch.object(seoul_reserve, "get_key", return_value=KEY):
            with patch.object(seoul_reserve, "log") as log, patch.object(seoul_reserve, "_page", side_effect=responses) as get:
                self.assertEqual(seoul_reserve.collect(temporary, TODAY), 1001)
            self.assertEqual(len(_read(Path(temporary) / seoul_reserve.OUTPUT_FILE)), 1001)
        self.assertEqual([call.args for call in get.call_args_list], [(KEY, *page) for page in pages])
        log.assert_called_once_with("seoul: configured key mode")

    def test_configured_key_low_count_preserves_the_previous_file(self):
        with TemporaryDirectory() as temporary, patch.object(seoul_reserve, "get_key", return_value=KEY):
            path = Path(temporary) / seoul_reserve.OUTPUT_FILE
            common.atomic_write_json(path, [{"id": "previous"}])
            with patch.object(seoul_reserve, "log"), patch.object(seoul_reserve, "_rows", return_value=[RESERVATION]):
                with self.assertRaisesRegex(RuntimeError, "expected at least 20"):
                    seoul_reserve.collect(temporary, TODAY)
            self.assertEqual(_read(path), [{"id": "previous"}])

    def test_request_error_omits_the_key_and_url(self):
        service = seoul_reserve.SERVICES[0]
        with patch.object(seoul_reserve, "http_get_json", side_effect=RuntimeError(f"secret URL {KEY}")):
            with self.assertRaises(RuntimeError) as error:
                seoul_reserve._page(KEY, service, 1, 1000)
        self.assertEqual(str(error.exception), f"{service}: request failed at row 1")


class RunnerTests(unittest.TestCase):
    def test_empty_source_data_retains_previous_files(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root / "benefits" / "전국.json", root / "events.json", root / seoul_reserve.OUTPUT_FILE, root / "meta.json"]
            for path in paths:
                common.atomic_write_json(path, [{"id": "previous"}])
            old = [path.read_bytes() for path in paths]
            with patch.dict(os.environ, {common.KEY_NAME: KEY}), patch.object(run_all, "log") as log:
                with patch.object(benefits, "http_get_json", return_value={"data": [], "matchCount": 0}):
                    with patch.object(events, "_request", return_value=({"totalCount": 0}, [])), \
                            patch.object(seoul_reserve, "collect", side_effect=RuntimeError("failure")):
                        self.assertEqual(run_all.main(root), 1)
            self.assertEqual([path.read_bytes() for path in paths], old)
            self.assertEqual(log.call_count, 3)

    def test_partial_success_keeps_previous_count_and_updates_metadata(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            common.atomic_write_json(root / "benefits" / "index.json", {"전국": 51, "서울특별시": 2})
            with patch.object(run_all, "log"), patch.object(benefits, "collect", side_effect=RuntimeError("failure")):
                with patch.object(events, "collect", return_value=12) as collect_events, \
                        patch.object(seoul_reserve, "collect", return_value=25):
                    self.assertEqual(run_all.main(root), 1)
            collect_events.assert_called_once()
            meta = _read(root / "meta.json")
            self.assertTrue(meta["updated"].endswith("+09:00"))
            self.assertEqual(meta["sources"], {"benefits": {"count": 53, "ok": False},
                                               "events": {"count": 12, "ok": True},
                                               "seoul": {"count": 25, "ok": True}})

    def test_seoul_failure_reports_previous_seoul_count(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            common.atomic_write_json(root / seoul_reserve.OUTPUT_FILE, [{"id": "previous"}])
            with (patch.object(run_all, "log"), patch.object(benefits, "collect", return_value=10),
                  patch.object(events, "collect", return_value=12),
                  patch.object(seoul_reserve, "collect", side_effect=RuntimeError("failure"))):
                self.assertEqual(run_all.main(root), 1)
            self.assertEqual(_read(root / "meta.json")["sources"]["seoul"], {"count": 1, "ok": False})


if __name__ == "__main__":
    unittest.main()

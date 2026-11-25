import json
import os
import unittest
from datetime import date
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from collect import benefits, common, events, run_all


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


class RunnerTests(unittest.TestCase):
    def test_empty_source_data_retains_previous_files(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root / "benefits" / "전국.json", root / "events.json", root / "meta.json"]
            for path in paths:
                common.atomic_write_json(path, [{"id": "previous"}])
            old = [path.read_bytes() for path in paths]
            with patch.dict(os.environ, {common.KEY_NAME: KEY}), patch.object(run_all, "log") as log:
                with patch.object(benefits, "http_get_json", return_value={"data": [], "matchCount": 0}):
                    with patch.object(events, "_request", return_value=({"totalCount": 0}, [])):
                        self.assertEqual(run_all.main(root), 1)
            self.assertEqual([path.read_bytes() for path in paths], old)
            self.assertEqual(log.call_count, 2)

    def test_partial_success_keeps_previous_count_and_updates_metadata(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            common.atomic_write_json(root / "benefits" / "index.json", {"전국": 51, "서울특별시": 2})
            with patch.object(run_all, "log"), patch.object(benefits, "collect", side_effect=RuntimeError("failure")):
                with patch.object(events, "collect", return_value=12) as collect_events:
                    self.assertEqual(run_all.main(root), 1)
            collect_events.assert_called_once()
            meta = _read(root / "meta.json")
            self.assertTrue(meta["updated"].endswith("+09:00"))
            self.assertEqual(meta["sources"], {"benefits": {"count": 53, "ok": False},
                                               "events": {"count": 12, "ok": True}})


if __name__ == "__main__":
    unittest.main()

# Collector task (for the implementing AI)

Read ../SPEC.md first. Write Python 3.10+ collectors using only the standard library (urllib, json, os, datetime, concurrent.futures OK).
API docs are in collect/samples/: gov24_swagger.json (보조금24 = 행정안전부_대한민국 공공서비스(혜택) 정보) and culture_swagger.json
(한국문화정보원_한눈에보는문화정보조회서비스). The key is NOT active yet, so real samples are not available; work from the swagger schemas
and write tests with small hand-made fixtures that follow those schemas.

## Key
Read env var DATA_GO_KR_KEY. On Windows, if missing in os.environ, read HKCU\Environment DATA_GO_KR_KEY via winreg (import inside try).
Never print, log or write the key. Replace the key with *** in any error text before logging.

## Files to create
- collect/common.py: get_key(), http_get_json(url, params, retries=3, backoff) supporting JSON (gov24) and XML or JSON (culture: send
  `_type=json` if supported by the swagger, otherwise parse XML with xml.etree), atomic_write_json(path, obj) (write tmp then os.replace),
  KST helpers, log(msg) -> collect/last_run.log (append, keep last 300 lines).
- collect/benefits.py: page through /gov24/v3/serviceList (perPage=500) and /gov24/v3/supportConditions (perPage=500), join on 서비스ID.
  Keep only items whose 사용자구분 includes 개인 or 가구. Map to the SPEC benefits schema:
  id=서비스ID, name=서비스명, org=소관기관명, summary=서비스목적요약 (trim 120 chars), target=지원대상 (trim 160), amount=지원내용 (trim 120),
  how=신청방법 (trim 120), url=상세조회URL, deadline: parse 신청기한 if it contains a clear YYYY.MM.DD / YYYY-MM-DD end date, else null,
  deadlineText=신청기한 raw (trim 60), field=서비스분야, emoji from a fixed map of 서비스분야 (e.g. 생활안정 💰, 주거·자립 🏠, 보육·교육 🎒,
  고용·창업 💼, 보건·의료 🏥, 행정·안전 🏛️, 임신·출산 🍼, 보호·돌봄 🤝, 문화·환경 🎨, 농림축산어업 🌾, default 📌),
  updated=수정일시, cond: ageMin/ageMax from JA0110/JA0111 (ints, null if missing or 0..0 meaning none), income: list of codes JA0201..JA0205
  that are "Y", flags: list of names for JA0326 근로자/직장인, JA0327 구직자/실업자, JA0320 대학생, JA0404 1인가구, JA0412 무주택세대,
  JA0411 다자녀가구, JA0403 한부모가정, JA0302 임산부, JA0303 출산/입양, JA0328 장애인, JA0329 국가보훈대상자 that are "Y".
  Region: 소관기관유형 / 소관기관명 tell central vs local. Central (중앙행정기관 or 공공기관 etc, not a local government) -> data/benefits/전국.json.
  Local government -> data/benefits/<시도 full name>.json (17 시도: 서울특별시 … 제주특별자치도, 강원특별자치도, 전북특별자치도), and set
  item.sigungu to the 시군구 name when 소관기관명 contains one (e.g. "서울특별시 강남구" -> 강남구), else "".
  Sort each file: items with deadline soonest first, then by name. Also write data/benefits/index.json {sido: count}.
  Drop items whose deadline is in the past.
- collect/events.py: call /period2 for today..today+45 days (paginate, numOfrows=100, cap 3000 items), then /detail2 for each seq with a
  ThreadPoolExecutor(max_workers=6) to get price and homepage url. Map to SPEC events schema: id=seq, title, venue=place, sido from area
  (normalize short names like 서울 -> 서울특별시), sigungu, start/end as YYYY-MM-DD, realm=realmName, emoji by realm (연극 🎭, 음악/콘서트 🎵,
  국악 🪕, 무용 🩰, 전시 🖼️, 뮤지컬/오페라 🎶, 아동/가족 🧸, 행사/축제 🎪, 교육/체험 🧩, default 🎟️), price (trim 60), free = price text
  contains 무료 and no digit-won amount, ticketOpen=null (this API has no ticket-open time), url = detail url or homepage or
  https://www.culture.go.kr . Write data/events.json sorted by start date. Drop ended events.
- collect/run_all.py: run benefits then events; each in try/except so one failing does not stop the other; on success update
  data/meta.json {updated, sources:{benefits:{count, ok}, events:{count, ok}}}. Exit code 1 if either failed. If a collector fails,
  keep the previous data file untouched (never write an empty list over good data; treat < 50 benefits or < 10 events as failure).
- collect/test_collect.py: unittest with fixtures (no network) covering mapping, region split, deadline parse, free detection, empty-data guard.

## App change (small)
app.js currently loads data/benefits.json. Change it to load data/benefits/전국.json plus data/benefits/<profile.sido>.json when the
profile has a sido, merge, and filter by sigungu (keep items with empty sigungu or matching profile.sigungu). Matching rules for cond:
age outside ageMin..ageMax hides the item only when birthYear is known; other conds never hide, they only add a small muted
"조건 확인 필요" note. Keep the existing sample-data label logic. Update sw.js jsonFiles / network-first rule so data/benefits/*.json is
network-first. Do not restyle anything else.

Do not touch SPEC.md, 진행상황.md, data/taxes.json, data/tips.json, .git. Do not commit. Run the unit tests and report results.

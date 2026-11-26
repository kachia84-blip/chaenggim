# Task 6 — Seoul public-service reservations (free, open for application, with deadlines)

Source: Seoul Open Data "공공서비스예약" API. URL pattern: http://openapi.seoul.go.kr:8088/{KEY}/json/{SERVICE}/{start}/{end}/
Services: ListPublicReservationCulture (문화행사, ~870 rows), ListPublicReservationEducation (교육·체험, ~280 rows). Max 1000 rows per call.
KEY: env var SEOUL_API_KEY (Windows: also HKCU\Environment via winreg like common.get_key). If missing, use the public key "sample"
(returns only 5 rows) so tests/dev still work; log which key mode was used (never print the key).
Row fields: SVCID, SVCNM, SVCSTATNM (접수중/안내중/접수종료/예약마감 ...), PAYATNM (무료/유료), AREANM (구), PLACENM, RCPTBGNDT, RCPTENDDT,
SVCOPNBGNDT, SVCOPNENDDT, USETGTINFO (대상), MINCLASSNM (분류), IMGURL, SVCURL, TELNO, X, Y, DTLCONT (HTML detail, ignore).

## collect/seoul_reserve.py
- Fetch both services fully (paginate by 1000). Keep rows with PAYATNM == 무료 and SVCSTATNM in (접수중, 안내중) and receipt end ≥ today
  (or, for 안내중, receipt start within 30 days). Map to the events schema used by data/events.json plus extra fields:
  id "seoul-"+SVCID, title SVCNM (strip [..] prefix into "host" field), venue PLACENM (last part after '>'), sido 서울특별시,
  sigungu AREANM, start/end from SVCOPNBGNDT/SVCOPNENDDT (YYYY-MM-DD), free true, price "무료", entry "예약 필요",
  applyStart/applyEnd (YYYY-MM-DD) and applyEndTime ("17:30") from RCPT*, status SVCSTATNM, target USETGTINFO trimmed,
  realm MINCLASSNM, emoji by realm (교육체험 🧩, 전시/관람 🖼️, 공연 🎵, 자연/과학 🌿, 문화행사 🎪, default 🎟️), image IMGURL (https),
  url SVCURL, source "seoul". Deduplicate same SVCNM+venue+applyEnd.
- Write data/seoul_events.json (separate file, sorted by applyEnd then start). Treat < 20 rows as failure when a real key is used
  (keep previous file); with the sample key, write what you get. Hook into collect/run_all.py as a third independent step and meta.json
  sources.seoul {count, ok}.
- Tests with fixtures: mapping, status filter, dedupe, date parsing.

## app.js
- Load data/seoul_events.json too (allow missing) and merge into the home "이번 주 무료 행사" list. Home rule update:
  show items whose application is open now (applyEnd ≥ today) OR the event happens this week. Group: first a section
  "신청 마감 임박" (applyEnd within 7 days, sorted by applyEnd, right side "신청 D-n", n=0 → "오늘 마감"), then the existing day groups.
  Rows show target (USETGTINFO) in the muted line when it is not 제한없음 (e.g. "가족", "초등 1~3학년").
  Location: profile.sigungu first, then rest of 서울 (label 구), as now.
- 공연 tab: include seoul events, filter chip "신청 가능" (applyEnd ≥ today).
- sw.js: add data/seoul_events.json (network-first), bump cache.
Do not touch SPEC.md, 진행상황.md, other data files, .git. Do not commit. Run tests + node --check.
Reply in under 10 lines.

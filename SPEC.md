# 챙김 — spec (shared by every module)

Korean mobile PWA for one person living in Korea. Every day it shows "what to take care of this week":
benefits I can receive, tax deadlines, free concerts/events and ticket-open dates, plus one daily life tip.
All UI text is Korean. Hosted on GitHub Pages (static). Data is refreshed by a GitHub Actions job later.

## Design direction (chosen mockup: "A. bill style")
- Character: meticulous, kind, one step ahead. World: a paper bill in the mailbox and a wall calendar.
- Neutrals: warm paper gray. Background #F7F6F3, surface #FFFFFF, text #1F1E1C / #5F5E5A / #8A8984, hairline rgba(31,30,28,.08).
- One accent: deep ink navy #1F4E8C (D-day numbers, selected tab, primary action only). Dark mode: bg #161615, surface #1F1F1E, accent #8DB4E8.
- Signature: perforation line = `border-top: 1px dashed` between items inside a card. Use it for every divider, nothing else.
- Bright moment: the D-day number (large, tabular-nums, accent) on the top card of "오늘".
- Font: Pretendard (subset file added later at fonts/; use font-family "Pretendard", system-ui fallback). Icons: emoji characters only
  (rendered with Tossface subset later). No other icon sets. No gradients, glows, shadows except a tiny neutral one on the bottom tab bar.
- Weights 400/500 only (600 rarely). Sentence-style Korean, no exclamation marks. 4px spacing grid. Radius: cards 14, controls 10.
- Motion: color/opacity transitions 150ms only. Respect prefers-reduced-motion. No looping animation (battery).

## Tabs (bottom tab bar, 4 tabs)
1. 오늘: date line, "이번 주 챙길 것 N가지" card (merge of: benefits with deadline ≤ 14 days, taxes in period or starting ≤ 14 days,
   events with ticket_open or apply_open ≤ 7 days, sorted by D-day), then "오늘의 생활정보" card (one tip, rotates by day-of-year).
2. 지원금: list from data/benefits.json filtered by profile. Each row: emoji, name, amount line, deadline D-day, org. Tap → detail sheet
   (summary, target, how to apply, official link). Top: "내 조건 바꾸기" link to profile sheet. Empty profile → short invitation to set it.
3. 세금: month strip calendar (12 months, current highlighted) + list of data/taxes.json items for the year, upcoming first.
   Each item: emoji, title, period "12월 16일~31일", D-day or "진행 중", who it's for, tip. Tap → detail (how, tip, link).
4. 공연: data/events.json. Filter chips: 전체 · 무료 · 티켓 오픈 · 내 지역. Row: emoji, title, venue, date range, price ("무료" pill),
   ticket_open with D-day/time if present. Tap → link out to the official page (no in-app booking, no automation).

## Profile (localStorage key "chaenggim.profile", never sent anywhere)
{ "birthYear": 1990, "sido": "서울특별시", "sigungu": "강남구", "household": "1인|부부|자녀있음|부모님과",
  "homeless": true, "incomeBand": "모름|중위50이하|중위100이하|중위150이하|그이상", "car": true, "worker": "직장인|자영업|프리랜서|없음" }
Profile sheet = 3 short steps (나이·지역 / 가구·집 / 일·차). Taxes with `who` not matching (e.g. car taxes when car=false) are hidden.

## Data files (all UTF-8 JSON, arrays unless noted)
data/meta.json  { "updated": "2026-11-25T06:00:00+09:00", "sources": {"benefits": "...", "events": "..."} }

data/taxes.json — recurring yearly items, dates as MM-DD (end may be next year → "endNextYear": true)
{ "id": "car-tax-2", "emoji": "🚗", "title": "자동차세 2기분", "start": "12-16", "end": "12-31",
  "who": "car|all|worker|owner|business", "what": "...", "how": "...", "tip": "...", "link": "https://www.wetax.go.kr" }

data/tips.json — daily tips
{ "id": "t001", "emoji": "💡", "category": "세금|지원금|생활요금|교통|주거|건강|소비", "title": "...", "body": "2~3 short sentences",
  "link": "official source url" }

data/benefits.json — from 보조금24 API (collector, needs data.go.kr key)
{ "id": "...", "emoji": "🏠", "name": "...", "org": "...", "summary": "...", "target": "...", "amount": "월 20만 원, 최대 12개월",
  "deadline": "2026-11-30" | null (상시), "how": "...", "url": "...",
  "cond": { "ageMin": 19, "ageMax": 34, "sido": ["서울특별시"] | [], "sigungu": [] , "homeless": true|null, "household": [] , "incomeMax": "중위150이하"|null } }
Matching rule: a condition that is null/empty does not filter. Unknown profile values never hide an item.

data/events.json — from 문화 공연 API (collector)
{ "id": "...", "emoji": "🎻", "title": "...", "venue": "...", "sido": "서울특별시", "start": "2026-12-20", "end": "2026-12-20",
  "free": true, "price": "무료" , "ticketOpen": "2026-12-02T10:00:00+09:00" | null, "url": "..." }

## Files
index.html, style.css, app.js (vanilla JS, no framework, no build), sw.js (cache app shell + data, network-first for data/*.json),
manifest.json (name 챙김, theme #F7F6F3), icons/. Until real collectors run, data/benefits.json and data/events.json
hold a few items with "sample": true — the UI shows a small muted "예시 데이터" label on those rows.

## Quality bar
- Mobile first (360–430px), works at desktop width (max content 480px centered).
- All dates computed in Asia/Seoul. D-day: "D-3", "오늘 마감", "진행 중", past items hidden.
- Text ≥ 12px, tap targets ≥ 44px, focus-visible ring, aria labels for emoji-only buttons.

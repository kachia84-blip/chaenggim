# Task 8 — event search, event detail sheet (calendar, saved, share), saved events on home

Read SPEC.md first (design rules: paper neutrals, one navy accent, dashed dividers, weights 400/500, no new icon sets,
no exclamation marks, sentence-style Korean). Write all UI text in Korean.
Edit only app.js, style.css, sw.js. Do not touch data/, collect/, SPEC.md, 진행상황.md, .git. Do not commit.
Keep every existing behaviour not mentioned here. Change only the lines these features need; do not reformat or
"improve" neighbouring code. Do not add new emoji anywhere (text-only buttons).

## 1. Search on the 공연 tab (`renderEvents`)
- Module variable `let eventQuery = "";`.
- A search field placed between `pageHead("공연")` and the condition chip row, built exactly like the benefit search
  (`inputField("행사 검색", "event-search", eventQuery, { id: "event-search", type: "search", placeholder: "행사 이름, 장소" })`).
- Match: lowercase, split on whitespace, every term must be contained in
  `[item.title, item.venue, item.host, item.placeAddr, item.realm, item.sigungu].join(" ")`.
  Query is applied together with row-1 filter AND region AND category, and BEFORE counting, so category chip counts
  reflect the query.
- Typing must not re-render the whole page (the input would lose focus/IME composition). Refactor so the category chip
  row and the results block are produced by one helper (e.g. `eventResults(events, today, now)` returning
  `[categoriesNode, resultsNode]`), wrapped in a container, and on `input` replace only that container's children
  (same approach as `renderBenefits` + `benefitResults`). Category chip clicks may still call `render({ focusFilter })`.
- Empty state with a non-empty query: "검색 결과가 없어요" (keep the existing "조건 초기화" button; it must also clear
  `eventQuery`).
- Every place that sets `eventFilter`/`eventCategory` before navigating to #events (home links) also resets `eventQuery = ""`.

## 2. Event detail sheet
Today event rows (`eventRow` on the 공연 tab and `homeEventRow` on home) are links straight to `item.url`
(via `rowControl(item, ...)`, which makes a link when there is no `item.open`). Change both so tapping opens a sheet:
pass `{ open: () => openEvent(item) }` to `rowControl` instead of `item` (keep the same classes and content).
Give each row control a stable id (`"event-" + item.id`, sanitised to [A-Za-z0-9_-]) so focus returns after the
sheet closes (the sheet close handler already looks up `sheetOpener.id`).

`openEvent(item)` uses `showSheet(title, context, ...body)`:
- Title: `el("span", "detail-title", emoji(item.emoji), item.title)` (like `showDetail`).
- Context: `sampleLabel(item)` (may be null).
- A `<dl>` with `.sheet-section` rows, skipping empty ones, in this order:
  기간 (`periodLabel(item.startDay, item.endDay)`), 장소 (venue, then placeAddr on a new line if present),
  지역 (`[sido short, sigungu]` e.g. "서울 강서구"), 대상 (full `item.target`), 요금 (`item.free ? "무료" : item.price`),
  신청 (if `applyDay` is finite: "~ 12월 2일(화) 17:30 마감" using `dateLabel` and `applyEndTime`; if `applyStart`
  exists and is in the future, prefix "12월 1일부터 "), 티켓 오픈 (from `eventOpenings`), 분야 (`item.realm`), 주최 (`item.host`).
- Actions row (`.sheet-actions event-actions`), in this order:
  1. Primary link `officialLink(item.url, label, "action")` where label is "신청하러 가기" when `applyOpen(item, today)`,
     otherwise "공식 안내 보기". Omit if no valid URL.
  2. Quiet buttons (class `quiet-button sheet-button`): calendar, saved toggle, share (described below).

### 2a. Calendar ("달력에 넣기")
- If `applyOpen(item, today)` and the application deadline is in the future or today: add the DEADLINE as an all-day
  event on `applyEnd`, titled `"신청 마감 · " + item.title`; details: `마감 ${applyEndTime}` when present, venue, url.
  Button label "마감일 달력에 넣기".
- Otherwise add the EVENT itself as an all-day event from `start` to `end` (inclusive), titled `item.title`;
  details: venue, url. Button label "달력에 넣기".
- On iPhone/iPad (`/iPhone|iPad|iPod/.test(navigator.userAgent)` or Mac with touch points > 1): build an .ics
  (VCALENDAR 2.0, PRODID "-//chaenggim//KO", one VEVENT with UID `${item.id}@chaenggim`, DTSTAMP, DTSTART;VALUE=DATE,
  DTEND;VALUE=DATE exclusive next day, SUMMARY, LOCATION, DESCRIPTION, URL; for the deadline variant add a VALARM
  TRIGGER:-PT15H so it alerts at 09:00 the day before; escape `\ , ;` and newlines per RFC 5545; CRLF line ends),
  then download it via a Blob URL and a temporary `<a download="챙김.ics">` click, revoking the URL afterwards.
- Everywhere else open Google Calendar's template URL in a new tab:
  `https://calendar.google.com/calendar/render?action=TEMPLATE&text=..&dates=YYYYMMDD/YYYYMMDD&details=..&location=..&ctz=Asia/Seoul`
  (end date exclusive; build with `URLSearchParams`). On Android this opens the Google Calendar app.

### 2b. Saved events ("관심")
- localStorage key `"chaenggim.saved"`: JSON array of item ids. Read once with try/catch (fall back to empty), keep
  in a module `Set`; write back with try/catch on every change.
- Toggle button: label "관심 추가" / "관심 해제", `aria-pressed` reflects state. Toggling updates the button in place
  (no sheet re-render). Remember that something changed; when the sheet closes and the saved set changed, call
  `render()` so the home row count and lists update (focus restore still works via ids).
- 공연 tab: add a condition chip "관심 N" (key `saved`) at the end of the row-1 filters, shown only when
  N > 0 or it is selected. `eventMatches` for `saved`: `savedEvents.has(item.id)`. N counts saved ids that exist in
  `upcomingEvents(today)` (ignore region/category/query).
- Saved ids whose items no longer exist in the data are simply not shown (do not delete them from storage).

### 2c. Share ("공유")
- If `navigator.share` exists: `navigator.share({ title: item.title, text: `${item.title}\n${period} · ${venue}`, url: item.url })`,
  ignore AbortError.
- Else if `navigator.clipboard?.writeText` exists: copy the url and change the button text to "링크 복사됨" for 2 s.
- Else do not render the share button. Also skip it when the item has no valid https URL.

## 3. Home: saved row in "그 밖에 챙길 것" (`renderToday`)
- Only when at least one saved id exists in `upcomingEvents(today)`: add, as the FIRST row of that list, a button row
  (`"row quiet-row"`) with `el("span", "row-text", el("span", "row-title", "관심 행사"), meta)` and a status.
  meta: the soonest upcoming application deadline among saved items, e.g. "숲 해설 산책 신청 마감" when one exists,
  otherwise the soonest starting saved item's title + " " + dateLabel(start). status: `statusText(dDay(...))` for the
  deadline case, else `${count}건`.
- Clicking it: `eventFilter = "saved"; eventCategory = "전체"; eventRegion = ["", ""]; eventQuery = "";` then
  `location.hash = "events"` (or use `tabLink("events", ...)` like the other home links).

## 4. Styles (style.css)
- `.event-actions { flex-wrap: wrap; justify-content: flex-start; }` and let the primary `.action` sit first.
- `.sheet-button { border: 1px solid var(--hairline); }` (44px min height already from `.quiet-button`).
- Keep everything else unchanged.

## 5. Misc
- Bump sw.js cache version v16 → v17.
- Check: `node --check app.js`. Mentally test at 375 px: no horizontal overflow; sheet actions wrap.
- Do not use alert/confirm/prompt.

Report in Korean: what changed, functions added/changed, anything you could not do.

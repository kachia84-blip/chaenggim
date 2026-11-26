# Task 5 — home screen "B. 요일별 목록" (free local events first) + typography pass

User feedback (2026-11-26): (1) typography looks AI-made — keep Pretendard (project rule) but fix layout/hierarchy;
(2) the money list is generic and not useful; (3) free events and applications with deadlines must be on top.
User chose mockup B. Read SPEC.md first. All UI text Korean, short, no exclamation marks. Do not touch SPEC.md, 진행상황.md,
data/*.json files written by collectors/AIs (taxes, tips, dormant, picks, benefits, events), .git. Do not commit.

## 1. collect/events.py (data)
- From detail2 (see collect/samples/culture_swagger.json for its fields) keep extra fields when present: time text (e.g. 시작 시각),
  placeAddr, and a short description. Add "entry": "예약 필요" when price/description/url text clearly mentions 예약, 사전 신청, 사전접수,
  신청 필요, 선착순 예약; "자유 입장" when it clearly says 자유 관람, 자유 입장, 누구나, 현장 입장; otherwise "".
  Add "applyEnd" (YYYY-MM-DD) only when a clear application deadline date appears; else null.
- Make sure sigungu is the 시군구 name only (e.g. "강남구"), normalized (trim, remove 시도 prefix).
- Update tests (entry detection, applyEnd parse, sigungu normalize).

## 2. Home tab layout (mockup B), top to bottom
1. Title "이번 주 무료 행사" (19px, weight 500). Muted sub line: "<profile.sigungu or sido or 전국> · <today's date>".
2. Day chips (horizontal, wrap): "전체 N", then one chip per day that has events from today through the coming Sunday
   (label "오늘 n", "내일 n", or weekday "토 n"/"일 n"). Selecting filters the list below. Chip style: thin border, active = dark fill.
3. Event list grouped by day (section label like "토요일 12월 6일", 12px muted). Rows: 56×56 thumbnail (radius 10, lazy, neutral
   block on error), title (14px/500, max 2 lines), muted "19:00 · 장소", right side: "신청 D-n" in accent if applyEnd, else muted
   entry text ("예약 필요"/"자유 입장"), else nothing. Free events only. Location filter: profile.sigungu first; if fewer than 5 events in
   the 구, fill with events from the same 시도 and label those rows with the 구 name in the muted line. No profile → nationwide + a
   one-line prompt "내 동네를 넣으면 가까운 행사만 보여요" with a text button opening the profile sheet. Show up to 12 rows, then
   "공연 탭에서 더 보기". Multi-day exhibitions running through the week appear once, under the first day of the week range, with
   "~12.31까지" in the muted line. Tap → existing event detail/link.
4. Section label "그 밖에 챙길 것", then three quiet one-line rows (no big cards, no big numbers):
   "신청 마감 임박" → count of benefits matching the profile with deadline ≤ 14 days that pass readyToReceive (opens #benefits sorted
   by deadline); "잠자는 내 돈 5곳" with "n/5" → opens a sheet containing the existing dormant checklist; "이득 보는 제도 N가지" → #picks.
5. Keep "다가오는 세금" as one quiet row and the 생활정보 card at the bottom.
Remove the big hero number card and the TOP 5 card from home (keep #picks route and its list).

## 3. Typography pass (whole app, style.css + markup), Pretendard stays
- Type scale only: 19 (page title), 15 (sheet title), 14 (row title), 13 (body), 12 (meta/labels). Weights 400/500 only.
- letter-spacing -0.01em for ≥14px, 0 for smaller. line-height 1.45 for titles, 1.6 for body.
- Accent navy only for D-day / deadlines and the active tab; remove accent from other numbers and headings.
- Fewer pills: kind labels ("받는 돈/아끼는 돈") become muted text, not pills. Keep cards for grouped sections only; rows use dashed dividers.
- Consistent 4px spacing grid; list rows min-height 56px; page side padding 20px.

## 4. sw.js bump cache version. Run unit tests + `node --check app.js`.
Reply in under 12 lines: files changed, test result, what detail2 fields you used for entry/applyEnd, anything not done.

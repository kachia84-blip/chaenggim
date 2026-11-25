# Task 2 — make the app useful ("wow" home screen, real matching)

Read SPEC.md and collect/TASK.md first. User feedback: the app shows a raw government list with truncated text, shows benefits the user
cannot get (e.g. 통합문화이용권 is only for 기초생활수급자·차상위 but is shown to a civil servant), and has no moment that makes them say "wow".
The user chose home-screen mockup "A. 돈 먼저". All UI text in Korean (write the output UI text in Korean), short, no exclamation marks.
Keep the SPEC design rules (paper neutrals, one navy accent, dashed perforation dividers, weights 400/500, no gradients/glow/looping motion).
Do not touch SPEC.md, 진행상황.md, data/taxes.json, data/tips.json, data/dormant.json, .git. Do not commit. Run the unit tests at the end.

## 1. collect/benefits.py (data quality)
- Target-trait groups from supportConditions: personal traits = JA0301,JA0302,JA0303,JA0313-JA0320,JA0322,JA0326-JA0330;
  household traits = JA0401-JA0404,JA0410-JA0414. For each group: if every code is "Y", or the "해당사항없음" code (JA0322 / JA0410)
  is "Y", the group is NOT restricted. Otherwise cond.need = names of the "Y" codes in that group (use FLAG_NAMES-style Korean names,
  add names for the codes not mapped yet). Replace cond.flags with cond.need (list, empty = no restriction).
- cond.income: null when all five JA0201-JA0205 are "Y" or none are; otherwise the list of "Y" codes.
- New field amountWon (int or null) = best-effort yearly maximum in won parsed from 지원내용 (then 서비스명): handle "월 20만원",
  "월 최대 20만 원", "연 36만원", "최대 300만원", "1인당 10만원", "50만원 상당", 억/천만/만 units, commas. If "월" amount, multiply by the
  stated months ("최대 12개월", "12개월간") else by 12. Take the largest clearly-stated amount; null when unclear or when it is a loan/융자/대출
  /보증 (those are not received money). Add amountText (short human text like "월 20만 원 · 최대 12개월", ≤ 30 chars) or "".
- New field plain = 서비스목적요약 cleaned (remove ○ □ - bullets, \r\n, double spaces), ≤ 60 chars, ending cleanly at a word.
- New field who = first clause of 지원대상 cleaned the same way, ≤ 60 chars.
- Keep summary/target/amount/how as now. Keep file splitting by region.
- Update collect/test_collect.py: tests for the group rule, income rule, amount parsing (at least 8 cases incl. 월×개월, 억, 융자→null).

## 2. collect/events.py
- Add image = thumbnail from period2 (http:// → https://), "" if missing.

## 3. app.js — profile and matching
- Profile step 2 (가구·집) gets one more select "기초생활수급·차상위" with options 예 / 아니요 / 모름 → profile.lowIncome true/false/null.
  Keep 공무원 in the 일 options.
- A benefit is hidden only when the profile clearly contradicts it (unknown never hides):
  income restricted to only JA0201 (or JA0201+JA0202) and lowIncome === false; need includes 무주택세대 and homeless === false;
  need includes 1인가구 and household is known and not 1인; need includes 구직자/실업자 and worker is 직장인 or 공무원;
  need includes 근로자/직장인 and worker is 없음; age outside ageMin..ageMax (existing); need only contains traits like 임산부, 출산/입양,
  장애인, 국가보훈대상자, 한부모가정, 다자녀가구, 농업인, 어업인, 축산업인, 임업인 → hide unless the profile says so (profile has no such
  fields, so hide these "narrow" items from TOP 5 but keep them in the full list under a muted "조건 확인 필요" note).
- "조건 확인 필요" appears only when cond.need is non-empty and not confirmed by the profile.
- relevance(item): +3 local sigungu match, +2 same sido, +2 deadline within 30 days, +2 amountWon ≥ 1,000,000, +1 amountWon > 0,
  +2 each need trait confirmed by profile (무주택세대, 1인가구, 근로자/직장인), −4 if narrow (see above), −3 if field is 농림축산어업.
  Benefits tab sorts by relevance then deadline. Render the first 40 rows and a "더 보기" button that adds 40 more.

## 4. Home tab ("오늘") — mockup A, top to bottom
1. Hero card: muted label "내 조건으로 받을 수 있는 지원금", big accent number "연 최대 N만 원" (sum of amountWon of the TOP 5,
   formatted with 만/억, tabular-nums), sub line "K건 · 신청 안 하면 못 받아요". If no profile yet: label "내 조건을 넣으면 받을 수 있는
   돈을 계산해 드려요" and a button "내 조건 넣기" opening the profile sheet.
2. TOP 5 card (top relevance, amountWon not null preferred, narrow items excluded): row = emoji + name, right side amountText or D-day,
   second line = who or plain (muted), dashed dividers; tap → benefit detail; last line "N건 더 보기" → #benefits.
3. "잠자는 내 돈 찾기" card from data/dormant.json: header with "5곳 중 N곳 확인함"; each row has a checkbox (localStorage
   "chaenggim.dormant" = {id: "YYYY-MM-DD"}) and the title + where (muted). Tapping the row text opens a sheet with what / where / how and
   a link button "사이트 열기" (target=_blank rel=noopener). The checkbox has an aria-label.
4. "이번 주말 무료 공연": free events overlapping the coming Saturday–Sunday (if today is Sat/Sun, this weekend), in profile.sido when
   set (else nationwide), up to 3 horizontally scrollable cards: image (loading=lazy, 4:3, object-fit cover, alt = title, neutral block
   on error), title (2 lines max), muted "토 · 장소". Empty → "이번 주말 무료 공연이 아직 없어요". Link "공연 더 보기" → #events with
   the 무료 filter active.
5. A small "다가오는 세금" row (nearest upcoming tax for the profile) and the existing 오늘의 생활정보 card at the bottom.
Remove the old "이번 주 챙길 것" mixed card.

## 5. Benefit detail sheet
Sections: 무엇 (plain), 누가 (who, then target), 얼마 (amountText, then amount), 어떻게 신청 (how), 마감 (deadlineText or 상시),
condition note when relevant, primary link "정부24에서 자세히 보기" (url).

## 6. sw.js
Add data/dormant.json to the data list (network-first), bump the cache version.

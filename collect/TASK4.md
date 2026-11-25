# Task 4 — review data/picks.json, then drive the home screen from it

Context: SPEC.md, collect/TASK2.md. The home screen hero ("내 조건으로 받을 수 있는 지원금 연 최대 N만 원") and TOP 5 currently come from
9,000 government services and pick situational items (육아휴직급여, 난자 냉동, 유가족 포상금). They must come from data/picks.json instead
(curated eligibility-based items written by another AI; treat its facts as unverified).

## A. Review and fix data/picks.json (use web search on official sources: gov.kr, nts.go.kr, hometax, bokjiro, 각 기관 공식 사이트)
- Check every amount, rate, age limit and income limit against official 2026 info; fix wrong ones, set yearlyWon null when unverifiable.
- Make eligibility machine-readable in "who": ageMin/ageMax (e.g. 기초연금·어르신 items ageMin 65), "incomeCapped": true for any item
  with an income/asset limit (근로장려금, 자녀장려금, 기초연금, 청년월세, 청년내일저축, 에너지바우처, 복지할인 …) plus a short
  incomeNote, "lowIncomeOnly": true only for 수급자·차상위 items, "workers"/"excludeWorkers" (e.g. 국민내일배움카드 excludes 공무원;
  노란우산공제 is 자영업 only), "sido" for regional items, "car": true for car items, "housing": list among 자가/전세/월세 when it
  depends on housing (월세 세액공제 → ["월세"], 전세대출 공제 → ["전세"], 주담대 이자 → ["자가"]), "needsChild": true for child items.
- Remove items that are situational or not money (drop if unsure). Keep 35–50 items. Add "checkedBy": "gpt-2026-11" to each.
- Write a short collect/picks_review.md listing every change (old → new, source URL).

## B. App changes (app.js, style.css, sw.js) — keep SPEC design rules, Korean UI text, no exclamation marks
- Profile step 2: replace the 무주택 select with "집" (자가 / 전세 / 월세 / 부모님 집 / 모름) stored as profile.housing; derive
  homeless = housing in (전세, 월세, 부모님 집) for existing benefit matching; keep 기초생활수급·차상위. Step 1 or 2: add "자녀" (있음 / 없음 / 모름).
  Keep backward compatibility with saved profiles that only have homeless.
- pickStatus(item, profile): "ok" (clearly eligible), "check" (eligible only if an unknown fact holds, or incomeCapped and income unknown),
  "no" (clearly not eligible: age outside range, worker excluded/not allowed, lowIncomeOnly and lowIncome === false, sido mismatch,
  car required and car === false, housing mismatch when housing known, needsChild and child === 없음). Unknown never → "no".
- Hero: sum yearlyWon of "ok" picks only (never "check"), label "내 조건으로 챙길 수 있는 돈", big "연 약 N만 원",
  sub "받는 돈 a만 · 아끼는 돈 b만 · K가지". No profile → invitation + "내 조건 넣기" button (existing).
- TOP 5 card titled "지금 챙기면 이득": top "ok" picks by yearlyWon desc (then "check" ones if fewer than 5, with a muted
  "조건 확인 필요" note); row = emoji, title, kind pill (받는 돈/아끼는 돈), amountText; second line plain. Tap → sheet with
  plain, amountText + basis, who summary in plain Korean (age, income note, job), how, when, link "공식 안내 보기" (url).
  Last line "전체 N가지 보기" opens a full picks list (new hash route #picks, grouped 받는 돈 / 아끼는 돈, "no" items hidden,
  "check" items marked).
- Remove the government-services TOP 5 from the home screen (keep the 지원금 tab as the full searchable list; add a simple text search
  box at the top of that tab filtering by name/plain/org).
- sw.js: add data/picks.json (network-first), bump cache version.

Do not touch SPEC.md, 진행상황.md, data/taxes.json, data/tips.json, data/dormant.json, data/benefits/*, data/events.json, .git.
Do not commit. Run `python -m unittest collect.test_collect` and a JS syntax check. Reply in under 12 lines: picks kept/removed/fixed
counts, the 5 biggest corrections, files changed, test result.

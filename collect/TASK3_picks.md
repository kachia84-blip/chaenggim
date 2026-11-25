# Task 3 — data/picks.json: "누구나 챙기면 이득" (curated eligibility-based money list for South Korea, 2026)

Goal: 40–50 items of money a person in South Korea can GET or SAVE just by meeting eligibility (age, income, job type, housing,
region, car) and applying — NOT situational support (no childbirth, illness, accident, disaster, unemployment, bereavement,
military-family, disability-only, farming/fishing-only items). Mix: cash/refund benefits ("받는 돈") and legal savings / tax
deductions / discounts ("아끼는 돈"). Examples to consider (verify each, drop if not real or not current): K-패스 환급, 기후동행카드(서울),
근로장려금, 에너지캐시백, 문화누리카드, 청년월세 지원, 청년도약계좌 정부기여금, 국민내일배움카드(공무원·대기업 등 제외 조건 확인),
연금저축·IRP 세액공제, 주택청약종합저축 소득공제, 월세 세액공제, 신용카드 소득공제 전통시장·대중교통 공제율, 휴대폰 선택약정 25% 할인,
통신비 감면(저소득), 고향사랑기부제 세액공제·답례품, 자동차세 연납 할인, 지방세 카드 포인트/전자고지 할인, 건강검진 무료(국가검진),
독감 무료접종 대상, 청년 마음건강 바우처, 알뜰교통 관련, 전기요금 복지할인, 도시가스 요금 경감, 노후 대비 국민연금 추납 등.

## Schema (UTF-8 JSON array, 2-space indent) — write to data/picks.json
{
  "id": "k-pass",
  "emoji": "🚌",                       // one emoji
  "title": "K-패스 교통비 환급",         // ≤ 16 chars
  "kind": "받는 돈" | "아끼는 돈",
  "plain": "대중교통 이용액의 20~53%를 다음 달에 돌려받아요",   // ≤ 45 chars, plain Korean
  "yearlyWon": 360000,                  // conservative realistic yearly value in won for a typical eligible person; null if it cannot be estimated honestly
  "amountText": "연 최대 약 36만 원",     // ≤ 20 chars, must match yearlyWon basis
  "basis": "월 6만 원 사용 × 20% × 12개월 가정",   // how yearlyWon was estimated, ≤ 50 chars
  "who": { "ageMin": null, "ageMax": null, "lowIncomeOnly": false, "incomeNote": "",
           "workers": [] ,                // allowed job types among 직장인, 공무원, 자영업, 프리랜서, 없음; [] = any
           "excludeWorkers": [],          // e.g. ["공무원"] when officially excluded
           "homeless": null, "household": [], "sido": [], "car": null, "renter": null },
  "how": "카드사 앱에서 K-패스 카드 발급 후 회원가입",   // ≤ 45 chars
  "when": "상시" | "매년 5월" | "1월 16~31일" ...,
  "url": "official page (gov / public institution / card company official)",
  "source": "official page that states the amount/rate",
  "verified": "2026-11"
}
Rules: only facts you can confirm on an official source; if a figure changed for 2026, use the 2026 figure; when unsure, set yearlyWon null
and explain in basis. Keep yearlyWon conservative (typical person, not theoretical max) — the app sums these. Write the output in Korean
(values), keep keys in English. Do not edit any other file.
When done, reply in under 10 lines: item count, how many have yearlyWon, and the items you were least sure about.

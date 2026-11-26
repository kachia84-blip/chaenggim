# Task 7 — category and region filters on the 공연 tab (mockup "A. two chip rows")

Read SPEC.md first (design rules: paper neutrals, one navy accent #1F4E8C, dashed dividers, weights 400/500, no new icon sets,
emoji only, no exclamation marks, sentence-style Korean). All UI text in Korean (write the output UI text in Korean).
Edit only app.js, style.css, sw.js. Do not touch data/, collect/, SPEC.md, 진행상황.md, .git. Do not commit.
The home tab ("오늘") stays as it is — filters go on the 공연 tab only.

## Data
Events come from `upcomingEvents(today)` (merged data/events.json + data/seoul_events.json). Each item has `realm`, `sido`,
`sigungu`, `target` (may be missing on events.json items), `free`, `applyDay`, `source` ("seoul" for Seoul items).
Realm values seen:
- events.json: 음악/콘서트, 전시, 연극, 교육/체험, 뮤지컬/오페라, 무용/발레, 행사/축제, 국악, 기타, 아동/가족
- seoul_events.json: 교육체험, 공원탐방, 산림여가, 전시/관람, 문화행사, 기타, 자연/과학, 청년정보, 도시농업, 역사, 공예/취미,
  서울형키즈카페, 교양/어학, 스포츠, 미술제작

## 1. Categories
Add `eventCategories(item)` returning an array of category keys (an item may belong to more than one):
- 음악: 음악/콘서트, 국악
- 연극·뮤지컬: 연극, 뮤지컬/오페라, 무용/발레
- 전시: 전시, 전시/관람, 미술제작, 역사
- 체험·교육: 교육/체험, 교육체험, 공예/취미, 교양/어학, 도시농업, 자연/과학, 스포츠
- 숲·공원: 공원탐방, 산림여가
- 축제: 행사/축제, 문화행사
- 아이랑: 아동/가족, 서울형키즈카페, OR `target` matches /어린이|유아|아동|초등|가족/ (in addition to its realm category)
- 청년: 청년정보, OR `target` matches /청년/
- 기타: anything that got no category above
Order of chips: 전체, 음악, 연극·뮤지컬, 전시, 체험·교육, 숲·공원, 축제, 아이랑, 청년, 기타.

## 2. Layout (two rows above the list)
Row 1 — condition chips (single select, same behaviour as now): 전체 · 무료 · 신청 가능 · 티켓 오픈, followed by a region
control. Remove the old "내 지역" chip; the region control replaces it.
- Region control: a native `<select>` styled like a chip (same height/radius/border as `.chip`, a small "▾" is fine via CSS),
  `aria-label="지역"`. Options: "전국", then every 시도 present in the data as "<시도 short name> 전체" (e.g. "서울 전체"),
  and, for the currently selected 시도 only, each 구/군 present in the data for that 시도 (sorted ko). Value encoding is up to you.
- Default region: profile.sigungu (if set and not "모름") else profile.sido (if set and not "모름") else 전국.
  Keep the choice in a module variable for the session (no localStorage).
Row 2 — category chips (single select): only show categories that have ≥1 item under the current row-1 + region filters,
but always keep the selected one visible. Each chip shows its count, e.g. "음악 34" (전체 shows the total).
This row must not wrap: one horizontal scroll line (`overflow-x: auto`, hide the scrollbar, keep 44px tap height,
`scroll-padding` so the first chip aligns with the page edge). Row 1 may wrap as now.
Give each row role="group" with aria-label "공연 조건" / "분야". Keep `aria-pressed` on chips and the existing
`render({ focusFilter })` focus behaviour (use distinct dataset keys so focus restores to the right chip in either row).

## 3. Filtering and sorting
Row 1 AND region AND category. Region match: 전국 → all; 시도 → `item.sido === sido`; 구 → same sido and
`inDistrict(item, gu)`. Keep the existing sort (신청 가능 → applyDay ascending, otherwise start order).
Empty state: "조건에 맞는 행사가 없어요" with a quiet text button "조건 초기화" that resets row 1 to 전체, category to 전체
and region to 전국.
The home links that set `eventFilter = "apply"` / `"free"` before going to #events must also reset the category to 전체.

## 4. Misc
- Page head stays "공연".
- Bump sw.js cache version (v12 → v13).
- No new emoji.
- Check: `node --check app.js`; open the page logic mentally for a 375px screen; make sure nothing overflows horizontally
  except the intended scroll row.

Report in Korean: what changed, which functions were added, anything you could not do.

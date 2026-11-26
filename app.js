"use strict";

// 날짜 · 서울 달력의 날짜를 정수로 계산한다.
const DAY_MS = 86_400_000;
const SEOUL_OFFSET = 9 * 60 * 60 * 1000;
const seoul = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit"
});
const koreanDate = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "UTC", month: "long", day: "numeric", weekday: "long"
});
const weekdays = ["일", "월", "화", "수", "목", "금", "토"];
const koreanTime = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul", hour: "numeric", minute: "2-digit", hourCycle: "h23"
});

function dayNumber(date) {
  return Date.parse(date + "T00:00:00Z") / DAY_MS;
}

function seoulDay(now = Date.now()) {
  const parts = Object.fromEntries(seoul.formatToParts(now).map(({ type, value }) => [type, value]));
  return dayNumber(parts.year + "-" + parts.month + "-" + parts.day);
}

function dayDate(day) {
  return new Date(day * DAY_MS);
}

function dateParts(day) {
  const date = dayDate(day);
  return [date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate()];
}

function dateLabel(day) {
  const [, month, date] = dateParts(day);
  return month + "월 " + date + "일";
}

function periodLabel(start, end) {
  if (start === end) return dateLabel(start);
  const [year, month] = dateParts(start);
  const [endYear, endMonth, endDate] = dateParts(end);
  if (year !== endYear) return dateLabel(start) + "~" + endYear + "년 " + dateLabel(end);
  return dateLabel(start) + "~" + (month === endMonth ? endDate + "일" : dateLabel(end));
}

function dDay(distance, todayLabel = "오늘 마감") {
  return distance === 0 ? todayLabel : "D-" + distance;
}

function openingDate(value) {
  if (!value) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return { day: dayNumber(value), time: null };
  }
  const time = Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : value + "+09:00");
  return Number.isFinite(time) ? { day: seoulDay(time), time } : null;
}

function opensLater(opening, today, now) {
  return opening.day >= today && (opening.time === null || opening.time >= now);
}

// 데이터 불러오기 · 일부 파일이 실패해도 받은 일정은 표시한다.
const eventDataKeys = ["events", "seoul_events"];
const dataKeys = ["picks", "benefits", "taxes", ...eventDataKeys, "tips", "dormant"];
const data = Object.fromEntries(dataKeys.map(key => [key, []]));
const failed = new Set();
let pendingLoads = 0;

async function readData(key, allowMissing = false) {
  let response;
  try {
    response = await fetch("./data/" + key + ".json", { cache: "no-cache" });
  } catch (error) {
    if (allowMissing && error instanceof TypeError) return null;
    throw error;
  }
  if (allowMissing && response.status === 404) return null;
  if (!response.ok) throw new Error("일정을 불러오지 못했어요.");
  const items = await response.json();
  if (!Array.isArray(items)) throw new Error("일정 형식을 확인해 주세요.");
  return items;
}

async function readBenefits(sido) {
  const [national, local] = await Promise.all([
    readData("benefits/전국", true),
    sido ? readData("benefits/" + encodeURIComponent(sido), true) : null
  ]);
  const regional = (local ?? []).map(item => ({ ...item, sido }));
  if (national !== null) return [...national, ...regional].map(prepareBenefit);

  const samples = (await readData("benefits")).flatMap(item => {
    const sampleRegions = item.cond?.sido ?? [];
    if (!item.sample || (sampleRegions.length && (local !== null || !sampleRegions.includes(sido)))) return [];
    return [{ ...item, sido: sampleRegions.length ? sido : item.sido }];
  });
  return [...samples, ...regional].map(prepareBenefit);
}

async function loadData(keys = dataKeys) {
  const sido = benefitSido();
  pendingLoads++;
  render();
  const results = await Promise.allSettled(keys.map(key =>
    key === "benefits" ? readBenefits(sido) : readData(key, key === "seoul_events")));
  results.forEach((result, index) => {
    const key = keys[index];
    if (key === "benefits" && sido !== benefitSido()) return;
    if (result.status === "fulfilled") {
      data[key] = result.value ?? [];
      failed.delete(key);
    } else {
      failed.add(key);
    }
  });
  pendingLoads--;
  render();
  scheduleRefresh();
}

function dataNotice(keys) {
  const missing = keys.filter(key => failed.has(key));
  if (!missing.length) return null;
  return el("div", "state", el("p", null, "일부 일정을 불러오지 못했어요."),
    button("다시 불러오기", "quiet-button text-button", () => loadData(missing)));
}

// 프로필 · 선택한 조건만 기기에 저장한다.
const PROFILE_KEY = "chaenggim.profile";
const DORMANT_KEY = "chaenggim.dormant";
const regions = [
  "서울특별시", "부산광역시", "대구광역시", "인천광역시", "대전광역시",
  "울산광역시", "세종특별자치시", "경기도", "강원특별자치도", "충청북도", "충청남도",
  "전북특별자치도", "전남광주통합특별시", "경상북도", "경상남도", "제주특별자치도"
];
const profileSteps = ["나이·지역", "가구·집", "일·차"];
const nonOwnerHousing = ["전세", "월세", "부모님 집"];
const housingOptions = ["자가", ...nonOwnerHousing, "모름"];
const childOptions = ["있음", "없음", "모름"];
let profile = readSavedObject(PROFILE_KEY);
let dormantChecks = readSavedObject(DORMANT_KEY);
// 잠자는 돈은 해마다 새로 생기므로, 확인한 지 1년이 지나면 체크를 풀고 다시 알린다.
const dormantDue = new Set();
for (const [id, day] of Object.entries(dormantChecks)) {
  if (Date.now() - Date.parse(day) > 365 * 864e5) { dormantDue.add(id); delete dormantChecks[id]; }
}

function benefitSido() {
  return regions.includes(profile.sido) ? profile.sido : "";
}

function readSavedObject(key) {
  try {
    const saved = JSON.parse(localStorage.getItem(key));
    if (saved && typeof saved === "object" && !Array.isArray(saved)) return saved;
  } catch {
    // 저장소를 사용할 수 없으면 조건 없이 표시한다.
  }
  return {};
}

function hasProfile() {
  return Object.values(profile).some(value => value != null && value !== "" && value !== "모름");
}

function childStatus(person) {
  return person.child ?? (person.household === "자녀있음" ? "있음" : "모름");
}

function field(label, input) {
  return el("label", "field", el("span", null, label), input);
}

function inputField(label, name, value, attributes) {
  const input = el("input");
  for (const [attribute, setting] of Object.entries(attributes)) input.setAttribute(attribute, setting);
  input.name = name;
  input.value = value ?? "";
  return field(label, input);
}

function selectField(label, name, value, choices, emptyLabel = "선택 안 함") {
  const select = el("select");
  select.name = name;
  const options = [["", emptyLabel], ...choices];
  for (const choice of options) {
    const [key, title] = Array.isArray(choice) ? choice : [choice, choice];
    const option = el("option", null, title);
    option.value = key;
    select.append(option);
  }
  select.value = String(value ?? "");
  if (select.selectedIndex < 0) select.value = "";
  return field(label, select);
}

function profileFields(step, draft) {
  if (step === 0) {
    return [
      inputField("태어난 해", "birthYear", draft.birthYear, {
        type: "number", min: 1900, max: dateParts(seoulDay())[0], inputmode: "numeric", placeholder: "1990"
      }),
      selectField("시·도", "sido", draft.sido, regions),
      inputField("시·군·구", "sigungu", draft.sigungu, { type: "text", maxlength: 30, placeholder: "강남구" })
    ];
  }
  if (step === 1) {
    return [
      selectField("가구 형태", "household", draft.household, [
        ["1인", "1인 가구"], ["부부", "부부"], ["자녀있음", "자녀와 함께"], ["부모님과", "부모님과 함께"]
      ]),
      selectField("집", "housing", draft.housing, housingOptions),
      selectField("자녀", "child", childStatus(draft), childOptions),
      selectField("가구 소득", "incomeBand", draft.incomeBand, [
        ["모름", "모름"], ["중위50이하", "중위소득 50% 이하"], ["중위100이하", "중위소득 100% 이하"],
        ["중위150이하", "중위소득 150% 이하"], ["그이상", "중위소득 150% 초과"]
      ]),
      selectField("기초생활수급·차상위", "lowIncome", draft.lowIncome,
        [["true", "예"], ["false", "아니요"]], "모름")
    ];
  }
  return [
    selectField("일", "worker", draft.worker, ["직장인", "공무원", "자영업", "프리랜서", "없음"]),
    selectField("자동차 보유", "car", draft.car, [["true", "있음"], ["false", "없음"]])
  ];
}

function updateDraft(form, draft) {
  for (const [key, raw] of new FormData(form)) {
    const value = raw.trim();
    if (key === "lowIncome") draft[key] = value ? value === "true" : null;
    else if (!value) delete draft[key];
    else if (key === "birthYear") draft[key] = Number(value);
    else if (key === "car") draft[key] = value === "true";
    else draft[key] = value;
    if (key === "housing") {
      if (value && value !== "모름") draft.homeless = nonOwnerHousing.includes(value);
      else if (!value && profile.housing == null && typeof profile.homeless === "boolean") {
        draft.homeless = profile.homeless;
      } else delete draft.homeless;
    }
  }
}

function openProfile() {
  showProfileStep(0, { ...profile });
}

function showProfileStep(step, draft) {
  const title = profileSteps[step];
  const progress = el("p", "row-meta", (step + 1) + " / " + profileSteps.length + "단계");
  const form = el("form", null);
  const error = el("p", "profile-error row-meta");
  error.setAttribute("role", "alert");
  error.hidden = true;
  const actions = el("div", "sheet-actions");
  if (step > 0) {
    actions.append(button("이전", "quiet-button", () => {
      updateDraft(form, draft);
      showProfileStep(step - 1, draft);
    }));
  }
  const last = step === profileSteps.length - 1;
  const submit = el("button", "action", last ? "저장" : "다음");
  submit.type = "submit";
  actions.append(submit);
  form.append(el("div", "fields", ...profileFields(step, draft)), error, actions);
  form.addEventListener("submit", event => {
    event.preventDefault();
    updateDraft(form, draft);
    if (!last) {
      showProfileStep(step + 1, draft);
      return;
    }
    try {
      localStorage.setItem(PROFILE_KEY, JSON.stringify(draft));
    } catch {
      error.hidden = false;
      error.textContent = "이 기기에 조건을 저장할 수 없어요.";
      return;
    }
    const previousSido = benefitSido();
    profile = draft;
    homeEventDay = null;
    benefitLimit = BENEFIT_PAGE_SIZE;
    sheet.close();
    if (benefitSido() !== previousSido) {
      data.benefits = [];
      loadData(["benefits"]);
    } else {
      render();
    }
  });
  showSheet(title, progress, form);
}

// 추천 · 프로필로 확인할 수 있는 조건과 추가로 확인할 조건을 구분한다.
const pickKinds = ["받는 돈", "아끼는 돈"];

function pickStatus(item, person, today = seoulDay()) {
  const who = item.who ?? {};
  const ageRestricted = who.ageMin != null || who.ageMax != null;
  const [year, month, day] = dateParts(today);
  const ages = [];
  if (Number.isInteger(person.birthYear) && person.birthYear > 0 && person.birthYear <= year) {
    const yearAge = year - person.birthYear;
    ages.push(yearAge);
    // 출생연도만 저장하므로 생일에 따라 자격이 갈리는 경우는 확인이 필요하다.
    if (yearAge > 0 && !who.ageByYear && (month !== 12 || day !== 31)) ages.push(yearAge - 1);
  }
  const ageMin = who.ageMin ?? -Infinity;
  const ageMax = who.ageMax ?? Infinity;
  const possibleAge = ages.some(age => age >= ageMin && age <= ageMax + (who.ageAdjustmentMax ?? 0));
  const confirmedAge = ages.length && ages.every(age => age >= ageMin && age <= ageMax);
  const child = childStatus(person);
  const known = value => value != null && value !== "" && value !== "모름";
  const conditions = [
    [who.workers?.length || who.excludeWorkers?.length, known(person.worker),
      (!who.workers?.length || who.workers.includes(person.worker)) && !who.excludeWorkers?.includes(person.worker)],
    [who.lowIncomeOnly, typeof person.lowIncome === "boolean", person.lowIncome === true],
    [who.sido?.length, known(person.sido), who.sido?.includes(person.sido)],
    [who.excludeSigungu?.length, known(person.sigungu),
      !who.excludeSigungu?.some(area => person.sigungu?.split(/\s+/).includes(area))],
    [who.car, typeof person.car === "boolean", person.car === true],
    [who.housing?.length, known(person.housing), who.housing?.includes(person.housing)],
    [who.needsChild, known(child), child === "있음"]
  ];
  if (ageRestricted && ages.length && !possibleAge) return "no";
  if (conditions.some(([required, answered, matches]) => required && answered && !matches)) return "no";
  // 가구의 중위소득 구간만으로 제도별 급여·소득인정액·재산 한도를 확인할 수 없다.
  // eligibilityNote는 신청 방법 안내라서 그것만으로 "확인 필요"로 내리지 않는다.
  if ((who.incomeCapped && !who.lowIncomeOnly) ||
      (ageRestricted && !confirmedAge) ||
      conditions.some(([required, answered]) => required && !answered)) return "check";
  return "ok";
}

function visiblePicks(today) {
  return data.picks.map(item => ({ ...item, status: pickStatus(item, profile, today) }))
    .filter(item => item.status !== "no")
    .sort((first, second) => Number(first.status === "check") - Number(second.status === "check") ||
      (second.yearlyWon ?? -1) - (first.yearlyWon ?? -1));
}

function tabLink(tab, label, className) {
  const link = el("a", className, label);
  link.href = "#" + tab;
  return link;
}

function pickWho(who) {
  const age = who.ageMin != null && who.ageMax != null ? `만 ${who.ageMin}~${who.ageMax}세`
    : who.ageMin != null ? `만 ${who.ageMin}세 이상` : who.ageMax != null ? `만 ${who.ageMax}세 이하` : "";
  return [
    age, who.incomeNote || (who.lowIncomeOnly ? "기초생활수급자·차상위계층" : ""),
    who.workers?.join("·"), who.excludeWorkers?.length && who.excludeWorkers.join("·") + " 제외",
    who.sido?.join("·"), who.car && "자동차 보유", who.housing?.join("·"),
    who.needsChild && "자녀 있음", who.eligibilityNote
  ].filter(Boolean).join("\n") || "별도 대상 제한 없음";
}

function pickNote(item) {
  return item.status === "check" ? el("span", "row-meta", "조건 확인 필요") : null;
}

function openPick(item) {
  showDetail(item.emoji, item.title, false, [
    ["무엇", item.plain], ["얼마", detailCopy(item.amountText, item.basis)], ["누가", pickWho(item.who)],
    ["어떻게", item.how], ["언제", item.when]
  ], item.url, { note: pickNote(item) });
}

function pickRow(item) {
  return rowControl({ open: () => openPick(item) }, "row pick-row", emoji(item.emoji),
    el("span", "row-text", el("span", "pick-title", el("span", "row-title", item.title),
      el("span", "pick-kind", item.kind)), el("span", "row-sub", item.plain), pickNote(item)),
    el("span", "status pick-amount", item.amountText));
}

function renderPicks(today) {
  const items = visiblePicks(today);
  const groups = pickKinds.map(kind => {
    const group = items.filter(item => item.kind === kind);
    return group.length ? el("section", "card", el("h2", null, kind), listing(group.map(pickRow))) : null;
  });
  return [pageHead("챙길 수 있는 돈", null, button("내 조건 바꾸기", "quiet-button text-button", openProfile)),
    dataNotice(["picks"]), items.length ? el("div", "stack", ...groups)
      : el("p", "state", "조건에 맞는 추천이 없어요")];
}

function dormantCount() {
  return data.dormant.filter(item => Object.hasOwn(dormantChecks, item.id)).length;
}

function openDormant() {
  const progress = el("p", "row-meta");
  progress.setAttribute("aria-live", "polite");
  const updateProgress = () => {
    const count = dormantCount();
    const first = Object.values(dormantChecks).sort()[0];
    const again = first ? `${Number(first.slice(0, 4)) + 1}년 ${Number(first.slice(5, 7))}월` : "";
    progress.textContent = count === data.dormant.length && again
      ? `모두 확인했어요 · ${again}에 다시 알려 드릴게요`
      : `${data.dormant.length}곳 중 ${count}곳 확인함` + (dormantDue.size ? " · 다시 확인할 때가 됐어요" : "");
  };
  updateProgress();
  const rows = data.dormant.map(item => {
    const check = el("input");
    check.type = "checkbox";
    check.checked = Object.hasOwn(dormantChecks, item.id);
    check.setAttribute("aria-label", item.title + " 확인함");
    check.addEventListener("change", () => {
      const next = { ...dormantChecks };
      if (check.checked) next[item.id] = dayDate(seoulDay()).toISOString().slice(0, 10);
      else delete next[item.id];
      try {
        localStorage.setItem(DORMANT_KEY, JSON.stringify(next));
      } catch {
        check.checked = Object.hasOwn(dormantChecks, item.id);
        progress.textContent = "이 기기에 확인 기록을 저장할 수 없어요";
        return;
      }
      dormantChecks = next;
      updateProgress();
      const counter = document.querySelector("#dormant-count");
      if (counter) counter.textContent = `${dormantCount()}/5`;
    });
    const detail = button("", "row dormant-detail", () => showDetail(item.emoji, item.title, false, [
      ["무엇", item.what], ["어디서", item.where], ["어떻게", item.how]
    ], item.url, { linkLabel: "사이트 열기" }));
    detail.append(el("span", "row-text", el("span", "row-title", item.title),
      el("span", "row-meta", dormantDue.has(item.id) ? item.where + " · 1년이 지나 다시 확인해요" : item.where)));
    return el("div", "dormant-row", el("label", "check-target", check), detail);
  });
  showSheet("잠자는 내 돈 5곳", progress,
    rows.length ? listing(rows) : el("p", "state", "확인할 목록을 불러오지 못했어요"));
}

let homeEventDay = null;

function inDistrict(item, sigungu) {
  return item.sigungu === sigungu || (item.sigungu ?? "").startsWith(sigungu + " ");
}

function districtOrder(first, second, sigungu) {
  if (!sigungu) return 0;
  return Number(inDistrict(second, sigungu)) - Number(inDistrict(first, sigungu));
}

function weekEnd(today) {
  return today + (7 - dayDate(today).getUTCDay()) % 7;
}

function weeklyEvents(today, sido, sigungu) {
  const sunday = weekEnd(today);
  const events = upcomingEvents(today)
    .filter(item => item.free === true && (!sido || item.sido === sido) &&
      (item.applyDay >= today || (item.endDay >= today && item.startDay <= sunday)))
    .map(item => ({ ...item, day: Math.max(today, item.startDay) }))
    .sort((a, b) => a.day - b.day || districtOrder(a, b, sigungu) ||
      (a.applyDay >= today ? a.applyDay : Infinity) - (b.applyDay >= today ? b.applyDay : Infinity) ||
      b.startDay - a.startDay);
  if (!sigungu || sido === "서울특별시") return events;
  const local = events.filter(item => inDistrict(item, sigungu));
  if (!sido || local.length >= 5) return local;
  const nearby = events.filter(item => !inDistrict(item, sigungu) && item.sigungu).slice(0, 5 - local.length);
  const selected = new Set([...local, ...nearby]);
  return events.filter(item => selected.has(item));
}

function homeEventRow(item, today, sigungu) {
  const thumbnail = el("span", "home-event-image");
  if (item.source === "seoul") {
    // 서울 예약 사진은 원본이 장당 2MB 안팎이라 휴대폰 데이터·배터리를 아끼려고 분야 이모지로 대신한다.
    thumbnail.append(emoji(item.emoji));
  } else if (item.image) {
    const image = el("img");
    image.alt = "";
    image.loading = "lazy";
    image.addEventListener("error", () => image.remove(), { once: true });
    image.src = item.image;
    thumbnail.append(image);
  }
  const [, month, day] = dateParts(item.endDay);
  const multiDay = item.startDay !== item.endDay ? `~${month}.${day}까지` : "";
  const nearby = (sigungu || item.source === "seoul") && !inDistrict(item, sigungu) ? item.sigungu : "";
  const target = /^제한\s*없음$/.test(item.target) ? "" : item.target;
  const meta = [item.time, item.venue || item.placeAddr, multiDay, nearby, target].filter(Boolean).join(" · ");
  const distance = item.applyDay - today;
  const status = item.applyDay >= today && distance <= 30
    ? el("span", "status countdown", distance === 0 ? "오늘 마감" : `신청 D-${distance}`)
    : el("span", "status", item.applyDay > today ? "신청 받는 중" : item.applyDay < today ? "신청 마감" : item.entry);
  return rowControl(item, "row home-event-row", thumbnail,
    el("span", "row-text", el("span", "row-title", item.title), meta && el("span", "row-meta", meta), sampleLabel(item)),
    status.textContent ? status : null);
}

// 오늘 마감인데 마감 시각이 이미 지났으면 신청할 수 없다.
function applyOpen(item, today) {
  if (!(item.applyDay >= today)) return false;
  if (item.applyDay > today || !/^\d\d:\d\d$/.test(item.applyEndTime ?? "")) return true;
  return koreanTime.format(Date.now()).padStart(5, "0") < item.applyEndTime;
}

function homeEvents(today, sido, sigungu) {
  const sunday = weekEnd(today);
  const all = weeklyEvents(today, sido, sigungu);
  // 서울 예약은 신청만 이번 주이고 행사는 몇 주 뒤인 경우가 많아 요일 목록에는 이번 주 행사만 둔다.
  const events = all.filter(item => item.day <= sunday);
  const counts = new Map();
  for (const item of events) counts.set(item.day, (counts.get(item.day) ?? 0) + 1);
  if (!counts.has(homeEventDay)) homeEventDay = null;
  const filters = el("div", "filters home-filters");
  filters.setAttribute("role", "group");
  filters.setAttribute("aria-label", "행사 요일");
  const chip = (day, label) => {
    const control = button(label, "chip", () => {
      homeEventDay = day;
      render({ focusFilter: control.dataset.filter });
    });
    control.dataset.filter = day ?? "all";
    control.setAttribute("aria-pressed", String(homeEventDay === day));
    return control;
  };
  filters.append(chip(null, `전체 ${events.length}`));
  for (const [day, count] of counts) {
    const label = day === today ? "오늘" : day === today + 1 ? "내일" :
      day <= sunday ? weekdays[dayDate(day).getUTCDay()] : dateLabel(day);
    filters.append(chip(day, `${label} ${count}`));
  }
  const selected = events.filter(item => homeEventDay === null || item.day === homeEventDay);
  const deadlines = homeEventDay !== null ? [] : all
    .filter(item => applyOpen(item, today) && item.applyDay <= today + 7)
    .sort((a, b) => districtOrder(a, b, sigungu) || a.applyDay - b.applyDay);
  // 한 장소가 같은 달 프로그램을 여러 개 올려 목록을 채우지 않도록 장소마다 2건까지만 보인다.
  const perVenue = new Map();
  const fewPerVenue = item => {
    const key = item.venue || item.title;
    perVenue.set(key, (perVenue.get(key) ?? 0) + 1);
    return perVenue.get(key) <= 2;
  };
  const shown = deadlines.filter(fewPerVenue).slice(0, 6);
  const urgent = new Set(shown);
  const sections = [];
  if (shown.length) {
    const rest = deadlines.length - shown.length;
    const applyMore = rest > 0 ? tabLink("events", `신청 마감 임박 ${rest}건 더 보기`, "quiet-button text-button") : null;
    applyMore?.addEventListener("click", () => { eventFilter = "apply"; });
    sections.push(el("section", null, el("h2", "section-label", "신청 마감 임박"),
      listing(shown.map(item => homeEventRow(item, today, sigungu))), applyMore));
  }
  const groups = new Map();
  perVenue.clear();
  for (const item of selected.filter(item => !urgent.has(item)).filter(fewPerVenue).slice(0, 12)) {
    if (!groups.has(item.day)) groups.set(item.day, []);
    groups.get(item.day).push(homeEventRow(item, today, sigungu));
  }
  for (const [day, rows] of groups) {
    sections.push(el("section", null,
      el("h2", "section-label", weekdays[dayDate(day).getUTCDay()] + "요일 " + dateLabel(day)), listing(rows)));
  }
  const more = tabLink("events", "공연 탭에서 더 보기", "quiet-button text-button card-link");
  more.addEventListener("click", () => { eventFilter = "free"; });
  return [filters, !sido && !sigungu ? el("div", "home-location", el("p", null, "내 동네를 넣으면 가까운 행사만 보여요"),
    button("동네 설정", "quiet-button text-button", openProfile)) : null, dataNotice(eventDataKeys),
    sections.length ? el("div", "home-event-groups", ...sections)
      : el("p", "state", "이번 주 무료 행사가 없어요"), more];
}

function tipCard(today) {
  const [year] = dateParts(today);
  const dayOfYear = today - dayNumber(year + "-01-01");
  const tip = data.tips[dayOfYear % data.tips.length];
  return el("section", "card", el("h2", null, "오늘의 생활정보"), tip
    ? el("div", "tip-content", el("span", "row-meta", emoji(tip.emoji), tip.category),
      el("h3", null, tip.title), el("p", null, tip.body),
      officialLink(tip.link, "공식 안내 보기", "quiet-button text-button"))
    : el("p", "state", "오늘 표시할 생활정보가 없어요."));
}

function renderToday(today) {
  const sido = profile.sido === "모름" ? "" : profile.sido;
  const sigungu = profile.sigungu === "모름" ? "" : profile.sigungu;
  const tax = upcomingTaxes(today, true)[0];
  const due = matchingBenefits(today).filter(item => item.endDay - today <= 14 && readyToReceive(item, today)).length;
  const dueLink = tabLink("benefits", null, "row quiet-row");
  dueLink.append(el("span", "row-title", "지원금 마감 임박"), el("span", "status", `${due}건`));
  dueLink.addEventListener("click", () => {
    benefitSortByDeadline = true;
    benefitQuery = "";
    benefitLimit = BENEFIT_PAGE_SIZE;
  });
  const counter = el("span", "status", `${dormantCount()}/5`);
  counter.id = "dormant-count";
  const dormant = button("", "row quiet-row", openDormant);
  dormant.id = "dormant-button";
  dormant.append(el("span", "row-title", "잠자는 내 돈 5곳"), counter);
  const picks = tabLink("picks", `이득 보는 제도 ${visiblePicks(today).length}가지`, "row quiet-row row-title");
  const taxRow = tax ? rowControl({ open: () => openTax(tax) }, "row quiet-row",
    el("span", "row-text", el("span", "row-title", "다가오는 세금"), el("span", "row-meta", tax.title)),
    statusText(taxStatus(tax, today))) : null;
  const date = el("time", null, koreanDate.format(dayDate(today)));
  date.dateTime = dayDate(today).toISOString().slice(0, 10);
  return [pageHead("이번 주 무료 행사", el("p", null, (sigungu || sido || "전국") + " · ", date)),
    ...homeEvents(today, sido, sigungu), el("div", "stack home-extras",
      el("section", null, el("h2", "section-label", "그 밖에 챙길 것"),
        listing(taxRow ? [dueLink, dormant, picks, taxRow] : [dueLink, dormant, picks]),
        dataNotice(dataKeys.filter(key => !eventDataKeys.includes(key)))), tipCard(today))];
}

// 지원금 · 이전 수집본에도 금액과 조건을 표시한다.
const legacyPersonal = ["근로자/직장인", "구직자/실업자", "대학생", "임산부", "출산/입양", "장애인", "국가보훈대상자"];
const legacyHousehold = ["1인가구", "무주택세대", "다자녀가구", "한부모가정"];
const narrowTraits = new Set([
  "예비부모/난임", "임산부", "출산/입양", "장애인", "국가보훈대상자", "질병/질환자",
  "한부모가정", "다자녀가구", "농업인", "어업인", "축산업인", "임업인",
  "초등학생", "중학생", "고등학생", "대학생", "다문화가족", "북한이탈주민", "신규전입", "확대가족"
]);
const BENEFIT_PAGE_SIZE = 40;
let benefitLimit = BENEFIT_PAGE_SIZE;
let benefitQuery = "";
let benefitSortByDeadline = false;
const legacyWonUnits = { 억: 100_000_000, 천만: 10_000_000, 백만: 1_000_000, 십만: 100_000, 만: 10_000,
  천: 1_000, 백: 100, 십: 10, "": 1 };
const wonNumber = "(?:\\d{1,3}(?:,\\d{3})+|\\d+)(?:\\.\\d+)?";
const wonUnit = "억|천\\s*만|백\\s*만|십\\s*만|만|천|백|십";
const wonPart = new RegExp(`(${wonNumber})\\s*(${wonUnit})?`, "g");
const wonFigure = new RegExp(`(?<!\\d)(?<!\\d[.,])((?:(?:매월|월|연간|연|1인당|최대)\\s*)*)` +
  `(?:${wonNumber}\\s*(?:${wonUnit})?\\s*원?\\s*[~～∼–-]\\s*)?` +
  `((?:${wonNumber}\\s*(?:${wonUnit})\\s*)*${wonNumber}\\s*(?:${wonUnit})?\\s*)원(\\s*상당)?`, "g");

function shortBenefitText(value = "") {
  const text = value.replace(/^[ \t○□]*-(?!\d)|[○□]/gm, " ").trim().replace(/\s+/g, " ");
  return text.length <= 60 ? text : text.slice(0, Math.max(0, text.lastIndexOf(" ", 60))).trimEnd();
}

function legacyBenefitAmount(item) {
  const support = item.amount ?? "";
  if (/융자|대출|보증(?!금)|\bloan\b/i.test(item.name + " " + support)) return { amountWon: null, amountText: "" };
  for (const source of [support, item.name]) {
    let best = { amountWon: null, amountText: "" };
    for (const clause of source.split(/[\r\n;○□]/)) {
      const matches = [...clause.matchAll(wonFigure)];
      matches.forEach((match, index) => {
        const [, prefix, figure, equivalent] = match;
        let won = [...figure.matchAll(wonPart)].reduce((total, [, value, unit = ""]) =>
          total + Number(value.replaceAll(",", "")) * legacyWonUnits[unit.replace(/\s/g, "")], 0);
        const amount = figure.trim().replace(/\s+/g, " ") + " 원";
        let label = [prefix.trim(), amount, equivalent?.trim()].filter(Boolean).join(" ");
        if (prefix.includes("월")) {
          const trailing = clause.slice(match.index + match[0].length, matches[index + 1]?.index);
          const leading = index === 0 ? clause.slice(0, match.index) : "";
          const months = (trailing.match(/(\d+)\s*개월(?!\s*(?:미만|이상|이하|초과))/) ??
            leading.match(/(\d+)\s*개월\s*(?:간|동안)?\s*$/))?.[1];
          won *= months == null ? 12 : Number(months);
          if (months) label += ` · 최대 ${months}개월`;
        }
        won = Math.trunc(won);
        if (Number.isSafeInteger(won) && won > (best.amountWon ?? 0)) {
          best = { amountWon: won, amountText: label.length <= 30 ? label : "" };
        }
      });
    }
    if (best.amountWon != null) return best;
  }
  return { amountWon: null, amountText: "" };
}

function prepareBenefit(item) {
  const cond = item.cond ?? {};
  const flags = cond.flags ?? [];
  const need = cond.need ?? [
    ...[legacyPersonal, legacyHousehold].flatMap(group => group.every(trait => flags.includes(trait))
      ? [] : group.filter(trait => flags.includes(trait))),
    ...(cond.homeless === true ? ["무주택세대"] : []),
    ...(cond.household?.length === 1 && cond.household[0] === "1인" ? ["1인가구"] : [])
  ];
  return {
    ...item, cond: { ...cond, need },
    ...(Object.hasOwn(item, "amountWon") ? {} : legacyBenefitAmount(item)),
    plain: item.plain ?? shortBenefitText(item.summary),
    who: item.who ?? shortBenefitText(item.target?.split(/[\r\n;]|,(?=\s)|\.(?=\s|$)/).find(line => line.trim())),
    deadlineText: item.deadlineText ?? (item.deadline ? dateLabel(dayNumber(item.deadline)) : "")
  };
}

function confirmedTraits() {
  return new Set([
    ...(profile.homeless === true ? ["무주택세대"] : []),
    ...(profile.household === "1인" ? ["1인가구"] : []),
    ...(["직장인", "공무원"].includes(profile.worker) ? ["근로자/직장인"] : [])
  ]);
}

function benefitMatches(item, today) {
  if (item.sigungu && profile.sigungu && profile.sigungu !== "모름" && item.sigungu !== profile.sigungu) return false;
  const cond = item.cond;
  const income = cond.income ?? [];
  const need = cond.need;
  if (profile.lowIncome === false && income.includes("JA0201") &&
      income.every(code => code === "JA0201" || code === "JA0202")) return false;
  if (need.includes("무주택세대") && profile.homeless === false) return false;
  if (need.includes("1인가구") && profile.household && !["1인", "모름"].includes(profile.household)) return false;
  if (need.includes("구직자/실업자") && ["직장인", "공무원"].includes(profile.worker)) return false;
  if (need.includes("근로자/직장인") && profile.worker === "없음") return false;
  if (!Number.isInteger(profile.birthYear) || profile.birthYear <= 0) return true;
  const age = dateParts(today)[0] - profile.birthYear;
  return (cond.ageMin == null || age >= cond.ageMin) && (cond.ageMax == null || age <= cond.ageMax);
}

function conditionLabel(item) {
  return item.unconfirmed ? el("span", "row-meta", "조건 확인 필요") : null;
}

function relevance(item, today) {
  let score = item.confirmedCount * 2;
  if (item.sigungu && item.sigungu === profile.sigungu) score += 3;
  if (item.sido && item.sido === profile.sido) score += 2;
  if (item.endDay - today <= 30) score += 2;
  if (item.amountWon >= 1_000_000) score += 2;
  if (item.amountWon > 0) score += 1;
  if (item.narrow) score -= 4;
  if (item.field === "농림축산어업") score -= 3;
  return score;
}

function matchingBenefits(today) {
  const confirmed = confirmedTraits();
  return data.benefits.map(item => ({
    ...item, endDay: item.deadline ? dayNumber(item.deadline) : Infinity
  })).filter(item => item.endDay >= today && benefitMatches(item, today))
    .map(item => {
      const need = item.cond.need;
      const confirmedCount = need.filter(trait => confirmed.has(trait)).length;
      const narrow = need.length > 0 && need.every(trait => narrowTraits.has(trait));
      const match = { ...item, confirmedCount, narrow, unconfirmed: confirmedCount < need.length };
      return { ...match, score: relevance(match, today) };
    }).sort((first, second) => second.score - first.score || first.endDay - second.endDay ||
      first.name.localeCompare(second.name, "ko"));
}

function readyToReceive(item, today) {
  const cond = item.cond;
  const [year, month, day] = dateParts(today);
  const age = year - profile.birthYear;
  const youngest = age - Number(month !== 12 || day !== 31);
  const hasAgeLimits = cond.ageMin != null || cond.ageMax != null;
  const ageConfirmed = Number.isInteger(profile.birthYear) && profile.birthYear > 0 && age >= 0 &&
    youngest >= (cond.ageMin ?? 0) && age <= (cond.ageMax ?? Infinity);
  return !item.sample && !item.unconfirmed &&
    (!item.sigungu || item.sigungu === profile.sigungu) &&
    (!hasAgeLimits || ageConfirmed) && !cond.income?.length && !cond.incomeMax;
}

function openBenefit(item) {
  showDetail(item.emoji, item.name, item.sample, [
    ["무엇", item.plain || item.summary], ["누가", detailCopy(item.who, item.target)],
    ["얼마", detailCopy(item.amountText, item.amount)], ["어떻게 신청", item.how],
    ["마감", item.deadlineText || "상시"]
  ], item.url, { linkLabel: "정부24에서 자세히 보기", note: conditionLabel(item) });
}

function detailCopy(short, original) {
  if (!short || !original || short === original) return short || original;
  return el("div", "detail-copy", el("p", null, short), el("p", null, original));
}

// "1,800,000 원" → "180만 원", "지원자격" 같은 제목뿐인 설명은 건너뛴다.
function niceAmount(text) {
  const plainWon = /^([\d,]+)\s*원$/.exec(text || "");
  if (!plainWon) return text || "";
  const won = Number(plainWon[1].replaceAll(",", ""));
  return won >= 10000 ? `${(won / 10000).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}만 원` : text;
}
function usefulWho(item) {
  const who = (item.who || "").replace(/^[ㅇo○□\-·\s]+/, "");
  return who.length >= 8 && !/^(지원\s*자격|지원\s*대상|대상|자격|사업\s*대상)\s*:?$/.test(who) ? who : "";
}

function benefitRow(item, today) {
  const status = statusText(item.deadline ? dDay(item.endDay - today) : "상시");
  const preview = niceAmount(item.amountText) || usefulWho(item) || item.plain;
  return rowControl({ open: () => openBenefit(item) }, "row benefit-row", emoji(item.emoji),
    el("span", "row-text", el("span", "row-title", item.name), preview && el("span", "row-sub", preview),
      item.org ? el("span", "row-meta", item.org) : null, conditionLabel(item), sampleLabel(item)), status);
}

function benefitResults(items, today) {
  const terms = benefitQuery.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length) {
    items = items.filter(item => {
      const searchable = [item.name, item.plain, item.org].join(" ").toLowerCase();
      return terms.every(term => searchable.includes(term));
    });
  }
  const row = item => benefitRow(item, today);
  const list = listing(items.slice(0, benefitLimit).map(row));
  const more = button("더 보기", "quiet-button text-button card-link", () => {
    const next = items.slice(benefitLimit, benefitLimit + BENEFIT_PAGE_SIZE).map(row);
    list.append(...next.map(control => el("li", null, control)));
    benefitLimit += BENEFIT_PAGE_SIZE;
    next[0]?.focus();
    if (benefitLimit >= items.length) more.parentElement.remove();
  });
  return items.length ? el("div", "card list-card", list,
    items.length > benefitLimit ? el("div", "list-more", more) : null)
    : el("p", "state", terms.length ? "검색 결과가 없어요" : "조건에 맞는 지원금이 없어요");
}

function renderBenefits(today) {
  const items = matchingBenefits(today);
  if (benefitSortByDeadline) items.sort((first, second) => first.endDay - second.endDay);
  const edit = button("내 조건 바꾸기", "quiet-button text-button", openProfile);
  edit.id = "benefit-profile-button";
  const results = el("div", null, benefitResults(items, today));
  const search = inputField("지원금 검색", "benefit-search", benefitQuery, {
    id: "benefit-search", type: "search", placeholder: "지원금 이름, 내용, 기관"
  });
  search.addEventListener("input", event => {
    benefitQuery = event.target.value;
    benefitLimit = BENEFIT_PAGE_SIZE;
    results.replaceChildren(benefitResults(items, today));
  });
  return [pageHead("지원금", hasProfile() ? null : el("p", null, "내 조건을 설정하면 맞는 지원금을 볼 수 있어요."), edit),
    search, dataNotice(["benefits"]), results];
}

// 세금 · 전년도에서 이어지는 기간과 다음 해 시작일을 함께 계산한다.
const taxWho = { all: "누구나", worker: "직장인", car: "자동차 보유자", owner: "주택 보유자", business: "사업자" };
let taxMonth = null;

function taxMatches(item) {
  if (item.who === "car") return profile.car !== false;
  if (item.who === "owner") return profile.homeless !== true;
  const worker = profile.worker;
  if (!["직장인", "공무원", "자영업", "프리랜서", "없음"].includes(worker)) return true;
  if (item.who === "worker") return worker === "직장인" || worker === "공무원";  // 공무원도 연말정산 대상
  if (item.who === "business") return worker === "자영업" || worker === "프리랜서";
  return true;
}

function taxOccurrence(item, year) {
  return {
    ...item,
    startDay: dayNumber(year + "-" + item.start),
    endDay: dayNumber((year + Number(Boolean(item.endNextYear))) + "-" + item.end)
  };
}

function upcomingTaxes(today, includeNextYear = false) {
  const [year] = dateParts(today);
  return data.taxes.filter(taxMatches).flatMap(item => {
    const years = [year];
    if (item.endNextYear) years.unshift(year - 1);
    if (includeNextYear) years.push(year + 1);
    return years.map(startYear => taxOccurrence(item, startYear));
  }).filter(item => item.endDay >= today)
    .sort((first, second) => Math.max(first.startDay, today) - Math.max(second.startDay, today) ||
      first.endDay - second.endDay);
}

function taxStatus(item, today) {
  if (item.startDay > today) return dDay(item.startDay - today);
  return item.endDay === today ? "오늘 마감" : "진행 중";
}

function openTax(item) {
  showDetail(item.emoji, item.title, false, [
    ["기간", periodLabel(item.startDay, item.endDay)], ["대상", taxWho[item.who]],
    ["신고·납부 내용", item.what], ["신고·납부 방법", item.how], ["챙길 점", item.tip]
  ], item.link);
}

function monthStrip(year, current) {
  const months = el("div", "months");
  months.setAttribute("role", "group");
  months.setAttribute("aria-label", year + "년 월별 세금 일정");
  for (let month = 1; month <= 12; month++) {
    const chip = button(month + "월", "chip", () => {
      taxMonth = taxMonth === month ? null : month;
      render({ retainControls: true, focusMonth: month });
    });
    chip.dataset.month = month;
    chip.setAttribute("aria-pressed", String(taxMonth === month));
    if (current === month) chip.setAttribute("aria-current", "date");
    months.append(chip);
  }
  return months;
}

function renderTaxes(today) {
  const [year, currentMonth] = dateParts(today);
  let items = upcomingTaxes(today);
  if (taxMonth) {
    const monthStart = Date.UTC(year, taxMonth - 1, 1) / DAY_MS;
    const nextMonth = Date.UTC(year, taxMonth, 1) / DAY_MS;
    items = items.filter(item => item.startDay < nextMonth && item.endDay >= monthStart);
  }
  const rows = items.map(item => rowControl({ open: () => openTax(item) }, "row", emoji(item.emoji),
    el("span", "row-text", el("span", "row-title", item.title),
      el("span", "row-sub", periodLabel(item.startDay, item.endDay)),
      el("span", "row-meta", taxWho[item.who]), el("span", "row-note", item.tip)),
    statusText(taxStatus(item, today))));
  return [pageHead("세금", el("p", null, year + "년 세금 달력")), monthStrip(year, currentMonth),
    el("p", "month-caption", taxMonth ? taxMonth + "월 일정" : "다가오는 일정"),
    dataNotice(["taxes"]), cardList(rows, "다가오는 세금 일정이 없어요.")];
}

// 공연 · 공연 기간과 티켓·신청 시작은 각각 표시한다.
const eventFilters = { all: "전체", free: "무료", apply: "신청 가능", tickets: "티켓 오픈", local: "내 지역" };
let eventFilter = "all";

function eventOpenings(item) {
  return [
    { label: "티켓 오픈", opening: openingDate(item.ticketOpen ?? item.ticket_open) },
    { label: "신청 시작", opening: openingDate(item.applyOpen ?? item.apply_open) }
  ].filter(entry => entry.opening).map(({ label, opening }) => ({ label, ...opening }));
}

function upcomingEvents(today) {
  return eventDataKeys.flatMap(key => data[key]).map(item => ({
    ...item, startDay: dayNumber(item.start), endDay: dayNumber(item.end), applyDay: dayNumber(item.applyEnd)
  })).filter(item => item.endDay >= today || item.applyDay >= today)
    .sort((first, second) => first.startDay - second.startDay);
}

function eventMatches(item, today, now) {
  if (eventFilter === "free") return item.free === true;
  if (eventFilter === "apply") return applyOpen(item, today);
  if (eventFilter === "tickets") {
    return eventOpenings(item).some(opening => opening.label === "티켓 오픈" && opensLater(opening, today, now));
  }
  if (eventFilter === "local") return item.sido === profile.sido;
  return true;
}

function openingLine(opening, today, now) {
  const time = opening.time === null ? "" : " " + koreanTime.format(opening.time);
  const status = opensLater(opening, today, now)
    ? statusText(dDay(opening.day - today, "오늘 열림")) : null;
  return el("span", "row-meta opening", opening.label + " " + dateLabel(opening.day) + time,
    status ? " · " : null, status);
}

function eventRow(item, today, now) {
  const price = item.free ? el("span", "price", "무료") : el("span", "row-meta", item.price);
  const deadline = Number.isFinite(item.applyDay)
    ? el("span", "row-meta", "신청 마감 " + dateLabel(item.applyDay) + (item.applyEndTime ? " " + item.applyEndTime : ""))
    : null;
  return rowControl(item, "row event-row", emoji(item.emoji), el("span", "row-text",
    el("span", "row-title", item.title), el("span", "row-sub", item.venue),
    el("span", "row-meta", periodLabel(item.startDay, item.endDay)), price, deadline,
    ...eventOpenings(item).map(opening => openingLine(opening, today, now)), sampleLabel(item)));
}

function renderEvents(today, now) {
  const filters = el("div", "filters");
  filters.setAttribute("role", "group");
  filters.setAttribute("aria-label", "공연 필터");
  for (const [key, label] of Object.entries(eventFilters)) {
    const chip = button(label, "chip", () => {
      eventFilter = key;
      render({ focusFilter: key });
    });
    chip.dataset.filter = key;
    chip.setAttribute("aria-pressed", String(eventFilter === key));
    filters.append(chip);
  }
  const rows = upcomingEvents(today).filter(item => eventMatches(item, today, now))
    .sort((a, b) => eventFilter === "apply" ? a.applyDay - b.applyDay : 0)  // 신청 가능은 마감 빠른 순
    .map(item => eventRow(item, today, now));
  const missingRegion = eventFilter === "local" && (!profile.sido || profile.sido === "모름");
  const results = missingRegion
    ? el("div", "state", el("p", null, "지역을 설정하면 가까운 공연을 볼 수 있어요."),
      button("지역 설정", "quiet-button text-button", openProfile))
    : cardList(rows, "조건에 맞는 공연이 없어요.");
  return [pageHead("공연"), filters, dataNotice(eventDataKeys), results];
}

// 시트 · 상세 정보와 프로필은 같은 하단 대화상자를 사용한다.
const sheet = document.querySelector("#sheet");
let sheetOpener = null;

function showSheet(title, context, ...body) {
  if (!sheet.open) sheetOpener = document.activeElement;
  const heading = el("h2", null, title);
  heading.id = "sheet-title";
  heading.tabIndex = -1;
  sheet.replaceChildren(el("div", "sheet-head", button("닫기", "quiet-button", () => sheet.close())),
    el("div", "sheet-intro", heading, context), ...body);
  if (!sheet.open) sheet.showModal();
  sheet.scrollTop = 0;
  heading.focus({ preventScroll: true });
}

function showDetail(icon, title, sample, details, url, { linkLabel = "공식 안내 보기", note = null } = {}) {
  const label = sampleLabel({ sample });
  const list = el("dl", null, ...details.filter(([, content]) => content)
    .map(([term, content]) => el("div", "sheet-section", el("dt", null, term), el("dd", null, content))));
  const link = officialLink(url, linkLabel, "action");
  const context = label && note ? el("div", "heading-line", label, note) : label ?? note;
  showSheet(el("span", "detail-title", emoji(icon), title), context, list,
    link ? el("div", "sheet-actions", link) : null);
}

sheet.addEventListener("close", () => {
  const fallback = document.getElementById(sheetOpener?.id) ?? document.querySelector("#profile-button");
  (sheetOpener?.isConnected ? sheetOpener : fallback)?.focus({ preventScroll: true });
  sheetOpener = null;
});
sheet.addEventListener("click", event => {
  if (event.target !== sheet) return;
  const bounds = sheet.getBoundingClientRect();
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top) sheet.close();
});

// 라우터 · 해시 탭과 공통 화면 요소를 관리한다.
const main = document.querySelector("#main");
const tabLinks = [...document.querySelectorAll(".tab-inner a")];
const views = { today: renderToday, picks: renderPicks, benefits: renderBenefits, taxes: renderTaxes, events: renderEvents };

function el(tag, className, ...children) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.append(...children.filter(child => child != null));
  return node;
}

function button(label, className, action) {
  const node = el("button", className, label);
  node.type = "button";
  node.addEventListener("click", action);
  return node;
}

function emoji(value) {
  const node = el("span", "row-icon", value || "📌");
  node.setAttribute("aria-hidden", "true");
  return node;
}

function officialLink(url, label, className) {
  if (typeof url !== "string" || !/^https:\/\//i.test(url)) return null;
  const node = el("a", className, label);
  node.href = url;
  node.target = "_blank";
  node.rel = "noopener noreferrer";
  return node;
}

function sampleLabel(item) {
  return item.sample ? el("span", "sample", "예시 데이터") : null;
}

function statusText(status) {
  const countdown = status.startsWith("D-") || status === "오늘 마감" || status === "오늘 열림";
  return el("span", countdown ? "status countdown" : "status", status);
}

function rowControl(item, className, ...content) {
  const control = item.open ? button("", className, item.open) : officialLink(item.url, null, className);
  const row = control ?? el("div", className);
  row.append(...content.filter(child => child != null));
  return row;
}

function pageHead(title, description, action) {
  return el("header", "page-head", el("div", "heading-line", el("h1", null, title), action), description);
}

function listing(rows) {
  return el("ul", "perforated", ...rows.map(row => el("li", null, row)));
}

function cardList(rows, empty) {
  return rows.length ? el("div", "card list-card", listing(rows)) : el("p", "state", empty);
}

function render(options = {}) {
  const hash = location.hash.slice(1);
  const tab = Object.hasOwn(views, hash) ? hash : "today";
  const now = Date.now();
  const today = seoulDay(now);
  const previousScroll = options.retainControls ? main.querySelector(".months")?.scrollLeft : null;
  for (const link of tabLinks) {
    if (link.hash === "#" + (tab === "picks" ? "today" : tab)) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  if (pendingLoads) {
    const notice = el("p", "state", "일정을 불러오는 중이에요.");
    notice.setAttribute("role", "status");
    main.replaceChildren(notice);
    return;
  }
  main.replaceChildren(...views[tab](today, now).filter(node => node != null));
  const months = main.querySelector(".months");
  if (months) {
    const month = months.querySelector('[aria-current="date"]');
    months.scrollLeft = previousScroll ?? month.offsetLeft - months.offsetLeft;
  }
  if (options.focusMonth) main.querySelector('[data-month="' + options.focusMonth + '"]')?.focus({ preventScroll: true });
  if (options.focusFilter) main.querySelector('[data-filter="' + options.focusFilter + '"]')?.focus();
  if (options.focusMain) main.focus({ preventScroll: true });
}

let refreshTimer;
function scheduleRefresh() {
  clearTimeout(refreshTimer);
  const now = Date.now();
  const midnight = (seoulDay(now) + 1) * DAY_MS - SEOUL_OFFSET;
  const nextOpening = eventDataKeys.flatMap(key => data[key].flatMap(eventOpenings)).map(opening => opening.time)
    .filter(time => time > now).reduce((soonest, time) => Math.min(soonest, time), midnight);
  refreshTimer = setTimeout(() => {
    render();
    scheduleRefresh();
  }, nextOpening - now + 20);
}

document.querySelector("#profile-button").addEventListener("click", openProfile);
window.addEventListener("hashchange", () => {
  if (location.hash !== "#benefits") benefitSortByDeadline = false;
  window.scrollTo(0, 0);
  render({ focusMain: true });
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    render();
    scheduleRefresh();
  }
});
loadData();

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("./sw.js").catch(error => console.warn("오프라인 기능을 시작할 수 없어요.", error));
}

// 설치 · 크롬이 설치를 허락하면 바로 설치 창을 띄우고, 아니면 방법을 보여 준다.
let installPrompt = null;
const installButton = document.querySelector("#install-button");
const installed = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
installButton.hidden = installed;
addEventListener("beforeinstallprompt", event => { event.preventDefault(); installPrompt = event; });
addEventListener("appinstalled", () => { installButton.hidden = true; installPrompt = null; });
installButton.addEventListener("click", async () => {
  if (installPrompt) {
    installPrompt.prompt();
    await installPrompt.userChoice.catch(() => {});
    installPrompt = null;
    return;
  }
  const ios = /iPhone|iPad|iPod/.test(navigator.userAgent);
  const steps = ios ? ["사파리 아래쪽 공유 버튼을 눌러요", "‘홈 화면에 추가’를 눌러요"]
    : ["크롬 오른쪽 위 점 세 개 메뉴를 눌러요", "‘앱 설치’ 또는 ‘홈 화면에 추가’를 눌러요"];
  showSheet("앱으로 설치", el("p", null, "카카오톡이나 삼성 인터넷에서 열었다면 크롬으로 다시 열어 주세요."),
    el("ol", "install-steps", ...steps.map(step => el("li", null, step))));
});

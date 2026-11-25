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
const dataKeys = ["benefits", "taxes", "events", "tips"];
const data = { benefits: [], taxes: [], events: [], tips: [] };
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
  if (national !== null) return [...national, ...(local ?? [])];

  const samples = await readData("benefits");
  return [...samples.filter(item => {
    const sampleRegions = item.cond?.sido ?? [];
    return item.sample && (sampleRegions.length === 0 || (local === null && sampleRegions.includes(sido)));
  }), ...(local ?? [])];
}

async function loadData(keys = dataKeys) {
  const sido = benefitSido();
  pendingLoads++;
  render();
  const results = await Promise.allSettled(keys.map(key => key === "benefits" ? readBenefits(sido) : readData(key)));
  results.forEach((result, index) => {
    const key = keys[index];
    if (key === "benefits" && sido !== benefitSido()) return;
    if (result.status === "fulfilled") {
      data[key] = result.value;
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
const regions = [
  "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시",
  "울산광역시", "세종특별자치시", "경기도", "강원특별자치도", "충청북도", "충청남도",
  "전북특별자치도", "전라남도", "경상북도", "경상남도", "제주특별자치도"
];
const profileSteps = ["나이·지역", "가구·집", "일·차"];
let profile = readProfile();

function benefitSido() {
  return regions.includes(profile.sido) ? profile.sido : "";
}

function readProfile() {
  try {
    const saved = JSON.parse(localStorage.getItem(PROFILE_KEY));
    if (saved && typeof saved === "object" && !Array.isArray(saved)) return saved;
  } catch {
    // 저장소를 사용할 수 없으면 조건 없이 표시한다.
  }
  return {};
}

function hasProfile() {
  return Object.values(profile).some(value => value != null && value !== "" && value !== "모름");
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

function selectField(label, name, value, choices) {
  const select = el("select");
  select.name = name;
  const options = [["", "선택 안 함"], ...choices];
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
      selectField("주택 보유", "homeless", draft.homeless, [["true", "무주택"], ["false", "주택 보유"]]),
      selectField("가구 소득", "incomeBand", draft.incomeBand, [
        ["모름", "모름"], ["중위50이하", "중위소득 50% 이하"], ["중위100이하", "중위소득 100% 이하"],
        ["중위150이하", "중위소득 150% 이하"], ["그이상", "중위소득 150% 초과"]
      ])
    ];
  }
  return [
    selectField("일", "worker", draft.worker, ["직장인", "자영업", "프리랜서", "없음"]),
    selectField("자동차 보유", "car", draft.car, [["true", "있음"], ["false", "없음"]])
  ];
}

function updateDraft(form, draft) {
  for (const [key, raw] of new FormData(form)) {
    const value = raw.trim();
    if (!value) delete draft[key];
    else if (key === "birthYear") draft[key] = Number(value);
    else if (key === "car" || key === "homeless") draft[key] = value === "true";
    else draft[key] = value;
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

// 오늘 · 지원금, 세금, 공연의 가까운 일정을 한 장에 모은다.
function todayEntries(today, now) {
  const benefits = matchingBenefits(today).filter(item => item.deadline && item.endDay - today <= 14)
    .map(item => ({
      title: item.name, emoji: item.emoji, sample: item.sample, label: "지원금 마감",
      cond: item.cond,
      distance: item.endDay - today, status: dDay(item.endDay - today),
      open: () => openBenefit(item)
    }));
  const taxes = upcomingTaxes(today, true).filter(item => item.startDay - today <= 14).map(item => ({
    title: item.title, emoji: item.emoji, label: item.startDay > today ? "세금 시작" : "세금",
    distance: Math.max(0, (item.startDay > today ? item.startDay : item.endDay) - today),
    status: taxStatus(item, today), open: () => openTax(item)
  }));
  const events = upcomingEvents(today).flatMap(item => eventOpenings(item)
    .filter(opening => opensLater(opening, today, now) && opening.day - today <= 7)
    .map(opening => ({
      title: item.title, emoji: item.emoji, sample: item.sample, label: opening.label,
      distance: opening.day - today, status: dDay(opening.day - today, "오늘 열림"), url: item.url
    })));
  return [...benefits, ...taxes, ...events].sort((first, second) => first.distance - second.distance);
}

function todayRow(item, lead) {
  const status = statusText(item.status);
  const title = el("span", "row-title", item.title);
  const label = el("span", "row-meta", item.label);
  if (lead) {
    return rowControl(item, "row bill-lead", status,
      el("span", "row-text", el("span", "lead-title", emoji(item.emoji), title), label,
        conditionLabel(item), sampleLabel(item)));
  }
  return rowControl(item, "row", emoji(item.emoji),
    el("span", "row-text", title, label, conditionLabel(item), sampleLabel(item)), status);
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

function renderToday(today, now) {
  const items = todayEntries(today, now);
  const date = el("time", null, koreanDate.format(dayDate(today)));
  date.dateTime = dayDate(today).toISOString().slice(0, 10);
  const bill = el("section", "card bill",
    el("h2", null, "이번 주 챙길 것 ", el("span", null, items.length + "가지")),
    items.length ? listing(items.map((item, index) => todayRow(item, index === 0)))
      : el("p", "state", "다가오는 일정이 없어요."));
  return [pageHead("오늘", el("p", null, date)),
    dataNotice(dataKeys), el("div", "stack", bill, tipCard(today))];
}

// 지원금 · 시군구와 나이를 확인한다.
function benefitMatches(item, today) {
  if (item.sigungu && profile.sigungu && item.sigungu !== profile.sigungu) return false;
  const cond = item.cond ?? {};
  if (!Number.isInteger(profile.birthYear) || profile.birthYear <= 0) return true;
  const age = dateParts(today)[0] - profile.birthYear;
  return (cond.ageMin == null || age >= cond.ageMin) && (cond.ageMax == null || age <= cond.ageMax);
}

function conditionLabel(item) {
  const { ageMin, ageMax, ...other } = item.cond ?? {};
  return Object.values(other).some(value => Array.isArray(value) ? value.length > 0 : value != null && value !== "")
    ? el("span", "sample", "조건 확인 필요") : null;
}

function matchingBenefits(today) {
  return data.benefits.map(item => ({
    ...item, endDay: item.deadline ? dayNumber(item.deadline) : Infinity
  })).filter(item => item.endDay >= today && benefitMatches(item, today))
    .sort((first, second) => first.endDay - second.endDay || first.name.localeCompare(second.name, "ko"));
}

function openBenefit(item) {
  const deadline = item.deadline ? dateLabel(item.endDay) : "상시 신청";
  showDetail(item.emoji, item.name, item.sample, [
    ["지원 내용", item.summary], ["지원 금액", item.amount], ["대상", item.target],
    ["신청 기한", deadline], ["신청 방법", item.how], ["담당 기관", item.org]
  ], item.url);
}

function renderBenefits(today) {
  const items = matchingBenefits(today);
  const edit = button("내 조건 바꾸기", "quiet-button text-button", openProfile);
  edit.id = "benefit-profile-button";
  const rows = items.map(item => rowControl({ open: () => openBenefit(item) }, "row", emoji(item.emoji),
    el("span", "row-text", el("span", "row-title", item.name), el("span", "row-sub", item.amount),
      el("span", "row-meta", item.org), conditionLabel(item), sampleLabel(item)),
    statusText(item.deadline ? dDay(item.endDay - today) : "상시")));
  return [pageHead("지원금", hasProfile() ? null : el("p", null, "내 조건을 설정하면 맞는 지원금을 볼 수 있어요."), edit),
    dataNotice(["benefits"]), cardList(rows, "조건에 맞는 지원금이 없어요.")];
}

// 세금 · 전년도에서 이어지는 기간과 다음 해 시작일을 함께 계산한다.
const taxWho = { all: "누구나", worker: "직장인", car: "자동차 보유자", owner: "주택 보유자", business: "사업자" };
let taxMonth = null;

function taxMatches(item) {
  if (item.who === "car") return profile.car !== false;
  if (item.who === "owner") return profile.homeless !== true;
  const worker = profile.worker;
  if (!["직장인", "자영업", "프리랜서", "없음"].includes(worker)) return true;
  if (item.who === "worker") return worker === "직장인";
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
const eventFilters = { all: "전체", free: "무료", tickets: "티켓 오픈", local: "내 지역" };
let eventFilter = "all";

function eventOpenings(item) {
  return [
    { label: "티켓 오픈", opening: openingDate(item.ticketOpen ?? item.ticket_open) },
    { label: "신청 시작", opening: openingDate(item.applyOpen ?? item.apply_open) }
  ].filter(entry => entry.opening).map(({ label, opening }) => ({ label, ...opening }));
}

function upcomingEvents(today) {
  return data.events.map(item => ({ ...item, startDay: dayNumber(item.start), endDay: dayNumber(item.end) }))
    .filter(item => item.endDay >= today).sort((first, second) => first.startDay - second.startDay);
}

function eventMatches(item, today, now) {
  if (eventFilter === "free") return item.free === true;
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
  return rowControl(item, "row event-row", emoji(item.emoji), el("span", "row-text",
    el("span", "row-title", item.title), el("span", "row-sub", item.venue),
    el("span", "row-meta", periodLabel(item.startDay, item.endDay)), price,
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
    .map(item => eventRow(item, today, now));
  const missingRegion = eventFilter === "local" && (!profile.sido || profile.sido === "모름");
  const results = missingRegion
    ? el("div", "state", el("p", null, "지역을 설정하면 가까운 공연을 볼 수 있어요."),
      button("지역 설정", "quiet-button text-button", openProfile))
    : cardList(rows, "조건에 맞는 공연이 없어요.");
  return [pageHead("공연"), filters, dataNotice(["events"]), results];
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

function showDetail(icon, title, sample, details, url) {
  const label = sampleLabel({ sample });
  const list = el("dl", null, ...details.filter(([, content]) => content)
    .map(([term, content]) => el("div", "sheet-section", el("dt", null, term), el("dd", null, content))));
  const link = officialLink(url, "공식 안내 보기", "action");
  showSheet(el("span", "detail-title", emoji(icon), title), label, list,
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
const views = { today: renderToday, benefits: renderBenefits, taxes: renderTaxes, events: renderEvents };

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
  return el("span", status.startsWith("D-") ? "status countdown" : "status", status);
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
    if (link.hash === "#" + tab) link.setAttribute("aria-current", "page");
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
  const nextOpening = data.events.flatMap(eventOpenings).map(opening => opening.time)
    .filter(time => time > now).reduce((soonest, time) => Math.min(soonest, time), midnight);
  refreshTimer = setTimeout(() => {
    render();
    scheduleRefresh();
  }, nextOpening - now + 20);
}

document.querySelector("#profile-button").addEventListener("click", openProfile);
window.addEventListener("hashchange", () => {
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

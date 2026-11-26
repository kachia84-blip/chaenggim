"use strict";

const scope = new URL(self.registration.scope);
const cachePrefix = "chaenggim:" + scope.pathname + ":";
const cacheName = cachePrefix + "v13";
const shell = [
  "./", "./index.html", "./style.css", "./app.js", "./manifest.json", "./icons/icon.svg",
  "./fonts/fonts.css", "./fonts/pretendard.woff2",
  "./icons/icon-192.png", "./icons/icon-512.png", "./icons/maskable-512.png", "./icons/apple-touch-icon.png"
];
const jsonFiles = ["benefits", "events", "taxes", "tips", "dormant", "picks", "meta"].map(name => "./data/" + name + ".json");
const nationalBenefits = "./data/benefits/전국.json";
const seoulEvents = "./data/seoul_events.json";
const shellPaths = new Set(shell.map(path => new URL(path, scope).pathname));

self.addEventListener("install", event => {
  event.waitUntil(caches.open(cacheName).then(async cache => {
    const reload = path => new Request(new URL(path, scope), { cache: "reload" });
    await cache.addAll([...shell, ...jsonFiles].map(reload));
    // 첫 수집 전에도 설치할 수 있도록 수집 결과 파일은 있을 때만 캐시한다.
    await Promise.all([nationalBenefits, seoulEvents].map(path => cache.add(reload(path)).catch(() => {})));
  }).then(() => self.skipWaiting()));
});

self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(names => Promise.all(names
    .filter(name => name.startsWith(cachePrefix) && name !== cacheName)
    .map(name => caches.delete(name))
  )).then(() => self.clients.claim()));
});

async function networkFirst(request) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (!response.ok) return await cache.match(request) ?? response;
    // 캐시 쓰기가 실패해도 온라인 응답은 전달한다.
    await cache.put(request, response.clone()).catch(() => {});
    return response;
  } catch {
    return await cache.match(request) ?? Response.error();
  }
}

async function cacheFirst(request, path) {
  const cache = await caches.open(cacheName);
  return await cache.match(new URL(path, scope)) ?? fetch(request);
}

// 토스페이스 조각(tf*.woff2)은 쓰는 이모지에 따라 바뀌므로 처음 받을 때 캐시에 넣는다.
async function fontFirst(request) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(request);
  if (hit) return hit;
  const response = await fetch(request);
  if (response.ok) await cache.put(request, response.clone()).catch(() => {});
  return response;
}

self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== scope.origin || !url.pathname.startsWith(scope.pathname)) return;
  const relative = url.pathname.slice(scope.pathname.length);
  if (/^data\/(?:benefits\/)?[^/]+\.json$/.test(relative)) {
    event.respondWith(networkFirst(request));
  } else if (shellPaths.has(url.pathname)) {
    event.respondWith(cacheFirst(request, relative));
  } else if (/^fonts\/tf\d+\.woff2$/.test(relative)) {
    event.respondWith(fontFirst(request));
  }
});

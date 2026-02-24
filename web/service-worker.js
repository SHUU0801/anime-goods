/* ============================================================
   Service Worker — Anime Goods Tracker PWA
   オフライン対応・キャッシュ戦略
   ============================================================ */

const CACHE_NAME = "anime-goods-tracker-v4";
const STATIC_ASSETS = [
    "/",
    "/index.html",
    "/style.css",
    "/app.js",
    "/manifest.json"
];

// インストール時: 静的アセットをキャッシュ
self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS);
        })
    );
    self.skipWaiting();
});

// アクティベート時: 古いキャッシュを削除
self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((k) => k !== CACHE_NAME)
                    .map((k) => caches.delete(k))
            )
        )
    );
    self.clients.claim();
});

// フェッチ戦略:
// - /api/* → Network First（常に最新データを取得）
// - その他  → Cache First（高速表示）
self.addEventListener("fetch", (event) => {
    const url = new URL(event.request.url);

    if (url.pathname.startsWith("/api/")) {
        // Network First
        event.respondWith(
            fetch(event.request)
                .then((res) => {
                    const clone = res.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                    return res;
                })
                .catch(() => caches.match(event.request))
        );
    } else {
        // Cache First
        event.respondWith(
            caches.match(event.request).then(
                (cached) => cached || fetch(event.request)
            )
        );
    }
});

// Push通知受信
self.addEventListener("push", (event) => {
    const data = event.data ? event.data.json() : {};
    const title = data.title || "新着グッズ情報";
    const options = {
        body: data.body || "新しい情報が追加されました",
        icon: "/icon-192.png",
        badge: "/icon-192.png",
        vibrate: [200, 100, 200],
        data: { url: data.url || "/" },
        actions: [
            { action: "view", title: "確認する" },
            { action: "dismiss", title: "閉じる" }
        ]
    };
    event.waitUntil(self.registration.showNotification(title, options));
});

// 通知クリック
self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    if (event.action === "view") {
        const url = event.notification.data.url;
        event.waitUntil(clients.openWindow(url));
    }
});

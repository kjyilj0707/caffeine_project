// 카페인 측정기 알림 수신기 (서비스 워커, Step 4-5)
// 브라우저·앱을 닫아도 핸드폰이 서버(send-push)가 보낸 알림을 받아 화면에 띄운다. 오프라인 저장은 하지 않는다.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = { title: "☕ 카페인 측정기", body: "" };
  try { data = { ...data, ...event.data.json() }; } catch (e) { if (event.data) data.body = event.data.text(); }
  event.waitUntil(self.registration.showNotification(data.title, {
    body: data.body,
    tag: data.tag,                       // 같은 알림이 두 번 와도 하나만 보이게
    icon: "icons/icon-192.png",
    badge: "icons/icon-192.png",
    data: { url: data.url || self.registration.scope },
  }));
});

// 알림을 누르면 열려 있는 앱으로, 없으면 새로 연다
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification.data?.url || self.registration.scope;
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
    for (const w of windows) if (w.url.startsWith(self.registration.scope)) return w.focus();
    return self.clients.openWindow(url);
  }));
});

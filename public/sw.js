self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let payload = {};
  if (event.data) {
    try {
      payload = event.data.json();
    } catch (error) {
      payload = { body: event.data.text() };
    }
  }
  const title = payload.title || "SmartAlert nearby emergency";
  const vehicleNames = { car: "car", bike: "bike", lorry: "lorry" };
  const targetVehicle = vehicleNames[payload.target_vehicle];
  const options = {
    body: `${payload.body || "A nearby emergency alert was reported."}${targetVehicle ? ` Notified vehicle: ${targetVehicle}.` : ""}`,
    icon: "/icon.svg",
    badge: "/icon.svg",
    tag: payload.alert_id || "smartalert-alert",
    renotify: true,
    requireInteraction: payload.priority === "critical",
    data: { url: payload.url || "/" },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "/", self.location.origin).href;
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
    const existing = windows.find((client) => client.url === target && "focus" in client);
    return existing ? existing.focus() : self.clients.openWindow(target);
  }));
});

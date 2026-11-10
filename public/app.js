const DEFAULT_LOCATION = { latitude: 12.9716, longitude: 77.5946, place: "Bengaluru demo location" };
const LANGUAGE_NAMES = {
  en: "English", hi: "हिन्दी · Hindi", ta: "தமிழ் · Tamil", te: "తెలుగు · Telugu",
  bn: "বাংলা · Bengali", mr: "मराठी · Marathi", gu: "ગુજરાતી · Gujarati",
  kn: "ಕನ್ನಡ · Kannada", ml: "മലയാളം · Malayalam", pa: "ਪੰਜਾਬੀ · Punjabi", ur: "اردو · Urdu",
};
const CATEGORY_LABELS = {
  accident: "Road accident", breakdown: "Vehicle breakdown", fire: "Fire",
  medical: "Medical emergency", roadblock: "Road blockage", vehicle: "Vehicle-specific road alert",
  other: "Community emergency",
};
const icons = { accident: "⚠", breakdown: "⌁", fire: "♨", medical: "✚", roadblock: "⊘", vehicle: "🚘", other: "!" };
const VEHICLE_NAMES = { car: "Car", bike: "Bike", lorry: "Lorry" };
const VOICE_SAMPLE = {
  en: "SmartAlert voice preview. Please slow down and stay safe.",
  hi: "स्मार्ट अलर्ट आवाज़ का नमूना। कृपया धीरे चलें और सुरक्षित रहें।",
  ta: "ஸ்மார்ட் அலர்ட் குரல் மாதிரி. மெதுவாகச் சென்று பாதுகாப்பாக இருங்கள்.",
  te: "స్మార్ట్ అలర్ట్ వాయిస్ నమూనా. దయచేసి నెమ్మదిగా వెళ్లి సురక్షితంగా ఉండండి.",
};
function storedNumber(key, fallback) {
  const stored = localStorage.getItem(key);
  if (stored === null || stored.trim() === "") return fallback;
  const value = Number(stored);
  return Number.isFinite(value) ? value : fallback;
}
const clientId = localStorage.getItem("smartalert-client-id") || (
  crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`
);
localStorage.setItem("smartalert-client-id", clientId);

let profile = {
  client_id: clientId,
  name: localStorage.getItem("smartalert-name") || "Neighbor",
  role: localStorage.getItem("smartalert-role") || "resident",
  vehicle_type: localStorage.getItem("smartalert-vehicle-type") || "",
  phone_number: localStorage.getItem("smartalert-phone-number") || "",
  phone_alerts_enabled: localStorage.getItem("smartalert-phone-alerts-enabled") === "true",
  locale: localStorage.getItem("smartalert-locale") || (navigator.language || "en").split("-")[0],
  latitude: storedNumber("smartalert-latitude", DEFAULT_LOCATION.latitude),
  longitude: storedNumber("smartalert-longitude", DEFAULT_LOCATION.longitude),
  radius_km: storedNumber("smartalert-radius", 10),
  place: localStorage.getItem("smartalert-place") || DEFAULT_LOCATION.place,
};
let alerts = [];
let voices = [];
let voiceEnabled = localStorage.getItem("smartalert-voice-enabled") === "true";
let pushSubscription = null;
let eventSource;
let toastTimer;

const $ = (selector) => document.querySelector(selector);
function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 3600);
}

async function api(path, options = {}) {
  if (!["http:", "https:"].includes(location.protocol)) {
    throw new Error(
      "The SmartAlert backend cannot run from a file preview. Start the server with .\\run.ps1, then open http://127.0.0.1:8000/."
    );
  }
  const endpoint = new URL(path, location.href);
  if (endpoint.origin !== location.origin) {
    throw new Error("SmartAlert API requests must use the same origin as the app.");
  }
  let response;
  try {
    response = await fetch(endpoint, {
      ...options,
      headers: { Accept: "application/json", "Content-Type": "application/json", ...(options.headers || {}) },
    });
  } catch (error) {
    throw new Error(`Could not reach ${endpoint.href}. Start the SmartAlert server and use its address. ${error.message}`);
  }
  const contentType = response.headers.get("content-type") || "";
  const responseText = await response.text();
  let data;
  try {
    data = contentType.includes("application/json") ? JSON.parse(responseText) : null;
  } catch {
    data = null;
  }
  if (!data || typeof data !== "object") {
    const detail = responseText.trim().replace(/\s+/g, " ").slice(0, 100);
    throw new Error(
      `${endpoint.href} returned HTTP ${response.status} ${response.statusText}, not SmartAlert JSON` +
      `${detail ? `: "${detail}"` : ""}. Open http://127.0.0.1:8000/ and start SmartAlert with .\\run.ps1.`
    );
  }
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status}) at ${endpoint.href}`);
  return data;
}

function showConnectionHelp(title, message, targetUrl = "http://127.0.0.1:8000/") {
  $("#connection-help-title").textContent = title;
  $("#connection-help-message").textContent = message;
  $("#connection-help-link").href = targetUrl;
  $("#connection-help").hidden = false;
  $("#connection-label").textContent = "Setup needed";
  showToast(message);
}

function persistProfile() {
  localStorage.setItem("smartalert-name", profile.name);
  localStorage.setItem("smartalert-role", profile.role);
  localStorage.setItem("smartalert-vehicle-type", profile.vehicle_type);
  localStorage.setItem("smartalert-phone-number", profile.phone_number || "");
  localStorage.setItem("smartalert-phone-alerts-enabled", String(profile.phone_alerts_enabled));
  localStorage.setItem("smartalert-locale", profile.locale);
  localStorage.setItem("smartalert-latitude", String(profile.latitude));
  localStorage.setItem("smartalert-longitude", String(profile.longitude));
  localStorage.setItem("smartalert-radius", String(profile.radius_km));
  localStorage.setItem("smartalert-place", profile.place || "");
}

async function saveProfile() {
  const data = await api("/api/profile", { method: "POST", body: JSON.stringify(profile) });
  Object.assign(profile, data.profile);
  persistProfile();
  renderProfile();
  loadNearby().catch((error) => console.error("Could not load nearby volunteers:", error));
}

function renderProfile() {
  $("#greeting-name").textContent = profile.name || "Neighbor";
  $("#coverage-radius").textContent = `${profile.radius_km} km`;
  $("#location-label").textContent = profile.place || `${profile.latitude.toFixed(4)}, ${profile.longitude.toFixed(4)}`;
  $("#name-input").value = profile.name;
  $("#role-select").value = profile.role;
  $("#vehicle-type-select").value = profile.vehicle_type;
  $("#profile-phone").value = profile.phone_number || "";
  $("#phone-alerts-enabled").checked = profile.phone_alerts_enabled;
  $("#vehicle-profile-status").textContent = profile.vehicle_type
    ? `Your profile can receive alerts targeted to ${VEHICLE_NAMES[profile.vehicle_type]}.`
    : "Choose a vehicle type to receive targeted vehicle alerts.";
  const profileLanguage = profile.locale.toLowerCase().split("-")[0];
  $("#profile-language").value = LANGUAGE_NAMES[profileLanguage] ? profileLanguage : "en";
  $("#latitude-input").value = profile.latitude;
  $("#longitude-input").value = profile.longitude;
  $("#profile-radius").value = profile.radius_km;
  $("#profile-radius-value").textContent = profile.radius_km;
  $("#language-select").value = profile.locale;
}

async function loadDashboard() {
  const data = await api(`/api/bootstrap?client_id=${encodeURIComponent(clientId)}`);
  alerts = data.alerts || [];
  renderAlerts();
  renderStats();
}

async function loadNearby() {
  const data = await api(`/api/nearby?client_id=${encodeURIComponent(clientId)}`);
  const volunteers = Array.isArray(data.volunteers) ? data.volunteers : [];
  $("#volunteer-count").textContent = volunteers.length;
  $("#volunteer-badge").textContent = `${volunteers.length} online`;
  const list = $("#volunteer-list");
  list.replaceChildren();
  if (!volunteers.length) {
    const empty = document.createElement("p");
    empty.className = "empty-inline";
    empty.textContent = "No volunteers have shared their location nearby yet.";
    list.append(empty);
    return;
  }
  for (const volunteer of volunteers) {
    const row = document.createElement("div");
    row.className = "volunteer-row";
    const avatar = document.createElement("span");
    avatar.className = "volunteer-avatar";
    avatar.textContent = volunteer.name.slice(0, 1).toUpperCase();
    const identity = document.createElement("span");
    identity.className = "volunteer-identity";
    const name = document.createElement("strong");
    name.textContent = volunteer.name;
    const role = document.createElement("small");
    role.textContent = `${volunteer.role === "responder" ? "Responder" : "Volunteer"} · ${volunteer.distance_km} km away`;
    identity.append(name, role);
    row.append(avatar, identity);
    list.append(row);
  }
}

function formatTime(dateString) {
  const date = new Date(dateString);
  return Number.isNaN(date.getTime()) ? "Just now" : new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(date);
}

function renderStats() {
  const active = alerts.filter((alert) => alert.status !== "resolved");
  $("#active-count").textContent = active.length;
  const verified = alerts.filter((alert) => alert.status === "verified").length;
  $("#response-time").textContent = verified;
  renderMapMarkers(active);
}

function renderMapMarkers(items) {
  const markers = $("#map-markers");
  markers.replaceChildren();
  const radius = Math.max(Number(profile.radius_km) || 10, 1);
  items.slice(0, 14).forEach((alert, index) => {
    const dx = (Number(alert.longitude) - Number(profile.longitude)) * 111 * Math.cos(profile.latitude * Math.PI / 180);
    const dy = (Number(alert.latitude) - Number(profile.latitude)) * 111;
    const left = Math.max(12, Math.min(88, 50 + dx / radius * 32));
    const top = Math.max(15, Math.min(80, 50 - dy / radius * 32));
    const marker = document.createElement("button");
    marker.type = "button";
    marker.className = `map-marker ${alert.priority === "critical" ? "critical" : ""}`;
    marker.style.left = `${left}%`;
    marker.style.top = `${top}%`;
    marker.title = `${CATEGORY_LABELS[alert.category] || "Alert"} · ${alert.place}`;
    marker.textContent = icons[alert.category] || "!";
    marker.setAttribute("aria-label", marker.title);
    marker.addEventListener("click", () => document.getElementById(`alert-${alert.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }));
    markers.append(marker);
  });
}

function renderAlerts() {
  const list = $("#alert-list");
  const filter = $("#alert-filter").value;
  const filtered = alerts.filter((alert) => {
    if (filter === "critical") return alert.priority === "critical";
    if (filter === "unverified") return alert.status === "unverified";
    return true;
  });
  list.replaceChildren();
  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = alerts.length ? "No alerts match this filter." : "No nearby alerts. Your community is looking good.";
    list.append(empty);
    renderStats();
    return;
  }
  for (const alert of filtered) {
    const card = document.createElement("article");
    card.id = `alert-${alert.id}`;
    card.className = `alert-card ${alert.priority === "critical" ? "is-critical" : ""}`;
    const icon = document.createElement("span");
    icon.className = `alert-icon icon-${alert.category}`;
    icon.textContent = icons[alert.category] || "!";
    const body = document.createElement("div");
    body.className = "alert-content";
    const heading = document.createElement("div");
    heading.className = "alert-title-row";
    const title = document.createElement("h3");
    title.textContent = alert.title || CATEGORY_LABELS[alert.category] || "Community alert";
    const badge = document.createElement("span");
    badge.className = `priority-badge priority-${alert.priority}`;
    badge.textContent = alert.priority === "critical" ? "Critical" : alert.priority === "high" ? "High" : "Notice";
    heading.append(title, badge);
    if (alert.target_vehicle && alert.target_vehicle !== "all") {
      const target = document.createElement("span");
      target.className = "vehicle-target";
      target.textContent = `For ${VEHICLE_NAMES[alert.target_vehicle] || alert.target_vehicle}`;
      heading.append(target);
    }
    const message = document.createElement("p");
    message.textContent = alert.message || "";
    const detail = document.createElement("p");
    detail.className = "alert-detail";
    detail.textContent = alert.details || "";
    const meta = document.createElement("div");
    meta.className = "alert-meta";
    meta.textContent = `${alert.place} · ${formatTime(alert.created_at)} · ${alert.reporter_name || "Neighbor"}`;
    body.append(heading, message);
    if (alert.details) body.append(detail);
    body.append(meta);
    const actions = document.createElement("div");
    actions.className = "alert-actions";
    const status = document.createElement("span");
    status.className = alert.status === "verified" ? "verified-label" : "unverified-label";
    status.textContent = alert.status === "verified" ? "✓ Verified" : "Unverified";
    const directions = document.createElement("a");
    directions.className = "text-button";
    directions.target = "_blank";
    directions.rel = "noopener noreferrer";
    directions.href = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${alert.latitude},${alert.longitude}`)}`;
    directions.textContent = "Directions ↗";
    actions.append(status, directions);
    if (alert.status !== "verified") {
      const verify = document.createElement("button");
      verify.className = "text-button verify-button";
      verify.type = "button";
      verify.textContent = "Verify";
      verify.addEventListener("click", () => verifyAlert(alert.id));
      actions.append(verify);
    }
    card.append(icon, body, actions);
    list.append(card);
  }
  renderStats();
}

async function verifyAlert(id) {
  const button = document.querySelector(`#alert-${CSS.escape(id)} .verify-button`);
  if (button) button.disabled = true;
  try {
    const data = await api(`/api/alerts/${encodeURIComponent(id)}/verify`, {
      method: "POST", body: JSON.stringify({ verified: true, client_id: clientId }),
    });
    alerts = alerts.map((item) => item.id === id ? data.alert : item);
    renderAlerts();
    showToast("Alert marked as verified.");
  } catch (error) {
    showToast(error.message);
    if (button) button.disabled = false;
  }
}

function connectRealtime() {
  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/api/events?client_id=${encodeURIComponent(clientId)}`);
  eventSource.onopen = () => {
    $("#connection-label").textContent = "Live";
    $(".live-indicator").classList.add("is-live");
  };
  eventSource.onerror = () => {
    $("#connection-label").textContent = "Reconnecting";
    $(".live-indicator").classList.remove("is-live");
  };
  eventSource.addEventListener("alert", (event) => {
    const alert = JSON.parse(event.data);
    if (alerts.some((item) => item.id === alert.id)) return;
    alerts.unshift(alert);
    alerts = alerts.slice(0, 60);
    renderAlerts();
    showToast(`${alert.title}: ${alert.place}`);
    announceAlert(alert);
    if (!pushSubscription && "Notification" in window && Notification.permission === "granted") {
      const targetName = VEHICLE_NAMES[alert.target_vehicle];
      new Notification(alert.title, {
        body: `${alert.message}${targetName ? ` Notified vehicle: ${targetName}.` : ""}`,
        icon: "/icon.svg",
        tag: alert.id,
      });
    }
    loadNearby().catch((error) => console.error("Could not refresh nearby volunteers:", error));
  });
  eventSource.addEventListener("alert-update", (event) => {
    const updated = JSON.parse(event.data);
    alerts = alerts.map((item) => item.id === updated.id ? { ...item, ...updated } : item);
    renderAlerts();
  });
}

function announceAlert(alert) {
  if (!voiceEnabled || !("speechSynthesis" in window)) return;
  const utterance = new SpeechSynthesisUtterance([alert.title, alert.message, alert.details].filter(Boolean).join(". "));
  const language = alert.language || "en";
  utterance.lang = language;
  const voice = voices.find((item) => item.lang.toLowerCase().startsWith(language));
  if (voice) utterance.voice = voice;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

function refreshVoiceOptions() {
  if (!("speechSynthesis" in window)) {
    $("#voice-status").textContent = "Speech playback is not available in this browser.";
    $("#voice-button").disabled = true;
    return;
  }
  voices = window.speechSynthesis.getVoices();
  const select = $("#language-select");
  const selected = profile.locale;
  const availableLocales = [...new Set(voices.map((voice) => voice.lang).filter(Boolean))].sort();
  select.replaceChildren();
  const preferred = new Set(["en", "hi", "ta", "te", selected, ...availableLocales]);
  for (const locale of preferred) {
    const base = locale.toLowerCase().split("-")[0];
    const option = document.createElement("option");
    option.value = locale;
    const hasVoice = voices.some((voice) => voice.lang.toLowerCase().startsWith(base));
    const isVoicePack = ["hi", "ta", "te"].includes(base);
    const voiceLabel = isVoicePack ? (hasVoice ? "voice available" : "install device voice for speech") : "";
    const translationLabel = LANGUAGE_NAMES[base] ? "" : " · English alert text";
    option.textContent = `${LANGUAGE_NAMES[base] || locale} · ${locale}${translationLabel}${voiceLabel ? ` · ${voiceLabel}` : ""}`;
    select.append(option);
  }
  select.value = [...select.options].some((option) => option.value === selected) ? selected : (select.options[0]?.value || "en");
  updateVoicePackStatus();
  updateVoiceButton();
}

function updateVoicePackStatus() {
  const language = $("#language-select").value.toLowerCase().split("-")[0];
  if (!["hi", "ta", "te"].includes(language)) {
    $("#voice-pack-status").textContent = "Tamil, Hindi and Telugu alert phrases are included. Spoken audio requires the matching device voice.";
    return;
  }
  const name = LANGUAGE_NAMES[language];
  const hasVoice = voices.some((voice) => voice.lang.toLowerCase().startsWith(language));
  $("#voice-pack-status").textContent = hasVoice
    ? `${name} alert phrases and a matching speech voice are available on this device.`
    : `${name} alert phrases are included. Install/enable a ${name} speech voice in your device settings for native pronunciation.`;
}

function previewVoice() {
  if (!("speechSynthesis" in window)) {
    showToast("Speech playback is not supported by this browser.");
    return;
  }
  const language = $("#language-select").value.toLowerCase().split("-")[0];
  const utterance = new SpeechSynthesisUtterance(VOICE_SAMPLE[language] || VOICE_SAMPLE.en);
  utterance.lang = language;
  const voice = voices.find((item) => item.lang.toLowerCase().startsWith(language));
  if (voice) utterance.voice = voice;
  else if (["hi", "ta", "te"].includes(language)) {
    showToast(`Install a ${LANGUAGE_NAMES[language]} system speech voice for the best voice preview.`);
  }
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

async function enablePush() {
  const button = $("#push-button");
  button.disabled = true;
  try {
    if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
      throw new Error("Push notifications are not supported by this browser.");
    }
    const permission = await Notification.requestPermission();
    if (permission !== "granted") throw new Error("Notification permission was not granted.");
    const registration = await navigator.serviceWorker.ready;
    const { public_key: publicKey } = await api("/api/push/vapid-public-key");
    if (!publicKey) {
      $("#push-status").textContent = "Browser notifications enabled while the app is open. Configure VAPID on the server for background push.";
      $("#push-button").textContent = "Browser notifications enabled";
      showToast("Background push is not configured on this server.");
      return;
    }
    pushSubscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey),
    });
    await api("/api/push/subscribe", {
      method: "POST",
      body: JSON.stringify({ client_id: clientId, subscription: pushSubscription }),
    });
    $("#push-status").textContent = "Background push notifications are enabled on this device.";
    button.textContent = "Push notifications enabled";
    showToast("Push notifications enabled.");
  } catch (error) {
    $("#push-status").textContent = error.message;
    showToast(error.message);
  } finally {
    button.disabled = false;
  }
}

function urlBase64ToUint8Array(value) {
  const padding = "=".repeat((4 - value.length % 4) % 4);
  const base64 = (value + padding).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
}

async function reportAlert(event) {
  event.preventDefault();
  const submit = $("#submit-alert");
  const isDirect = Boolean($("#recipient-phone").value.trim());
  $("#form-error").textContent = "";
  submit.disabled = true;
  submit.textContent = "Sending…";
  try {
    const data = await api("/api/alerts", {
      method: "POST",
      body: JSON.stringify({
        reporter_id: clientId,
        category: $("#category-select").value,
        priority: $("#priority-select").value,
        target_vehicle: $("#category-select").value === "vehicle" ? $("#target-vehicle").value : "all",
        place: $("#place-input").value,
        details: $("#details-input").value,
        recipient_phone: $("#recipient-phone").value,
        custom_message: $("#custom-message").value,
        latitude: profile.latitude,
        longitude: profile.longitude,
        radius_km: Number($("#radius-input").value),
      }),
    });
    alerts.unshift(data.alert);
    alerts = alerts.slice(0, 60);
    renderAlerts();
    $("#report-dialog").close();
    $("#alert-form").reset();
    $("#radius-input").value = profile.radius_km;
    $("#radius-value").textContent = profile.radius_km;
    updateDirectAlertControls();
    showToast(isDirect
      ? `Direct alert sent to ${data.delivery.recipient_count} registered profile(s).`
      : `Alert sent to ${data.delivery.recipient_count} nearby profile(s).`);
  } catch (error) {
    $("#form-error").textContent = error.message;
  } finally {
    submit.disabled = false;
    updateDirectAlertControls();
  }
}

function updateDirectAlertControls() {
  const isDirect = Boolean($("#recipient-phone").value.trim());
  $("#radius-input").disabled = isDirect;
  $("#radius-input").hidden = isDirect;
  $("#radius-input").previousElementSibling.hidden = isDirect;
  $("#submit-alert").textContent = isDirect ? "Send direct alert" : "Send nearby alert";
}

function useLocation() {
  if (!navigator.geolocation) {
    showToast("Location is not available in this browser.");
    return;
  }
  $("#locate-button").disabled = true;
  navigator.geolocation.getCurrentPosition(async (position) => {
    const previousProfile = { ...profile };
    profile.latitude = position.coords.latitude;
    profile.longitude = position.coords.longitude;
    profile.place = "Current location";
    try {
      await saveProfile();
      await loadDashboard();
      showToast("Your location has been updated.");
    } catch (error) {
      profile = previousProfile;
      renderProfile();
      showToast(error.message);
    } finally {
      $("#locate-button").disabled = false;
    }
  }, (error) => {
    $("#locate-button").disabled = false;
    showToast(error.code === 1 ? "Location permission was denied." : "Could not determine your location.");
  }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 });
}

function openProfile() {
  $("#profile-error").textContent = "";
  $("#profile-dialog").showModal();
}

function updateVoiceButton() {
  const button = $("#voice-button");
  button.replaceChildren();
  const icon = document.createElement("span");
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = "◖))";
  button.append(icon, document.createTextNode(voiceEnabled ? " Voice alerts enabled" : " Enable automatic voice"));
  $("#voice-status").textContent = voiceEnabled
    ? "New alerts will be spoken while this app is open."
    : "Tap to allow spoken alerts while this app is open.";
}

async function restorePushSubscription() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
  const registration = await navigator.serviceWorker.ready;
  pushSubscription = await registration.pushManager.getSubscription();
  if (pushSubscription) {
    $("#push-button").textContent = "Push notifications enabled";
    $("#push-status").textContent = "Background push notifications are enabled on this device.";
  }
}

$("#sos-button").addEventListener("click", () => {
  $("#form-error").textContent = "";
  $("#report-dialog").showModal();
});
$("#settings-button").addEventListener("click", openProfile);
$("#edit-location").addEventListener("click", openProfile);
$("#locate-button").addEventListener("click", useLocation);
$("#push-button").addEventListener("click", enablePush);
$("#alert-form").addEventListener("submit", reportAlert);
$("#alert-filter").addEventListener("change", renderAlerts);
$("#category-select").addEventListener("change", (event) => {
  $("#vehicle-target-wrap").hidden = event.target.value !== "vehicle";
});
$("#recipient-phone").addEventListener("input", (event) => {
  updateDirectAlertControls();
});
$("#radius-input").addEventListener("input", (event) => $("#radius-value").textContent = event.target.value);
$("#profile-radius").addEventListener("input", (event) => $("#profile-radius-value").textContent = event.target.value);
$("#vehicle-type-select").addEventListener("change", (event) => {
  const type = event.target.value;
  $("#vehicle-profile-status").textContent = type
    ? `Your profile can receive alerts targeted to ${VEHICLE_NAMES[type]}.`
    : "Choose a vehicle type to receive targeted vehicle alerts.";
});
$("#voice-preview-button").addEventListener("click", previewVoice);
$("#language-select").addEventListener("change", async (event) => {
  updateVoicePackStatus();
  const previousLocale = profile.locale;
  profile.locale = event.target.value;
  persistProfile();
  try {
    await saveProfile();
  } catch (error) {
    profile.locale = previousLocale;
    persistProfile();
    renderProfile();
    refreshVoiceOptions();
    showToast(error.message);
  }
});
$("#voice-button").addEventListener("click", () => {
  if (!("speechSynthesis" in window)) return;
  voiceEnabled = !voiceEnabled;
  localStorage.setItem("smartalert-voice-enabled", String(voiceEnabled));
  updateVoiceButton();
  if (voiceEnabled) {
    const confirmation = new SpeechSynthesisUtterance("Voice alerts enabled.");
    confirmation.lang = "en";
    window.speechSynthesis.speak(confirmation);
  } else {
    window.speechSynthesis.cancel();
  }
});
$("#profile-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#profile-error").textContent = "";
  const saveButton = $("#profile-form button[type=submit]");
  saveButton.disabled = true;
  const previousProfile = { ...profile };
  try {
    profile.name = $("#name-input").value.trim() || "Neighbor";
    profile.role = $("#role-select").value;
    profile.vehicle_type = $("#vehicle-type-select").value;
    profile.phone_number = $("#profile-phone").value.trim();
    profile.phone_alerts_enabled = $("#phone-alerts-enabled").checked;
    profile.locale = $("#profile-language").value;
    profile.latitude = Number($("#latitude-input").value);
    profile.longitude = Number($("#longitude-input").value);
    profile.radius_km = Number($("#profile-radius").value);
    profile.place = null;
    await saveProfile();
    $("#profile-dialog").close();
    showToast("Your profile and alert radius are saved.");
  } catch (error) {
    profile = previousProfile;
    renderProfile();
    $("#profile-error").textContent = error.message;
  } finally {
    saveButton.disabled = false;
  }
});
$("#volunteer-join").addEventListener("click", async () => {
  const previousRole = profile.role;
  profile.role = "volunteer";
  try {
    await saveProfile();
    showToast("You are now listed as a nearby volunteer.");
  } catch (error) {
    profile.role = previousRole;
    renderProfile();
    showToast(error.message);
  }
});
document.querySelectorAll("[data-close]").forEach((button) => {
  button.addEventListener("click", () => document.getElementById(button.dataset.close).close());
});
$("#radius-input").value = profile.radius_km;
$("#radius-value").textContent = profile.radius_km;
renderProfile();
refreshVoiceOptions();
if ("speechSynthesis" in window) window.speechSynthesis.onvoiceschanged = refreshVoiceOptions;
if (window.isSecureContext && ["http:", "https:"].includes(location.protocol) && "serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch((error) => {
  console.error("Service worker registration failed:", error);
  $("#push-status").textContent = "Background notification setup failed.";
});
(async () => {
  if (!window.isSecureContext || !["http:", "https:"].includes(location.protocol)) {
    showConnectionHelp(
      "You opened the static file, not the running app",
      "Start SmartAlert with .\\run.ps1, then open the local server address. The API, live alerts, and push do not work from a file URL."
    );
    return;
  }
  try {
    const health = await api("/api/health");
    if (health.status !== "ok") {
      throw new Error(`Unexpected health status from ${location.origin}: ${health.status || "missing"}`);
    }
    await saveProfile();
    await loadDashboard();
    try {
      await restorePushSubscription();
    } catch (error) {
      console.error("Could not restore push subscription:", error);
    }
    connectRealtime();
    window.setInterval(() => loadNearby().catch((error) => console.error("Could not refresh nearby volunteers:", error)), 30000);
  } catch (error) {
    showConnectionHelp(
      "SmartAlert backend not found at this address",
      `${error.message} Check the server window, then open the matching SmartAlert URL.`
    );
  }
})();

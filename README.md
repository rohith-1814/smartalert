# SmartAlert

SmartAlert is a runnable, browser-based prototype for location-aware community and automotive emergency alerts. It demonstrates one report flowing to nearby profiles through a live event stream, localized browser push notifications, and spoken announcements for active clients.

## Architecture

```text
Android demo app / Browser PWA
  ├─ Dashboard, profile, geolocation, map-like radar, volunteer view
  ├─ EventSource (SSE) ───────────────┐
  ├─ Service worker ← Web Push ───────┤
  ├─ SpeechSynthesis (active page)    │
  └─ Enrolled one-tap SOS ────────────┤
                                      ▼
                         Python HTTP API (server.py)
                           ├─ Profile and alert validation
                           ├─ Idempotent demo SOS incident log
                           ├─ Haversine radius matching
                           ├─ Contextual message/localization catalog
                           ├─ Live per-client event queues
                           ├─ Optional pywebpush delivery
                           └─ JSON persistence (local prototype)
```

### Production architecture target

The prototype keeps the backend in one process so it can be run locally. For a production deployment, split the same boundaries into independently scalable services:

1. **Identity and API gateway:** verified accounts, device registration, responder/admin roles, consent, request throttling, and abuse reporting.
2. **Alert intake and verification:** authenticated, idempotent alert submission; risk/priority rules; human verification and escalation; immutable audit events.
3. **Geospatial directory:** PostgreSQL/PostGIS for consented user/vehicle locations and indexed radius queries; short location-retention windows and access controls.
4. **Event fan-out:** a durable queue partitioned by geographic cell/category, with retry and dead-letter handling; deduplicated delivery to connected clients and push workers (Web Push, FCM, and APNs).
5. **Localization and voice:** reviewed locale catalogs plus a translation-provider adapter; client-native TTS for active use and platform notification/audio policies for background use. Critical alerts must remain deliverable if translation or TTS fails.
6. **Operations and response:** role-gated live map, alert lifecycle, responder assignment, traffic/closure feeds, delivery metrics, and incident audit history.

The message generator should remain a replaceable, bounded component: use deterministic safety templates as the fallback, require human review for high-impact AI output, and do not send precise locations or personal details to an external model without an explicit privacy/security review.

### Implemented flows

- **Community and automotive reporting:** road accident, vehicle breakdown, fire, medical emergency, road blockage, and other emergency categories; priority, details, location, and a configurable 1–25 km report radius.
- **Vehicle notifications:** profiles can register a car, bike/motorcycle, or lorry/truck. Vehicle-specific road alerts can target all vehicle types or only one class; the server applies that class filter to live alerts, history, and push subscriptions.
- **Direct mobile-number alerts:** a profile can opt in with an international-format mobile number (`+` and country code). A sender can write a custom message and address it to that number; delivery is restricted to registered profiles that enabled direct alerts for the exact number, using the existing live-app and configured browser push channels. The number is not included in the alert. This prototype does not verify number ownership or send SMS/calls.
- **Android one-tap SOS demo:** the native Android client supports one-time profile enrollment and a prominent in-app SOS button. A tap posts an idempotent critical alert to the SmartAlert backend and records a local demo incident. The app and server explicitly report that no emergency dispatch center or hospital was contacted. Android reserves the physical power key for system functions; ordinary apps cannot reliably bind to it.
- **Recipient matching:** the server filters registered profiles by the reporter's radius using the Haversine distance, then applies the optional vehicle-class filter. The recipient's own radius is used to find nearby volunteers/responders.
- **Realtime and push delivery:** Server-Sent Events deliver to connected nearby clients. Web Push subscriptions are saved and delivered through `pywebpush` when VAPID keys are configured. Without VAPID, in-app realtime alerts still work, and browser notifications are used while the page is open if permission is granted.
- **Voice announcements:** the active page can automatically speak incoming alerts with the browser's SpeechSynthesis API. Tamil, Hindi, and Telugu localized alert phrase packs and voice previews are included, and installed browser/system voices are detected. The built-in message catalog also includes English, Bengali, Marathi, Gujarati, Kannada, Malayalam, Punjabi, and Urdu. Uncatalogued locales use English text; extend `TRANSLATIONS` in `server.py` to add reviewed translations. The project includes localized speech text, not downloadable audio recordings: users need a matching Tamil/Hindi/Telugu voice installed in their operating system/browser for native pronunciation.
- **Response coordination:** nearby volunteers and responders, alert verification, priority filters, and directions links are included. Message generation is a deterministic contextual rules engine, not a hosted AI model; it can be replaced with a reviewed AI/translation provider without changing the alert transport.
- **Persistence:** profiles, subscriptions, and the latest 300 alerts are stored in `smartalert-state.json` alongside the server.

## Run locally

Requires Python 3.9 or later. From this directory:

```powershell
.\run.ps1
```

The launcher creates `.venv`, installs the optional push dependency, and starts the server. If PowerShell blocks scripts, run `powershell -ExecutionPolicy Bypass -File .\run.ps1`. Alternatively, start it manually with Python 3.9 or later:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe server.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Opening `public/index.html` directly only provides a static UI preview; profile saves, alerts, and notifications require the server. The preview now explains how to start SmartAlert and prevents file-based API requests. The default profile uses a clearly labeled Bengaluru demo location; use **Use my location** or edit the profile to set an actual location. Open the app in two browser profiles on the same machine with different locations to test nearby delivery. To test from another device, set `$env:SMARTALERT_HOST = "0.0.0.0"` before starting `server.py` and expose it only through a trusted HTTPS reverse proxy; browser geolocation, service workers, and push require localhost or HTTPS.

Choose a vehicle class under **Profile & location** to receive vehicle-targeted alerts. To send a targeted notification, report a **Vehicle-specific road alert** and choose cars, bikes, or lorries. This is profile-based vehicle identification; SmartAlert does not infer a vehicle from a camera or license plate.

Run the backend unit tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

### Android demo app

Open the project root in Android Studio with JDK 17+ and Android SDK Platform 35 installed, then run the `app` configuration. The Android Gradle project is under `android/app`. No Android SDK/JDK was available in the environment where this project was assembled, so build and device validation still need to be done in Android Studio.

The app's default API URL, `http://10.0.2.2:8000`, is for the Android emulator talking to the development server on the same computer. On a physical phone, configure the computer's reachable LAN URL and allow the local development connection through its firewall. Keep the server on a trusted network; the prototype uses plain HTTP and has no authentication. Do not expose it publicly.

Enroll once with location permission and then tap **SEND DEMO SOS** to send one critical community alert. It uses the latest location saved at enrollment/update; update enrollment after moving. A network/server response confirms only that the demo backend recorded the report and attempted community fan-out. It is not a request for real-world help. Always call the local emergency number directly.

### Enable background Web Push

Install the requirements, then generate a VAPID key pair:

```powershell
python generate_vapid.py
$env:VAPID_PUBLIC_KEY = "<the printed public key>"
$env:VAPID_PRIVATE_KEY = "vapid_private.pem"
$env:VAPID_CLAIMS_EMAIL = "mailto:admin@example.com"
python server.py
```

Use the printed public key in the server environment and keep the private PEM secret and out of source control. For a deployed service, serve the site over HTTPS, configure a real operator contact, and use a production database and secret manager. The app must be opened once on each device to register its browser push subscription.

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Server and push configuration status |
| `GET` | `/api/bootstrap?client_id=…` | Recent alerts visible to this profile |
| `GET` | `/api/nearby?client_id=…` | Nearby online volunteers/responders |
| `GET` | `/api/events?client_id=…` | Per-profile Server-Sent Events stream |
| `GET` | `/api/push/vapid-public-key` | Browser subscription public key |
| `POST` | `/api/profile` | Register/update profile, location, and optional opted-in mobile number |
| `POST` | `/api/alerts` | Validate, persist, localize, and distribute a nearby alert; optional `recipient_phone` plus `custom_message` sends only to opted-in registered profiles for that number |
| `POST` | `/api/emergency/sos` | Record an idempotent critical community SOS in the local demo incident log; never contacts an agency or hospital |
| `POST` | `/api/alerts/{id}/verify` | Mark an alert verified and update live clients |
| `POST` | `/api/push/subscribe` | Save a Web Push subscription |

## Important limitations before real-world use

This is a local MVP, not an emergency dispatch service. The SOS endpoint only records a local demo event and sends the ordinary community alert; it does not contact a dispatch center, ambulance, or hospital. It has no user authentication, authorization, mobile-number verification, moderation, abuse prevention, responder integration, or production-grade database. Do not expose it to the public internet or rely on it for emergencies. Real dispatch integration requires the relevant jurisdiction, an authorized agency/hospital interface, operational agreements, end-to-end testing, monitoring, and verified delivery/failure handling. Before any real-world deployment, add verified identity and phone-number ownership, rate limiting and abuse controls, alert verification/escalation workflows, consent and location-retention controls, encrypted storage, audit logging, monitoring, and emergency-service integrations. Real SMS/call delivery also requires a configured provider, recipient consent, and applicable regulatory compliance.

Web browsers generally block audible autoplay until a person enables voice playback through a user gesture. Speech synthesis works while the page is active; a service worker can display a background push notification but cannot reliably start spoken audio while the app is suspended. Keep local emergency-number guidance visible and never imply that SmartAlert contacts emergency services.

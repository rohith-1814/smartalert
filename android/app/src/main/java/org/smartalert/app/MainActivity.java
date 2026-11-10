package org.smartalert.app;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.location.Location;
import android.location.LocationManager;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final int LOCATION_PERMISSION_REQUEST = 7;
    private static final String PREFERENCES = "smartalert_demo";
    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private SharedPreferences preferences;
    private EditText serverInput;
    private EditText nameInput;
    private TextView statusView;
    private Button enrollButton;
    private Button sosButton;
    private boolean enrolling;
    private boolean sendingSos;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        preferences = getSharedPreferences(PREFERENCES, MODE_PRIVATE);
        buildScreen();
        renderEnrollmentState();
    }

    private void buildScreen() {
        int horizontal = dp(22);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(horizontal, dp(28), horizontal, dp(28));

        TextView title = text("SmartAlert", 30, 0xFF17243B, true);
        content.addView(title);
        TextView subtitle = text("Community emergency demo", 16, 0xFF66738A, false);
        content.addView(subtitle, marginParams(0, dp(5), 0, dp(20)));

        TextView safety = text(
                "DEMO ONLY — this app does not contact an emergency dispatch center or hospital. " +
                        "For real emergencies, call your local emergency number directly.",
                14, 0xFF7D431F, false);
        safety.setBackgroundColor(0xFFFFF2E2);
        safety.setPadding(dp(14), dp(14), dp(14), dp(14));
        content.addView(safety, marginParams(0, 0, 0, dp(20)));

        content.addView(text("Enroll this device once", 19, 0xFF17243B, true));
        content.addView(text(
                "Enrollment saves your profile and the latest available location to the configured demo server.",
                13, 0xFF66738A, false), marginParams(0, dp(5), 0, dp(12)));

        serverInput = field("Demo server URL", preferences.getString("server", "http://10.0.2.2:8000"));
        content.addView(serverInput, marginParams(0, 0, 0, dp(9)));
        nameInput = field("Your name", preferences.getString("name", ""));
        content.addView(nameInput, marginParams(0, 0, 0, dp(12)));

        enrollButton = new Button(this);
        enrollButton.setText("Enroll device");
        content.addView(enrollButton, marginParams(0, 0, 0, dp(16)));
        enrollButton.setOnClickListener(view -> enroll());

        sosButton = new Button(this);
        sosButton.setText("SEND DEMO SOS");
        sosButton.setTextSize(20);
        sosButton.setTextColor(0xFFFFFFFF);
        sosButton.setBackgroundTintList(android.content.res.ColorStateList.valueOf(0xFFC63831));
        sosButton.setMinHeight(dp(88));
        sosButton.setContentDescription("Send one-touch SmartAlert demo SOS");
        content.addView(sosButton, marginParams(0, 0, 0, dp(8)));
        sosButton.setOnClickListener(view -> sendSos());

        content.addView(text(
                "One tap sends a critical community alert to the demo server and records a local demo-dispatch event. " +
                        "No call, SMS, hospital, or emergency-service dispatch is made.",
                12, 0xFF66738A, false), marginParams(0, 0, 0, dp(16)));

        statusView = text("", 14, 0xFF30415B, false);
        statusView.setPadding(dp(12), dp(12), dp(12), dp(12));
        statusView.setBackgroundColor(0xFFF0F3F8);
        content.addView(statusView, marginParams(0, 0, 0, dp(16)));

        TextView locationHelp = text(
                "This demo uses the last known phone location. Permit location access and make sure device location is enabled before enrollment. " +
                        "The physical power key is reserved by Android; use the in-app SOS button.",
                12, 0xFF7B8798, false);
        content.addView(locationHelp);

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.addView(content);
        setContentView(scroll);
    }

    private void enroll() {
        if (enrolling) return;
        if (!hasLocationPermission()) {
            requestPermissions(new String[] {
                    Manifest.permission.ACCESS_COARSE_LOCATION,
                    Manifest.permission.ACCESS_FINE_LOCATION
            }, LOCATION_PERMISSION_REQUEST);
            return;
        }
        String baseUrl = normalizedBaseUrl(serverInput.getText().toString());
        String name = nameInput.getText().toString().trim();
        if (baseUrl == null) {
            setStatus("Enter a valid server URL, such as http://10.0.2.2:8000.", true);
            return;
        }
        if (name.isEmpty()) {
            setStatus("Enter your name before enrolling.", true);
            return;
        }
        Location location = lastKnownLocation();
        if (location == null) {
            setStatus("No location is available yet. Turn on device location, open a maps app, then try enrollment again.", true);
            return;
        }

        JSONObject profile = new JSONObject();
        try {
            profile.put("client_id", clientId);
            profile.put("name", name);
            profile.put("role", "resident");
            profile.put("vehicle_type", "");
            profile.put("phone_alerts_enabled", false);
            profile.put("locale", getResources().getConfiguration().getLocales().get(0).getLanguage());
            profile.put("latitude", location.getLatitude());
            profile.put("longitude", location.getLongitude());
            profile.put("radius_km", 10);
            profile.put("place", "Android device");
        } catch (Exception error) {
            setStatus("Could not prepare enrollment: " + error.getMessage(), true);
            return;
        }

        enrolling = true;
        updateButtons();
        setStatus("Saving your demo enrollment…", false);
        network.execute(() -> {
            try {
                JSONObject result = postJson(baseUrl, "/api/profile", profile);
                JSONObject savedProfile = result.getJSONObject("profile");
                preferences.edit()
                        .putString("server", baseUrl)
                        .putString("name", name)
                        .putString("client_id", clientId)
                        .putString("latitude", String.valueOf(savedProfile.getDouble("latitude")))
                        .putString("longitude", String.valueOf(savedProfile.getDouble("longitude")))
                        .putBoolean("enrolled", true)
                        .apply();
                runOnUiThread(() -> {
                    enrolling = false;
                    renderEnrollmentState();
                    setStatus("Enrolled. Your one-tap SOS is ready. This is a demo and does not contact emergency services.", false);
                });
            } catch (Exception error) {
                runOnUiThread(() -> {
                    enrolling = false;
                    updateButtons();
                    setStatus("Enrollment failed: " + error.getMessage(), true);
                });
            }
        });
    }

    private void sendSos() {
        if (sendingSos || !preferences.getBoolean("enrolled", false)) return;
        if (!hasLocationPermission()) {
            setStatus("Location permission is off. Re-enable it and enroll this device before sending the demo SOS.", true);
            return;
        }
        String baseUrl = normalizedBaseUrl(preferences.getString("server", ""));
        String clientId = preferences.getString("client_id", "");
        Location currentLocation = lastKnownLocation();
        String latitude = currentLocation == null
                ? preferences.getString("latitude", "")
                : String.valueOf(currentLocation.getLatitude());
        String longitude = currentLocation == null
                ? preferences.getString("longitude", "")
                : String.valueOf(currentLocation.getLongitude());
        if (baseUrl == null || clientId.isEmpty() || latitude.isEmpty() || longitude.isEmpty()) {
            setStatus("Enrollment details are incomplete. Enroll this device again.", true);
            return;
        }
        preferences.edit().putString("latitude", latitude).putString("longitude", longitude).apply();

        String requestId = preferences.getString("pending_request_id", "");
        if (requestId.isEmpty()) {
            requestId = UUID.randomUUID().toString();
            preferences.edit().putString("pending_request_id", requestId).apply();
        }
        JSONObject request = new JSONObject();
        try {
            request.put("client_id", clientId);
            request.put("request_id", requestId);
            request.put("latitude", Double.parseDouble(latitude));
            request.put("longitude", Double.parseDouble(longitude));
        } catch (Exception error) {
            setStatus("Could not prepare SOS: " + error.getMessage(), true);
            return;
        }

        sendingSos = true;
        updateButtons();
        setStatus("Sending SOS to the SmartAlert demo server…", false);
        network.execute(() -> {
            try {
                JSONObject result = postJson(baseUrl, "/api/emergency/sos", request);
                JSONObject incident = result.getJSONObject("incident");
                preferences.edit().remove("pending_request_id").apply();
                runOnUiThread(() -> {
                    sendingSos = false;
                    updateButtons();
                    setStatus(
                            "Demo SOS recorded at " + incident.optString("place", "your enrolled location") +
                                    ". Nearby profile deliveries: " +
                                    result.getJSONObject("delivery").optInt("recipient_count") +
                                    ". NO emergency service or hospital was contacted.",
                            true);
                });
            } catch (Exception error) {
                runOnUiThread(() -> {
                    sendingSos = false;
                    updateButtons();
                    setStatus("SOS was not confirmed by the demo server. Check your connection before retrying. " +
                            error.getMessage(), true);
                });
            }
        });
    }

    private JSONObject postJson(String baseUrl, String path, JSONObject body) throws Exception {
        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) new URL(baseUrl + path).openConnection();
            connection.setRequestMethod("POST");
            connection.setConnectTimeout(8000);
            connection.setReadTimeout(8000);
            connection.setDoOutput(true);
            connection.setRequestProperty("Accept", "application/json");
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);
            connection.setFixedLengthStreamingMode(bytes.length);
            try (OutputStream output = connection.getOutputStream()) {
                output.write(bytes);
            }
            int status = connection.getResponseCode();
            InputStream stream = status >= 200 && status < 300
                    ? connection.getInputStream() : connection.getErrorStream();
            StringBuilder response = new StringBuilder();
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(stream, StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) response.append(line);
            }
            JSONObject data = new JSONObject(response.toString());
            if (status < 200 || status >= 300) {
                throw new IllegalStateException(data.optString("error", "Server returned HTTP " + status));
            }
            return data;
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private Location lastKnownLocation() {
        if (!hasLocationPermission()) return null;
        LocationManager manager = (LocationManager) getSystemService(Context.LOCATION_SERVICE);
        Location best = null;
        try {
            for (String provider : manager.getProviders(true)) {
                Location candidate = manager.getLastKnownLocation(provider);
                if (candidate != null && (best == null || candidate.getTime() > best.getTime())) best = candidate;
            }
        } catch (SecurityException ignored) {
            return null;
        }
        return best;
    }

    private boolean hasLocationPermission() {
        return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
                checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == LOCATION_PERMISSION_REQUEST) {
            if (hasLocationPermission()) enroll();
            else setStatus("Location permission is needed to enroll and attach your location to alerts.", true);
        }
    }

    private void renderEnrollmentState() {
        boolean enrolled = preferences.getBoolean("enrolled", false);
        sosButton.setVisibility(enrolled ? View.VISIBLE : View.GONE);
        enrollButton.setText(enrolled ? "Update enrollment and location" : "Enroll device");
        if (enrolled) {
            setStatus("Enrolled as " + preferences.getString("name", "Neighbor") +
                    ". SOS uses the location saved during the latest enrollment.", false);
        }
        updateButtons();
    }

    private void updateButtons() {
        enrollButton.setEnabled(!enrolling && !sendingSos);
        sosButton.setEnabled(!sendingSos && preferences.getBoolean("enrolled", false));
        sosButton.setAlpha(sosButton.isEnabled() ? 1f : .65f);
    }

    private void setStatus(String message, boolean warning) {
        statusView.setText(message);
        statusView.setTextColor(warning ? 0xFF8A352F : 0xFF30415B);
    }

    private String normalizedBaseUrl(String value) {
        String base = value == null ? "" : value.trim().replaceAll("/+$", "");
        if (!base.startsWith("http://") && !base.startsWith("https://")) return null;
        if (base.contains("/api/")) return null;
        return base;
    }

    private EditText field(String hint, String value) {
        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setText(value);
        input.setHint(hint);
        input.setTextSize(15);
        input.setPadding(dp(12), dp(10), dp(12), dp(10));
        input.setBackgroundTintList(android.content.res.ColorStateList.valueOf(0xFF9BA8BA));
        return input;
    }

    private TextView text(String value, int size, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(color);
        if (bold) view.setTypeface(null, android.graphics.Typeface.BOLD);
        view.setGravity(Gravity.START);
        return view;
    }

    private LinearLayout.LayoutParams marginParams(int left, int top, int right, int bottom) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        params.setMargins(left, top, right, bottom);
        return params;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    @Override
    protected void onDestroy() {
        network.shutdownNow();
        super.onDestroy();
    }
}

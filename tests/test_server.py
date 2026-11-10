import os
import queue
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

import server


class SmartAlertTests(unittest.TestCase):
    def test_distance_is_zero_for_same_coordinates(self):
        self.assertAlmostEqual(server.distance_km(12.9, 77.5, 12.9, 77.5), 0)

    def test_distance_is_approximately_one_degree_of_latitude(self):
        self.assertAlmostEqual(server.distance_km(0, 0, 1, 0), 111.2, delta=0.5)

    def test_radius_matching_rejects_missing_coordinates(self):
        alert = {"latitude": 12.97, "longitude": 77.59, "radius_km": 10}
        self.assertFalse(server.profile_is_near({"latitude": None, "longitude": 77.59}, alert))

    def test_localization_uses_supported_language_and_safe_fallback(self):
        hindi = server.locale_messages("hi-IN", "accident", "MG Road")
        fallback = server.locale_messages("xx", "accident", "MG Road")
        self.assertEqual(hindi["language"], "hi")
        self.assertIn("MG Road", hindi["message"])
        self.assertEqual(fallback["language"], "en")
        self.assertIn("MG Road", fallback["message"])

    def test_regional_voice_packs_and_vehicle_labels_are_available(self):
        for language in ("hi", "ta", "te"):
            result = server.locale_messages(language, "vehicle", "MG Road", "bike")
            self.assertEqual(result["language"], language)
            self.assertIn(server.VEHICLE_LABELS[language]["bike"], result["title"])
            self.assertIn("MG Road", result["message"])

    def test_vehicle_alerts_match_only_the_selected_registered_vehicle(self):
        alert = {"target_vehicle": "bike"}
        self.assertTrue(server.vehicle_matches({"vehicle_type": "bike"}, alert))
        self.assertFalse(server.vehicle_matches({"vehicle_type": "car"}, alert))
        self.assertFalse(server.vehicle_matches({"vehicle_type": "lorry"}, alert))
        self.assertTrue(server.vehicle_matches({"vehicle_type": ""}, {"target_vehicle": "all"}))

    def test_phone_number_is_normalized_to_international_format(self):
        self.assertEqual(server.normalize_phone_number("+91 (98765) 43210"), "+919876543210")

    def test_phone_number_requires_a_country_code_and_valid_length(self):
        for value in ("9876543210", "+0 9876543210", "+91 123"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                server.normalize_phone_number(value)

    def test_create_alert_resolves_only_registered_opted_in_mobile_profiles(self):
        reporter = {"client_id": "reporter", "name": "Sender", "locale": "en"}
        state = {
            "profiles": {
                "reporter": reporter,
                "target": {
                    "phone_number": "+919876543210",
                    "phone_alerts_enabled": True,
                },
                "not-opted-in": {
                    "phone_number": "+919876543210",
                    "phone_alerts_enabled": False,
                },
            },
            "subscriptions": {},
            "alerts": [],
        }
        data = {
            "reporter_id": "reporter",
            "category": "other",
            "priority": "high",
            "latitude": 12.9716,
            "longitude": 77.5946,
            "radius_km": 10,
            "recipient_phone": "+91 (98765) 43210",
            "custom_message": "Please check the gate now.",
        }
        handler = object.__new__(server.SmartAlertHandler)
        handler.send_json = Mock()
        with ExitStack() as stack:
            stack.enter_context(patch.object(server, "state", state))
            stack.enter_context(patch.object(server, "save_state"))
            publish = stack.enter_context(patch.object(
                server, "publish_alert", return_value={"recipient_count": 1}
            ))
            handler.create_alert(data)

        alert = publish.call_args.args[0]
        self.assertEqual(alert["target_client_ids"], ["target"])
        self.assertEqual(alert["message"], data["custom_message"])
        status, response = handler.send_json.call_args.args
        self.assertEqual(status, 201)
        self.assertNotIn("target_client_ids", response["alert"])
        self.assertEqual(response["delivery"]["recipient_count"], 1)

    def test_one_tap_sos_creates_demo_only_incident_and_critical_alert(self):
        state = {
            "profiles": {
                "enrolled-user": {
                    "client_id": "enrolled-user",
                    "name": "Neighbor",
                    "locale": "en",
                    "place": "Demo location",
                    "radius_km": 10,
                },
            },
            "subscriptions": {},
            "alerts": [],
            "emergency_incidents": [],
        }
        handler = object.__new__(server.SmartAlertHandler)
        handler.send_json = Mock()
        data = {
            "client_id": "enrolled-user",
            "request_id": "280f01c6-b2f4-4b2f-b5e9-16de8e6e9a47",
            "latitude": 12.9716,
            "longitude": 77.5946,
        }
        delivery = {"nearby_recipients": 2, "recipient_count": 2}
        with ExitStack() as stack:
            stack.enter_context(patch.object(server, "state", state))
            stack.enter_context(patch.object(server, "save_state"))
            publish = stack.enter_context(patch.object(server, "publish_alert", return_value=delivery))
            handler.create_emergency_sos(data)

        alert = publish.call_args.args[0]
        self.assertEqual(alert["priority"], "critical")
        self.assertEqual(alert["category"], "medical")
        self.assertEqual(alert["id"], data["request_id"])
        self.assertEqual(state["emergency_incidents"][0]["status"], "demo_only")
        self.assertEqual(state["emergency_incidents"][0]["delivery"], delivery)
        status, response = handler.send_json.call_args.args
        self.assertEqual(status, 201)
        self.assertEqual(response["dispatch_status"], "demo_only")
        self.assertEqual(response["delivery"], delivery)

    def test_one_tap_sos_is_idempotent_for_a_retried_request(self):
        request_id = "280f01c6-b2f4-4b2f-b5e9-16de8e6e9a47"
        previous = {
            "request_id": request_id,
            "client_id": "enrolled-user",
            "delivery": {"recipient_count": 2},
        }
        state = {
            "profiles": {"enrolled-user": {"client_id": "enrolled-user"}},
            "emergency_incidents": [previous],
        }
        handler = object.__new__(server.SmartAlertHandler)
        handler.send_json = Mock()
        with patch.object(server, "state", state), patch.object(server, "publish_alert") as publish:
            handler.create_emergency_sos({
                "client_id": "enrolled-user",
                "request_id": request_id,
                "latitude": 12.9716,
                "longitude": 77.5946,
            })

        publish.assert_not_called()
        status, response = handler.send_json.call_args.args
        self.assertEqual(status, 200)
        self.assertEqual(response["incident"], previous)

    def test_one_tap_sos_requires_an_enrolled_profile_and_valid_coordinates(self):
        handler = object.__new__(server.SmartAlertHandler)
        handler.send_json = Mock()
        with patch.object(server, "state", {"profiles": {}, "emergency_incidents": []}):
            with self.assertRaisesRegex(ValueError, "Enroll this device"):
                handler.create_emergency_sos({
                    "client_id": "unknown",
                    "request_id": "280f01c6-b2f4-4b2f-b5e9-16de8e6e9a47",
                    "latitude": 12.9,
                    "longitude": 77.5,
                })

    def test_phone_targeted_alert_reaches_only_the_exact_registered_profile(self):
        targeted_queue = queue.Queue()
        nearby_queue = queue.Queue()
        profiles = {
            "reporter": {"latitude": 12.9716, "longitude": 77.5946, "locale": "en"},
            "target": {
                "latitude": 13.5,
                "longitude": 77.5946,
                "locale": "ta",
                "phone_number": "+919876543210",
                "phone_alerts_enabled": True,
            },
            "nearby": {"latitude": 12.98, "longitude": 77.5946, "locale": "en"},
        }
        alert = {
            "id": "direct-alert",
            "category": "other",
            "priority": "high",
            "target_vehicle": "all",
            "place": "MG Road",
            "message": "Please check the gate now.",
            "latitude": 12.9716,
            "longitude": 77.5946,
            "radius_km": 5,
            "reporter_id": "reporter",
            "target_client_ids": ["target"],
        }
        with ExitStack() as stack:
            stack.enter_context(patch.dict(server.state["profiles"], profiles, clear=True))
            stack.enter_context(patch.dict(server.state["subscriptions"], {}, clear=True))
            stack.enter_context(patch.dict(server.client_queues, {
                "target": {targeted_queue},
                "nearby": {nearby_queue},
                "reporter": {queue.Queue()},
            }, clear=True))
            stack.enter_context(patch.dict(os.environ, {"VAPID_PRIVATE_KEY": "", "VAPID_PUBLIC_KEY": ""}))
            delivery = server.publish_alert(alert)

        self.assertEqual(delivery["recipient_count"], 1)
        event_name, payload = targeted_queue.get_nowait()
        self.assertEqual(event_name, "alert")
        self.assertEqual(payload["message"], "Please check the gate now.")
        self.assertEqual(payload["language"], "ta")
        self.assertNotIn("target_client_ids", payload)
        self.assertTrue(nearby_queue.empty())

    def test_vehicle_alert_delivery_filters_the_geofenced_recipients(self):
        car_queue = queue.Queue()
        bike_queue = queue.Queue()
        profiles = {
            "reporter": {"latitude": 12.9716, "longitude": 77.5946, "locale": "en"},
            "car-user": {"latitude": 12.98, "longitude": 77.5946, "locale": "en", "vehicle_type": "car"},
            "bike-user": {"latitude": 12.98, "longitude": 77.5946, "locale": "ta", "vehicle_type": "bike"},
        }
        alert = {
            "id": "bike-alert",
            "category": "vehicle",
            "priority": "high",
            "place": "MG Road",
            "latitude": 12.9716,
            "longitude": 77.5946,
            "radius_km": 5,
            "reporter_id": "reporter",
            "target_vehicle": "bike",
        }
        with ExitStack() as stack:
            stack.enter_context(patch.dict(server.state["profiles"], profiles, clear=True))
            stack.enter_context(patch.dict(server.state["subscriptions"], {}, clear=True))
            stack.enter_context(patch.dict(server.client_queues, {
                "car-user": {car_queue},
                "bike-user": {bike_queue},
                "reporter": {queue.Queue()},
            }, clear=True))
            stack.enter_context(patch.dict(os.environ, {"VAPID_PRIVATE_KEY": "", "VAPID_PUBLIC_KEY": ""}))
            delivery = server.publish_alert(alert)

        self.assertEqual(delivery["nearby_recipients"], 1)
        event_name, payload = bike_queue.get_nowait()
        self.assertEqual(event_name, "alert")
        self.assertEqual(payload["language"], "ta")
        self.assertIn(server.VEHICLE_LABELS["ta"]["bike"], payload["title"])
        self.assertTrue(car_queue.empty())

    def test_alert_is_delivered_only_to_profiles_inside_report_radius(self):
        near_queue = queue.Queue()
        far_queue = queue.Queue()
        profiles = {
            "reporter": {
                "latitude": 12.9716, "longitude": 77.5946, "locale": "en",
            },
            "near": {
                "latitude": 12.98, "longitude": 77.5946, "locale": "hi",
            },
            "far": {
                "latitude": 13.5, "longitude": 77.5946, "locale": "en",
            },
        }
        alert = {
            "id": "test-alert",
            "category": "accident",
            "priority": "high",
            "place": "MG Road",
            "latitude": 12.9716,
            "longitude": 77.5946,
            "radius_km": 5,
            "reporter_id": "reporter",
        }
        with ExitStack() as stack:
            stack.enter_context(patch.dict(server.state["profiles"], profiles, clear=True))
            stack.enter_context(patch.dict(server.state["subscriptions"], {}, clear=True))
            stack.enter_context(patch.dict(server.client_queues, {
                "near": {near_queue},
                "far": {far_queue},
                "reporter": {queue.Queue()},
            }, clear=True))
            stack.enter_context(patch.dict(os.environ, {"VAPID_PRIVATE_KEY": ""}))
            delivery = server.publish_alert(alert)

        self.assertEqual(delivery["nearby_recipients"], 1)
        self.assertEqual(delivery["live_deliveries"], 1)
        event_name, payload = near_queue.get_nowait()
        self.assertEqual(event_name, "alert")
        self.assertEqual(payload["language"], "hi")
        self.assertEqual(payload["id"], "test-alert")
        self.assertTrue(far_queue.empty())


if __name__ == "__main__":
    unittest.main()

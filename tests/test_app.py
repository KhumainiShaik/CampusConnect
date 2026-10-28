import json
from html import escape
import unittest

from app import app, EVENTS


class CampusConnectTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_homepage_lists_events(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"CampusConnect", response.data)
        for event in EVENTS:
            self.assertIn(escape(event["title"], quote=False).encode(), response.data)

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_events_api_returns_event_list(self):
        response = self.client.get("/api/events")
        self.assertEqual(response.status_code, 200)
        events = json.loads(response.data)
        self.assertGreaterEqual(len(events), 1)
        self.assertTrue(all({"id", "title", "category", "date", "venue"} <= event.keys() for event in events))


if __name__ == "__main__":
    unittest.main()
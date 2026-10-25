"""Black-box HTTP contract tests plus independent database assertions."""
import concurrent.futures
import json
import sqlite3
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from tolling.server import create_server


class TollingAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = self.temp.name + "/test.sqlite3"
        self.server = create_server(self.database)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.payload = {"event_id": "evt-001", "plate": "DEMO123", "vehicle_class": "car", "occurred_at": "2026-01-01T12:00:00Z"}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, method="POST", path="/transactions", payload=None, raw=None, content_type="application/json"):
        body = raw if raw is not None else (json.dumps(payload).encode() if method == "POST" else None)
        request = Request(self.base + path, data=body, method=method, headers={"Content-Type": content_type})
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            self.assertTrue(response.headers["Content-Type"].startswith("application/json"))
            return response.status, json.load(response)

    def test_health(self):
        self.assertEqual(self.request("GET", "/health"), (200, {"status": "ok"}))

    def test_success_contract_and_sql_persistence(self):
        status, body = self.request(payload=self.payload)
        self.assertEqual(status, 201)
        self.assertFalse(body["replayed"])
        transaction = body["transaction"]
        self.assertEqual(set(transaction), {"id", "event_id", "plate", "vehicle_class", "occurred_at", "amount_cents"})
        self.assertEqual(transaction["amount_cents"], 250)
        self.assertIsInstance(transaction["id"], int)
        with sqlite3.connect(self.database) as conn:
            self.assertEqual(conn.execute("SELECT event_id,amount_cents FROM transactions").fetchall(), [("evt-001", 250)])

    def test_vehicle_rate_matrix(self):
        for vehicle, expected in (("car", 250), ("truck", 700), ("motorcycle", 150)):
            with self.subTest(vehicle=vehicle):
                status, body = self.request(payload=dict(self.payload, event_id=vehicle, vehicle_class=vehicle))
                self.assertEqual(status, 201)
                self.assertEqual(body["transaction"]["amount_cents"], expected)

    def test_idempotent_retry(self):
        first = self.request(payload=self.payload)[1]
        status, replay = self.request(payload=self.payload)
        self.assertEqual(status, 200)
        self.assertTrue(replay["replayed"])
        self.assertEqual(first["transaction"], replay["transaction"])
        self.assertEqual(self.request("GET")[1]["count"], 1)

    def test_concurrent_duplicate_events(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(lambda _: self.request(payload=self.payload), range(6)))
        self.assertEqual(sorted(status for status, _ in responses), [200]*5 + [201])
        self.assertEqual(len({body["transaction"]["id"] for _, body in responses}), 1)
        with sqlite3.connect(self.database) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 1)

    def test_duplicate_with_different_data_is_conflict(self):
        self.request(payload=self.payload)
        status, body = self.request(payload=dict(self.payload, plate="OTHER"))
        self.assertEqual(status, 409)
        self.assertIn("error", body)
        self.assertEqual(self.request("GET")[1]["items"][0]["plate"], "DEMO123")

    def test_invalid_input_matrix_never_persists(self):
        bad = [None, [], "text", {}, dict(self.payload, plate=""), dict(self.payload, plate="X"*13),
               dict(self.payload, event_id="X"*65), dict(self.payload, event_id=123),
               dict(self.payload, vehicle_class="bus"), dict(self.payload, vehicle_class=[]),
               dict(self.payload, occurred_at="not-a-date"), dict(self.payload, occurred_at="2026-01-01"),
               dict(self.payload, occurred_at=123), dict(self.payload, amount_cents=1)]
        for payload in bad:
            with self.subTest(payload=payload):
                status, body = self.request(payload=payload)
                self.assertEqual(status, 400)
                self.assertIn("error", body)
        self.assertEqual(self.request("GET")[1]["count"], 0)

    def test_input_normalization(self):
        status, body = self.request(payload=dict(self.payload, plate=" demo123 ", event_id=" evt-001 "))
        self.assertEqual(status, 201)
        self.assertEqual(body["transaction"]["plate"], "DEMO123")
        self.assertEqual(body["transaction"]["event_id"], "evt-001")

    def test_malformed_json(self):
        self.assertEqual(self.request(raw=b"{broken")[0], 400)

    def test_invalid_utf8(self):
        self.assertEqual(self.request(raw=b"\xff")[0], 400)

    def test_content_type(self):
        self.assertEqual(self.request(payload=self.payload, content_type="text/plain")[0], 415)

    def test_payload_size_limit(self):
        self.assertEqual(self.request(raw=b"x"*8193)[0], 413)

    def test_unknown_route(self):
        self.assertEqual(self.request("GET", "/unknown")[0], 404)
        self.assertEqual(self.request(path="/unknown", payload=self.payload)[0], 404)

    def test_parameterized_sql_preserves_schema(self):
        self.request(payload=dict(self.payload, event_id="'; DROP TABLE transactions; --"))
        status, body = self.request("GET")
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["items"][0]["event_id"], "'; DROP TABLE transactions; --")


if __name__ == "__main__":
    unittest.main()

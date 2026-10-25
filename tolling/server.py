"""Local JSON API backed by SQLite. Uses only synthetic data."""
import argparse
import json
import sqlite3
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

RATES = {"car": 250, "truck": 700, "motorcycle": 150}


def validate(payload):
    if not isinstance(payload, dict):
        raise ValueError("Body must be a JSON object")
    required = {"event_id", "plate", "vehicle_class", "occurred_at"}
    if set(payload) != required:
        raise ValueError("Expected exactly: " + ", ".join(sorted(required)))
    for field, limit in (("event_id", 64), ("plate", 12)):
        value = payload[field]
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            raise ValueError(f"{field} must contain 1 to {limit} characters")
    vehicle = payload["vehicle_class"]
    if not isinstance(vehicle, str) or vehicle not in RATES:
        raise ValueError("Unsupported vehicle_class")
    stamp = payload["occurred_at"]
    if not isinstance(stamp, str):
        raise ValueError("occurred_at must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("occurred_at must be an ISO 8601 timestamp") from exc
    if parsed.utcoffset() is None:
        raise ValueError("occurred_at must include a timezone")
    return {"event_id": payload["event_id"].strip(), "plate": payload["plate"].strip().upper(),
            "vehicle_class": vehicle, "occurred_at": parsed.isoformat(), "amount_cents": RATES[vehicle]}


def create_server(database, host="127.0.0.1", port=0):
    with sqlite3.connect(database) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, plate TEXT NOT NULL,
            vehicle_class TEXT NOT NULL, occurred_at TEXT NOT NULL, amount_cents INTEGER NOT NULL)""")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, value):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/health":
                return self.reply(200, {"status": "ok"})
            if path == "/transactions":
                with sqlite3.connect(database) as conn:
                    conn.row_factory = sqlite3.Row
                    items = [dict(row) for row in conn.execute("SELECT * FROM transactions ORDER BY id")]
                return self.reply(200, {"items": items, "count": len(items)})
            self.reply(404, {"error": "Not found"})

        def do_POST(self):
            if urlsplit(self.path).path != "/transactions":
                return self.reply(404, {"error": "Not found"})
            if self.headers.get_content_type() != "application/json":
                return self.reply(415, {"error": "Use application/json"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self.reply(400, {"error": "Invalid Content-Length"})
            if length < 1 or length > 8192:
                return self.reply(413, {"error": "Body must contain 1 to 8192 bytes"})
            try:
                data = validate(json.loads(self.rfile.read(length)))
            except (ValueError, UnicodeError) as exc:
                return self.reply(400, {"error": str(exc)})
            with sqlite3.connect(database, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("BEGIN IMMEDIATE")
                previous = conn.execute("SELECT * FROM transactions WHERE event_id = ?", (data["event_id"],)).fetchone()
                if previous:
                    if any(previous[key] != value for key, value in data.items()):
                        return self.reply(409, {"error": "event_id already has different transaction data"})
                    return self.reply(200, {"transaction": dict(previous), "replayed": True})
                cursor = conn.execute(
                    "INSERT INTO transactions (event_id,plate,vehicle_class,occurred_at,amount_cents) VALUES (?,?,?,?,?)",
                    tuple(data[key] for key in ("event_id", "plate", "vehicle_class", "occurred_at", "amount_cents")))
                result = dict(data, id=cursor.lastrowid)
            self.reply(201, {"transaction": result, "replayed": False})

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="demo.sqlite3")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    server = create_server(args.database, port=args.port)
    print(f"Demo API listening at http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

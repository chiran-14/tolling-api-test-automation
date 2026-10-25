# Tolling API Test Automation

A runnable QA learning project by Chiranjeevi Neerukattu. It combines a local demo tolling API, black-box HTTP automation, and independent SQLite checks. All inputs are synthetic. This is a portfolio learning project, not client work or a production tolling system.

## Quick start

Requires Python 3.11 or newer. No third-party packages or accounts are needed.

```bash
python -m unittest discover -s tests -v
```

The suite starts its own HTTP server on a free local port and uses a separate temporary database for every test. No manual server startup is required. It verifies HTTP responses and actual persisted data, including concurrent retries.

To explore the API yourself:

```bash
python -m tolling.server --port 8080
```

In a second terminal:

```bash
curl -i http://127.0.0.1:8080/transactions \
  -H 'Content-Type: application/json' \
  -d '{"event_id":"demo-1","plate":"DEMO123","vehicle_class":"car","occurred_at":"2026-01-01T12:00:00Z"}'
curl http://127.0.0.1:8080/transactions
```

## API contract

| Route | Expected behavior |
| --- | --- |
| `GET /health` | 200, health status |
| `GET /transactions` | 200, ordered items and count |
| `POST /transactions` | 201 created; 200 identical replay; 409 conflicting event ID |

POST accepts exactly `event_id`, `plate`, `vehicle_class`, and `occurred_at`. Event IDs have 1–64 characters, plates 1–12 after trimming. Plates are uppercased. Timestamps require an explicit timezone. Fictional rates: car = 250 cents, truck = 700, motorcycle = 150. Server-defined integer cents avoid floating-point money calculations.

Malformed input returns 400, oversized or empty JSON bodies 413, unsupported media types 415, unknown routes 404. Event IDs are idempotency keys: retries must preserve the original data. SQL parameters prevent input from being interpreted as executable SQL. A database transaction protects concurrent duplicate submissions.

## Automated coverage

- Positive contracts, exact response fields, rates, and SQL persistence.
- Negative and boundary scenarios using `subTest`.
- Duplicate prevention, conflicting retries, and six simultaneous requests.
- Invalid JSON/UTF-8, unsupported media types, size limits, unknown routes.
- A SQL-like event ID remains ordinary data.

See [test strategy](docs/test-strategy.md) for risk mapping and a failure experiment. GitHub Actions is configured for Python 3.11 and 3.12 on push and pull request; local verification does not imply CI has run.

## Layout

- `tolling/server.py`: demo system under test.
- `tests/test_api.py`: API and database automation.
- `docs/test-strategy.md`: risk mapping and manual exploration.
- `.github/workflows/tests.yml`: CI configuration.

## Learning next steps

Add pagination and authentication, then extend the tests. Try migrating to pytest or adding browser automation for a future UI. Keep test expectations independent from implementation constants.

## Limits

No real toll provider, authentication, payment, or personal vehicle data. The API binds to localhost and is not hardened for deployment. Passing tests cover the documented scenarios, not every possible behavior.

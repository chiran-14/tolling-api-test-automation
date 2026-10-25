# Test strategy

| Risk | Automated evidence |
| --- | --- |
| Incorrect charge | Independent fixed rate matrix |
| Lost data | HTTP response compared with direct SQL query |
| Duplicate charge | Identical replay and concurrent submissions |
| Silent overwrite | Same event ID with different plate returns 409 |
| Invalid input corrupts records | Invalid input matrix plus database count |
| Unsafe query composition | SQL-like ID stored as a literal value |

Each test owns a temporary database and HTTP server. Requests have timeouts. Failures identify assertions and inputs. SQL assertions do not reuse service-layer validation helpers.

## Failure experiment

In a temporary branch, change the car rate from 250 to 251 and run the suite. The success/persistence check and rate matrix should fail. Revert afterward. This demonstrates detection of a real behavior change; no intentional bug is shipped by default.

## Manual exploration

1. Create a transaction with curl, repeat it, then change the plate with the same event ID.
2. Confirm 201, 200, then 409 and inspect the stored record.
3. Try missing timezones, unknown vehicle classes, and overlength plates.
4. Restart the demo server and confirm database persistence.

## Not covered

Load/soak performance, TLS, authorization, real toll rates, external integrations, and production availability. Six concurrent requests are not a load test. Real plate-format and jurisdiction requirements would need separate rules.

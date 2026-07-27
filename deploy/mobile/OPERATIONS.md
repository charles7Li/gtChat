# Mobile production operations

## Release gate

1. Build one immutable image tag and scan it for critical vulnerabilities.
2. Store the production environment in the cloud secret manager; do not copy it into the image or repository.
3. Run `python -m app.mobile_api.preflight` with the production environment.
4. Back up PostgreSQL and verify the most recent restore exercise before applying a schema change.
5. Run `python -m app.mobile_api.migrate` once. Application containers use `MOBILE_AUTO_MIGRATE=false`.
6. Start API, Kafka outbox, Kafka Worker and notification Worker with the same image tag.
7. Verify API readiness, Kafka consumer lag, outbox age, one synthetic offline job, and one authorized subscription message before directing user traffic.

## Required alerts

- API 5xx rate, login failure rate, and P95/P99 latency.
- `mochi_mobile_outbox_oldest_age_seconds` and `mochi_mobile_outbox_pending`.
- Kafka consumer lag, retry-topic ingress and DLQ ingress.
- Jobs remaining queued/running beyond their route-specific SLO and workflow failure ratio.
- Notification `failed` growth, content-moderation unavailable/rejected ratio, PostgreSQL connections/storage, and object-storage failures.
- LLM calls, tokens, collector requests and cost anomalies. Logs must not contain access tokens, OpenID, cookies, uploaded content or full prompts.

## Backup and restore

- Enable managed PostgreSQL point-in-time recovery and daily snapshots. Define the retention period in the approved privacy policy and data inventory.
- Enable object-storage versioning only if the approved deletion policy permits it; configure lifecycle expiration and server-side encryption.
- At least once per release cycle, restore the database into an isolated account/project, verify schema version, job/report ownership, and object references, then destroy the isolated environment through the cloud change process.
- Account deletion removes online objects immediately. Backup expiry is asynchronous and must complete inside the published maximum retention period.

## Rollback

1. Set `MOBILE_ACCEPT_NEW_JOBS=false` and roll only the API service (or use the equivalent ingress feature flag), while keeping job status and report reads available.
2. Stop the outbox publisher if the new event format is incompatible; do not delete Kafka topics or offsets.
3. Roll API and Workers back to the last immutable image that understands the current schema and event version.
4. Prefer forward-compatible schema fixes. Never run a destructive down migration until a verified backup exists and all older processes are stopped.
5. Re-enable job creation in staged percentages and watch error rate, queue age, duplicates and cost.

## Incident evidence

Use request ID, job ID, event ID and timestamps to correlate API logs, `outbox_events`, Kafka records and Worker logs. Preserve only the minimum evidence needed for the incident and follow the approved retention policy. Do not ask users to provide login codes, tokens or platform cookies.

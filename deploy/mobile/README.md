# Mobile deployment

This directory runs the Mobile API and workflow Worker as separate processes against one persistent volume.

## Local experience build

1. Copy `mobile.env.example` to `mobile.env` and keep `WECHAT_AUTH_MODE=mock`.
2. Run `docker compose -f deploy/mobile/compose.dev.yml up --build` from the repository root.
3. Set `TARO_APP_API_BASE=http://127.0.0.1:8000` and build `miniprogram/`.
4. Import `miniprogram/dist` into WeChat DevTools.

For a real WeChat experience version, change the auth mode to `wechat`, configure AppID/AppSecret through the cloud secret manager, use a filed HTTPS domain, and set `TARO_APP_API_BASE` to that domain.

## Production boundary

`compose.dev.yml` is a single-host experience/staging template. It uses SQLite WAL and a local object volume. Do not scale API or Worker replicas with this storage mode. Production release remains gated on a PostgreSQL-backed `MobileStore`, cloud object storage, a reliable queue, secret manager, backup, alerting, and filing/review completion.

## Production process layout

`compose.prod.yml` separates preflight, migration, public API, Kafka outbox publisher, Kafka consumer worker, WeChat notification worker, and retention maintenance. It expects managed PostgreSQL, Kafka, and S3/COS-compatible object storage; it does not start stateful infrastructure on the application host.

Before using it, copy `mobile.env.example` to a secret-managed production environment file and set PostgreSQL, S3/COS, Kafka, real WeChat credentials, and `WECHAT_TASK_TEMPLATE_ID`. Keep the resulting file outside source control.

Set `MOBILE_AUTO_MIGRATE=false` in production. The one-shot `migrate` service applies the idempotent PostgreSQL schema first; API and workers start only after it succeeds.

```powershell
$env:MOCHI_MOBILE_IMAGE = "registry.example.com/mochi-scout-mobile:release-tag"
$env:MOBILE_ENV_FILE = "C:\secure\mochi-mobile.env"
docker compose -f deploy/mobile/compose.prod.yml config
docker compose -f deploy/mobile/compose.prod.yml up -d
```

Enable `WECHAT_CONTENT_SECURITY_ENABLED=true` only after the production AppID is verified. User-entered text and generated report text are checked before storage or delivery. Uploaded media moderation still requires a selected provider and remains a release gate.

See `OPERATIONS.md` for the release gate, alert set, backup/restore exercise, rollback sequence, and incident evidence rules.

For the real mini-program build, set `WECHAT_APP_ID` and run `npm run configure:wechat` inside `miniprogram/`. Then set the filed `TARO_APP_API_BASE` and the matching `TARO_APP_TASK_TEMPLATE_ID`, and run `npm run build:release`. The release preflight rejects `touristappid`, HTTP/example API domains, empty template IDs, or disabled WeChat domain checks.

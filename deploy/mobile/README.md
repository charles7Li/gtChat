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


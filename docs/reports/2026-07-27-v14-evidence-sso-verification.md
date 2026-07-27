# Yanqing V1.4 Evidence And SSO Verification

## Summary

- Evidence ingestion deployed: yes.
- Gateway SSO deployed: yes.
- Final review fixes deployed: yes, covering narrative evidence traceability, evidence file containment, and refresh gap propagation.
- Health check: internal app health returned `{"status":"ok","service":"yanqing"}`.
- Evidence refresh: internal refresh for `300767.SZ` returned 2 cached evidence items and no data gaps.
- Portal docs center: docs were synced to `/root/apps/yanqing/docs`; unauthenticated portal docs URL returned the BrianHub login page, so final visual rendering should be checked with an authenticated portal session.

## Verification

- VPS backup before release: `/root/apps/yanqing-backup-before-v14-20260727-132924.tgz`.
- Gateway backup before SSO change: `/root/apps/brianhub-gateway/Caddyfile.backup-yanqing-sso-20260727-133353`.
- Container tests before final review fixes: `python -m unittest backend.test_main` passed with 28 tests.
- Final review red test run: 32 tests ran with expected failures for unvalidated narrative claims, `documents/` symlink escape, and stale-cache refresh gap status.
- Container tests after fixes and rebuild: `python -m unittest backend.test_main` passed with 32 tests.
- Runtime configuration check: `PORTAL_INTERNAL_TOKEN` and `TUSHARE_TOKEN` were present in the Yanqing container after recreating with `.env.production`.
- Gateway validation: `caddy validate --config /etc/caddy/Caddyfile` returned valid configuration.
- Gateway reload: `caddy reload --config /etc/caddy/Caddyfile` completed.
- Public SSO behavior: unauthenticated `https://brianhub.net/yanqing/` returned `302` to the portal login flow.
- Public business API SSO behavior: unauthenticated `https://brianhub.net/yanqing/api/evidence/300767.SZ` returned `302` to the portal login flow.
- Evidence cache sample: 2 items for `300767.SZ`, both downloaded and text extraction ready.
- Final evidence refresh sample after rebuild: `300767.SZ` returned 2 evidence items, no data gaps, and both sampled PDFs had `downloaded` / `ready` statuses.

## Rollback

- Yanqing app rollback: restore `/root/apps/yanqing-backup-before-v14-20260727-132924.tgz` into `/root/apps/yanqing`, then run `docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build`.
- Gateway rollback: restore `/root/apps/brianhub-gateway/Caddyfile.backup-yanqing-sso-20260727-133353` to `/root/apps/brianhub-gateway/Caddyfile`, then run `docker compose -f docker-compose.prod.yml exec -T caddy caddy reload --config /etc/caddy/Caddyfile`.
- Verify rollback with internal `/api/health`, gateway route behavior, and container status.

## Notes

- No real tokens, API keys, cookies, or private keys were printed or saved.
- CNINFO source access uses public endpoints and local Yanqing cache only.
- Yanqing remains independent from cnstock data, login, cookies, database, and report assets.

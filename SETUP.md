# Setup

Do these steps in sequence. Each step tells you how to check that it worked.

## 1. Prerequisites

| Item | Check |
|---|---|
| Python 3.12 or later | `python3 --version` |
| Docker Desktop | `docker ps` |
| OpenObserve on `:5080` | `curl -s localhost:5080/healthz` gives `{"status":"ok"}` |
| WHOOP membership | You can sign in at <https://app.whoop.com> |

No OpenObserve yet? Run `docker compose --profile o2 up -d openobserve`.

### OpenObserve settings

| Variable | Value | Why |
|---|---|---|
| `ZO_INGEST_ALLOWED_UPTO` | `87600` (hours) | Default is 5 h. WHOOP history and late-scored sleeps are older. Without it, OpenObserve drops them with "Too old data". |
| `ZO_SKIP_SSRF_CHECKS` | `true` (only if alerts post to a private host) | OpenObserve blocks alert destinations on private hosts such as `host.docker.internal`. |

The bundled `o2` compose profile sets `ZO_INGEST_ALLOWED_UPTO` for you.

## 2. Create the WHOOP developer app

1. Open <https://developer-dashboard.whoop.com>. Sign in with your WHOOP account.
2. Create a team if the dashboard asks for one.
3. Click **Create App**. Fill in:

   | Field | Value |
   |---|---|
   | Name | any name, e.g. `whoop-dashboard` (WHOOP shows it on the consent page) |
   | Contact | your email |
   | Privacy policy | link to [PRIVACY.md](PRIVACY.md) in your repo, e.g. `https://github.com/<you>/whoop-monitoring/blob/main/PRIVACY.md` |
   | Redirect URL | `http://localhost:8765/callback` |
   | Scopes | all six `read:*` scopes |
   | Webhooks | leave empty for now |

4. Click **Create App**. Copy the **Client ID** and **Client Secret**.

The app starts on the **Sandbox** tier: up to 10 members. That is enough for personal use.

## 3. Configure

```bash
cp .env.example .env
chmod 600 .env
```

Set `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`, `O2_USER` and `O2_PASSWORD`.
Do not commit `.env`. It is in `.gitignore`.

Optional: set `TOKEN_ENCRYPTION_KEY` to encrypt the stored tokens (see `.env.example`).

## 4. Install and log in

```bash
make install
make login
```

Your browser opens the WHOOP consent page. Approve it. The terminal shows
`Connected WHOOP user <id>`.

Check: `make status` shows the token expiry and your user id.

## 5. Load history

```bash
make backfill SINCE=2024-01-01
```

A 3-year backfill uses about 180 API requests. The output shows rows per data type.

## 6. Create dashboards and alerts

```bash
make provision                                    # dashboards only
ALERT_WEBHOOK_URL=https://hooks.slack.com/... make provision   # dashboards + alerts
```

Check: OpenObserve → **Dashboards** shows four `WHOOP ·` dashboards with data.

## 7. Run the collector

```bash
make up
make logs
```

The collector syncs every 15 minutes. It re-reads the last 72 hours each time, because WHOOP
scores sleep and recovery some time after they end.

Check: **WHOOP · Collector Health** shows a successful run every 15 minutes.

> Do not run `make sync` on the host while the container runs. WHOOP refresh tokens rotate,
> and two processes that refresh at the same time can lock you out. If that happens, run
> `make login` again.

## 8. Optional: webhooks

Webhooks give updates in seconds instead of up to 15 minutes. They need a public HTTPS URL.

```bash
make tunnel        # prints https://<random>.trycloudflare.com
```

1. In the WHOOP developer dashboard, open your app → **Webhooks** → **Add**.
2. Enter `<tunnel URL>/webhook`. Select model version **v2**. Save.
3. Check: after your next sleep or workout, `whoopmon_app` shows `webhook.event.queued`.

The quick tunnel URL changes on each restart. For a stable URL, use a named Cloudflare tunnel.

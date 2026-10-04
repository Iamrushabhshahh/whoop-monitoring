# Security

## Secrets

| Secret | Where | Rule |
|---|---|---|
| WHOOP client secret | `.env` | Never commit. Never log. Server side only. |
| OpenObserve password | `.env` | Never commit. |
| WHOOP access/refresh tokens | `data/tokens.json` (mode 600) | Optional encryption with `TOKEN_ENCRYPTION_KEY` (Fernet). |

`.env` and `data/` are in `.gitignore` and `.dockerignore`. Pre-commit runs `gitleaks`.

## Controls in code

- Log redaction removes tokens, secrets, auth codes, emails and `Bearer` values.
- OAuth `state` is 32 random characters and is checked on callback.
- The callback server does not log request URLs (they contain the code).
- Webhooks: HMAC-SHA256 check with constant-time compare, 10-minute timestamp window,
  `trace_id` de-duplication.
- The container runs as a non-root user.

## Reporting

Open a private security advisory on the GitHub repository.

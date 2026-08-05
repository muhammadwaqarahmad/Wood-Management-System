# Mobile security architecture

How the phone app authenticates, stays signed in, and protects the session.
The goal: **type the password once**, then unlock with fingerprint/face — while
keeping the account safe if the phone is lost.

## The pieces

| Layer | What | Where |
|---|---|---|
| Password check | bcrypt, brute-force throttle | server (`timber.core.auth`, reused) |
| Transport | HTTPS/TLS | Cloudflare Tunnel in front of the API |
| Access token | short-lived (12h), JWT `type:access` | **phone memory only** |
| Refresh token | long-lived (45d), JWT `type:refresh` | **hardware keystore** (iOS Keychain / Android Keystore) |
| Biometric gate | Face ID / Touch ID / Android BiometricPrompt | OS (`local_auth`) — the app never sees biometric data |
| Server secret | signs/verifies all tokens | `TIMBER_API_SECRET` in the server `.env` |

## Token flow

```
FIRST TIME
  password  ──POST /auth/login──▶  { access(12h), refresh(45d), user }
  access → kept in memory        refresh → saved in the hardware keystore
  app offers: "Enable Face/Fingerprint unlock?"

EVERY REQUEST
  Authorization: Bearer <access>
  server checks it's a valid ACCESS token (a refresh token is rejected here)

WHEN ACCESS EXPIRES (a 401)
  client silently ──POST /auth/refresh { refresh }──▶ { new access, new refresh }
  the old refresh is ROTATED (invalidated); request retried once
  if refresh also fails → back to the password screen

RE-OPENING THE APP (biometric on)
  Lock screen ▶ Face/Fingerprint prompt ──▶ read refresh from keystore
  ▶ /auth/refresh ▶ signed in.  No password typed.
```

## Why it's safe

- **The password is never stored** on the device — only tokens are.
- **The access token never touches disk** (memory only); a device backup can't leak it.
- **The refresh token sits in the OS keystore** (hardware-backed) and is only used
  after a **biometric unlock** the app requests but the OS performs — the app
  never receives fingerprint/face data.
- **Token types can't be swapped**: an access token can't refresh, a refresh
  token can't call the API (enforced by the `type` claim).
- **Rotation**: every refresh issues a new refresh token, so a stolen old one
  stops working.
- **Lost phone**: without the user's face/fingerprint (or device passcode) the
  keystore won't release the refresh token; "Use password instead" and a server
  password change fully cut off access.

## Server setup (once)

Put a long random secret in the server `.env` so tokens survive restarts and
can't be forged:

```
TIMBER_API_SECRET=<64+ random characters>
# optional tuning:
TIMBER_API_ACCESS_HOURS=12
TIMBER_API_REFRESH_DAYS=45
```

> Never paste this secret into chat or commit it — it belongs only in the
> server's `.env`.

# Website — Production Plan

The browser version of **Abdul Sattar Woods**, with the **same functionality as
the desktop app** (full read & write, every screen), running independently
against one shared cloud database.

| | |
|---|---|
| **Parity** | all desktop features |
| **Access** | read & write |
| **Data** | one shared cloud database |
| **Independence** | works without the office PC |

---

## 1. What we're building & why it's feasible

The desktop app is a complete accounting system for the timber business — buying
& selling, payments, the split sub-ledger, weekly settlement, every ledger and
report. The website must do **all of it**, from a browser, for you and your
staff, over the internet.

The catch: thousands of lines of tested accounting logic already live in Python
(`timber/core`). Re-writing that in JavaScript would double the code and split
the truth — two engines drifting apart, two sets of bugs. So we don't.

> **The one principle** — Build the website on top of the **same Python core**,
> exposed through an API. Desktop, website, and mobile all run the identical
> accounting engine, so the numbers can never disagree.

---

## 2. Architecture

Three independent clients, one shared brain, one database you own. Nothing
depends on the office PC being on — the API and database live on always-on cloud
hosting.

```
   Desktop            Website            Mobile
  (PySide6)          (browser)          (Flutter)
      \                  |                  /
       \                 |                 /
        \-------------  HTTPS  -----------/
                         |
                 +---------------+
                 |  Shared API   |   FastAPI over timber/core
                 | read + write  |   + auth
                 +---------------+
                         |
                 +---------------+
                 | Cloud Postgres|   the database you buy (Mumbai region)
                 +---------------+
```

- **Website & mobile** talk only to the API → independent of the office PC.
- **Desktop** connects to the database directly today; it can move onto the API
  later for perfect consistency.
- One brain = identical numbers everywhere.

---

## 3. Decisions to lock first

| Decision | Recommendation | Notes |
|---|---|---|
| **Website technology** | **React (Vite or Next.js) + the shared JSON API** | The data-entry screens (Buy & Sell with live totals) are highly interactive, and one JSON API then serves both website *and* mobile. Lighter alternative: **FastAPI + HTMX** (all-Python, fewer moving parts, faster to ship). |
| **Login & roles** | Reuse the API's JWT login + the desktop's permission model | Admin / Manager / Viewer map straight across; the same rules that gate desktop actions gate the API endpoints. |
| **Hosting** | API on cloud hosting (Render or similar), website on a static host (Vercel / Netlify / Cloudflare Pages), database on the Postgres you buy | All three always-on and independent of your PC. |
| **Desktop's data path** | Keep it on a **direct database connection** for now | A cloud DB is slower than the old LAN — pick a **Mumbai region**, and if it still feels heavy, move the desktop onto the API too. |

---

## 4. Feature parity map

Every desktop screen has a home on the web — roughly thirty, grouped by how
they'll be built.

- **Data entry (6):** Buy & Sell · Payments · Transfers · Expenses · Loans · Cheques
- **Ledgers (9):** Party · Factory · Factory Sub-ledger · Trade · Profit ·
  Location · Wood type · Daily book · Bank book
- **Dashboards & reports (6):** Dashboard · Financial Position · Reports ·
  Overdue · Aging · PDF / Excel export
- **Management (8):** Parties · Users · Bank accounts · Wood / Locations ·
  Advance register · Settings · Audit log · Search

---

## 5. Build roadmap

### Phase 0 — Foundations
Monorepo split (`desktop/` · `website/` · `mobile/`) — **done**. Buy & provision
the cloud Postgres, point everything at it, run the migrations, and stand up the
API deploy with login.
**Done when:** one live cloud DB, API deploys green, everyone authenticates.

### Phase 1 — Backend to full read & write
Extend the FastAPI over `timber/core` with create / update / void endpoints for
every entity — trades, payments, expenses, transfers, loans, cheques, parties —
each guarded by the existing permission rules. Endpoint tests alongside the
current pytest suite.
**Done when:** anything the desktop can write, the API can write — safely.

### Phase 2 — Web shell
Login, app layout & navigation, light/dark theme, English + Urdu (with
right-to-left), and the shared building blocks — API client, tables, forms,
toasts — everything else slots into.
**Done when:** you can log in and move around an empty-but-real app.

### Phase 3 — The transactional heart
Buy & Sell (dynamic wood rows with live totals) and Payments — the screens that
actually run the business. This is where read/write earns its keep.
**Done when:** a full day's trading can be recorded from the browser.

### Phase 4 — Ledgers, reports & exports
All ledger and report pages, plus PDF/Excel export that **reuses the desktop's
existing exporters** server-side and hands the browser a download — identical
documents, no re-implementation.
**Done when:** every figure and export matches the desktop.

### Phase 5 — Management & the rest
Parties, users, bank accounts, settings, transfers, loans, cheques, expenses,
dashboard, financial position, audit log, search — closing the parity gap screen
by screen.
**Done when:** nothing on the desktop is missing from the web.

### Phase 6 — Hardening & launch
Roles verified end-to-end, multi-user editing made safe, a security review of the
public write API, backups, a load test, then deploy behind your own domain.
**Done when:** it's safe to run the business on.

---

## 6. Cross-cutting concerns

- **Auth & roles** — the same permission model as the desktop, enforced on the
  server; the browser never bypasses a rule.
- **Multi-user safety** — two people editing at once needs a rule (optimistic
  concurrency) so nobody silently overwrites or double-voids a record.
- **Bilingual + RTL** — reuse the existing English/Urdu translation keys; lay the
  web UI out for right-to-left like the desktop.
- **Exports** — generate PDFs/Excel with the exact code the desktop already uses;
  run it on the server, return the file.
- **Security** — HTTPS everywhere, JWT auth, server-side validation, rate
  limiting on writes, secrets only in environment variables.
- **Migrations & backups** — Alembic keeps the one shared schema in step;
  scheduled backups of the bought database, with tested restores.

---

## 7. Risks & how we handle them

- **It's a lot of screens.** → Phased delivery; ship the money-making screens
  (Buy & Sell, Payments) first, so it's useful long before it's complete.
- **Logic drifting between apps.** → One Python core behind the API — the whole
  point of the architecture.
- **Desktop feels slow on cloud DB.** → Mumbai region + keep batching queries;
  move the desktop onto the API if needed.
- **A write API open to the internet.** → Auth, validation, and rate limiting
  from day one — not bolted on at the end.

---

## 8. Immediate next steps

1. **Choose the website technology** — React + shared API (recommended) or
   FastAPI + HTMX.
2. **Buy the cloud database** — a Mumbai-region PostgreSQL; point the API (and
   later the desktop) at it.
3. **Start Phase 1** — extend the API to full read/write, then build the web shell.

---

*One core, three clients, one database.*

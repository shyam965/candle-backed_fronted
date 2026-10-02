# AK Royal Flames — candle shop

A server-rendered rebuild of the AK Royal Flames shop: storefront, cart, WhatsApp checkout, order tracking and an admin panel. It replaces the old React SPA and Express API and runs against the **existing MongoDB data**.

- **Stack:** Python 3.11+, FastAPI, Uvicorn, Jinja2 + HTMX 2 (local file), Tailwind CSS v4 (standalone CLI, no CDN), MongoDB via PyMongo `AsyncMongoClient`, Pydantic v2 / pydantic-settings, bcrypt, pytest + httpx.
- **Docs:** [`docs/PLAN.md`](docs/PLAN.md) (modules, routes, data model, traceability), [`docs/DECISIONS.md`](docs/DECISIONS.md) (every Known Issue fix and open question), [`docs/REVIEW.md`](docs/REVIEW.md) (page-by-page review).
- **Specs** this was built from: `FEATURES_AND_FR.md`, `FRONTEND_FEATURES_AND_FR.md`.

## 1. Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[test]"
cp .env.example .env        # then fill in the values (see below)
python scripts/fetch_assets.py   # downloads the pinned Tailwind CLI (bin/) and HTMX (app/static/js/)
python scripts/build_css.py      # builds app/static/css/app.css
```

### Environment variables (`.env`)

`.env.example` lists the names only. Required: **`MONGO_URI`** and **`SECRET_KEY`** (at least 32 random characters; the app refuses to start without it).

| Name | Purpose / default |
|---|---|
| `APP_ENV` | `development` \| `production` \| `test` (default `development`) |
| `APP_BASE_URL` | Public origin, e.g. `https://akroyalflames.in`; used for the API origin check |
| `PORT` | Listen port for `python -m app` (default `9000`) |
| `MONGO_URI` | MongoDB connection string |
| `MONGO_DB_NAME` | Optional override. Otherwise the database in the URI, else `test` (Mongoose's default) |
| `SECRET_KEY` | Signs CSRF tokens and flash cookies |
| `COOKIE_SECURE` | `true` in production (HTTPS). Set `false` only for plain-http local development |
| `SESSION_TTL_DAYS` | Session lifetime (default 7) |
| `CORS_ORIGINS` | Comma-separated origins allowed to call `/api/*` with cookies (e.g. a legacy SPA) |
| `UPLOAD_DIR` | Folder served at `/uploads` (default `uploads`, created at startup) |
| `MAX_UPLOAD_MB` / `MAX_BODY_MB` | Image size limit (5) / JSON-form body limit (10) |
| `ADMIN_ORDERS_PAGE_SIZE` | Admin orders per page (25) |
| `DISPLAY_TIMEZONE` | Date display timezone (default `Asia/Kolkata`) |
| `LOG_LEVEL` | `INFO` by default |
| `WHATSAPP_NUMBER`, `FREE_DELIVERY_THRESHOLD` | `919288245292`, `1099` |
| `BUSINESS_PHONE`, `BUSINESS_EMAIL`, `BUSINESS_ADDRESS`, `BUSINESS_HOURS` | Footer and Contact page details |
| `INSTAGRAM_URL`, `INSTAGRAM_HANDLE`, `FACEBOOK_URL`, `YOUTUBE_VIDEO_ID` | Social links and the Home video |
| `MAP_EMBED_URL` | Optional `https://www.google.com/maps/embed?...`; the map is hidden when empty |
| `RATE_LIMIT_LOGIN_PER_15M`, `RATE_LIMIT_LOGIN_IP_PER_15M`, `RATE_LIMIT_REGISTER_PER_HOUR` | 5 / 30 / 10 |
| `TEST_MONGO_URI` | Tests only (default `mongodb://localhost:27017`) |

## 2. Run (development)

```bash
python scripts/build_css.py --watch     # terminal 1: rebuild CSS when templates change
python -m app                           # terminal 2: http://localhost:9000
# or with auto-reload:
uvicorn app.main:create_app --factory --reload --port 9000
```

**Admins** can't be created from the web (BR-04). Promote an existing account with:

```bash
python -m app.cli promote-admin someone@example.com
python -m app.cli demote-admin someone@example.com
```

**Demo data** (optional, for trying the UI; it refuses any database not named `akrf_demo*`):

```bash
pip install -e ".[review]" && python -m playwright install chromium
python scripts/seed_demo.py mongodb://localhost:27017 akrf_demo uploads-demo
# then run with MONGO_DB_NAME=akrf_demo UPLOAD_DIR=uploads-demo ; logins: admin@demo.test / customer@demo.test, password demo1234
```

## 3. Tests

```bash
python -m pytest                        # 444 tests; needs a reachable MongoDB at TEST_MONGO_URI
python scripts/check_traceability.py    # every FR / FR-UI row exists and references real tests
python scripts/ui_review.py out-dir     # browser review at 375/768/1280 px (needs the [review] extra)
```

Every test creates its own `akrf_test_<random>` database and drops it afterwards; real data is never touched.

## 4. Production

1. Build assets once: `python scripts/fetch_assets.py && python scripts/build_css.py`, then deploy `app/static/css/app.css` with the code.
2. Configure `.env` (or real environment variables): `APP_ENV=production`, `COOKIE_SECURE=true`, a strong `SECRET_KEY`, `APP_BASE_URL=https://your-domain`.
3. **Persist uploads:** mount `UPLOAD_DIR` on a persistent volume and back it up. Existing images referenced as `/uploads/<file>` must be copied into it.
4. Run Uvicorn behind a reverse proxy (it trusts `X-Forwarded-*` only from the proxy address):

```bash
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 9000 --workers 4 \
        --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-server-header
```

Example nginx site:

```nginx
server {
    listen 443 ssl http2;
    server_name akroyalflames.in;
    # ssl_certificate ... ;
    client_max_body_size 6m;                # MAX_UPLOAD_MB + form overhead

    location /static/ {
        alias /srv/akrf/app/static/;
        expires 30d;                        # URLs carry a content hash (?v=...)
        add_header Cache-Control "public";
    }
    location / {
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

`/uploads/*` stays served by the app, which applies the sandbox CSP and path checks. Startup fails with exit code 1 if MongoDB is unreachable. Health check: `GET /healthz`.

## 5. Compatibility with the existing data

- Same 7 collections, fields, enums, `createdAt`/`updatedAt`/`__v`; two new collections `sessions` and `rate_limits` (both TTL-indexed).
- Existing `$2a$10$` bcrypt hashes verify; new hashes use the same `$2a$` format.
- Stored image paths `/uploads/<file>` keep working; legacy files of any extension are still served.
- Users must log in once after cut-over (old JWT cookies are not accepted).
- The JSON API under `/api/*` keeps the old endpoints for any remaining client (admin writes now require an admin session).

## 6. Open items needing a human decision

Full list with defaults in [`docs/DECISIONS.md` §0](docs/DECISIONS.md). In short:

1. **Rotate the leaked credentials** (MongoDB password, old JWT secret) from the previously committed `.env` (KI-03).
2. Confirm the **order status rules** (forward-only + cancel; Delivered and Cancelled final) — D-30.
3. **Stock decrement** on orders — currently checked but not reduced (D-31).
4. Confirm the **production database name** (D-08).
5. Provide real **brand assets** (logo, photos); the SVG artwork is a stand-in (D-40).
6. Confirm the **upload policy** (JPEG/PNG/WebP ≤ 5 MB, no videos) — D-12.
7. Decide whether to build the features neither spec has: profile editing, customer cancel, banner/promo editing, password reset (KI-23).
8. Keep or retire the **JSON compatibility API** once no other client uses it (D-01).

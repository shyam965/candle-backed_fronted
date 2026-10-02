# PLAN — AK Royal Flames (FastAPI + Jinja2 + HTMX + MongoDB)

Inputs: `FEATURES_AND_FR.md` (**BE**, FR-001…FR-122) and `FRONTEND_FEATURES_AND_FR.md` (**FE**, FR-UI-001…FR-UI-128).
Decisions referenced as `D-xx` / `Q-xx` are in [DECISIONS.md](DECISIONS.md).

Stack: Python 3.11+ (developed on 3.13), FastAPI, Uvicorn, Jinja2, HTMX 2 (local file), Tailwind CSS v4 standalone CLI → `app/static/css/app.css`, PyMongo `AsyncMongoClient`, Pydantic v2, pydantic-settings, bcrypt, pytest + pytest-asyncio + httpx (+ `asgi-lifespan`).

---

## 1. Modules

| # | Module | Responsibility | Main FRs |
|---|---|---|---|
| M0 | **platform** | Settings, logging, DB lifecycle and indexes, app factory, middleware (request id, path normalisation, body limit, security headers, CORS for `/api`), error handlers and pages, serialization, health check | FR-001–012, D-02/03/08/11/17–22 |
| M1 | **security** | bcrypt passwords, server sessions, CSRF, rate limiter, guards (`current_user`, `require_user`, `require_admin` in HTML / HTMX / API flavours), safe-redirect helper | FR-017, 026–033, 036, FR-UI-010/011/024–029, D-04–07 |
| M2 | **auth** | Register / login / logout pages and `/api/auth/*` | FR-013–025, 034–035, FR-UI-012–023 |
| M3 | **layout & static pages** | Base / site / admin layouts, header (nav, search, cart badge, auth area, mobile menu), footer, toasts, HTMX indicator, About, Contact (+ WhatsApp contact form), 404/403/500 | FR-UI-001–009, 093–096, 126–128 |
| M4 | **uploads** | Validation (magic bytes, size, single field), storage, deletion rules, `/uploads` serving | FR-006, 118–122, D-12/13/35 |
| M5 | **categories** | Service, admin UI, `/api/category/*` | FR-037–049, FR-UI-103–108 |
| M6 | **products** | Service, admin UI, `/api/product/*` | FR-050–064, FR-UI-109–113 |
| M7 | **merchandising** | Banners + promo cards: services, admin UI, `/api/banner/*`, `/api/promo-card/*` | FR-104–117, FR-UI-114–119 |
| M8 | **cart** | Cart service, cart page, add-to-cart endpoint used by product cards, selection, `/api/cart/*` | FR-065–080, FR-UI-005, 057–067 |
| M9 | **storefront** | Home (sections as partials) and Shop (server-side filter/search/sort), product card | FR-UI-030–056 |
| M10 | **checkout & orders** | Delivery form, pending order in session, WhatsApp message builder, confirm page, order creation, `/api/order/create` | FR-081–092, FR-UI-068–083 |
| M11 | **customer orders** | My Orders, Order Details (tracking), `/api/order/my-orders*` | FR-093–094, FR-UI-084–093 |
| M12 | **admin orders** | Orders table (search, filter, pagination), modal, status change, `/api/order/all`, `/api/order/status/:id` | FR-095–103, FR-UI-120–125 |
| M13 | **admin dashboard** | Stats, status counts, recent orders (independent partials) | FR-UI-097–102 |
| M14 | **ops** | `app.cli` (promote/demote admin), README, `.env.example` | D-23 |

---

## 2. Folder structure

```
candle-ak/
├─ app/
│  ├─ __init__.py
│  ├─ __main__.py                # `python -m app` → uvicorn with PORT (default 9000)
│  ├─ main.py                    # create_app(): lifespan, middleware, routers, exception handlers
│  ├─ config.py                  # Settings (pydantic-settings, .env)
│  ├─ logging_config.py
│  ├─ db.py                      # AsyncMongoClient lifecycle, get_db(), ensure_indexes()
│  ├─ cli.py                     # promote-admin / demote-admin
│  ├─ core/
│  │  ├─ errors.py               # AppError hierarchy (ValidationFailed, NotFound, Conflict, Forbidden, ...)
│  │  ├─ handlers.py             # HTML / HTMX / JSON error rendering
│  │  ├─ middleware.py           # request-id, path normalisation, body limit, security headers, API CORS
│  │  ├─ documents.py            # new_doc_meta(), touch(), __v helpers, number normalisation
│  │  ├─ serialization.py        # to_json(): ObjectId → hex, datetime → ISO ms Z
│  │  ├─ ids.py                  # parse_object_id()
│  │  ├─ formatting.py           # inr(), discount_percent(), fmt_date(), fmt_datetime(), image_url()
│  │  ├─ links.py                # safe_redirect(), cta_href(), validate_button_link()
│  │  ├─ validators.py           # email, mobile, pincode, colour, digits-only normalisation
│  │  ├─ htmx.py                 # is_htmx(), toast(), hx_redirect(), trigger helpers
│  │  └─ templating.py           # Jinja env, filters, globals (settings, csrf, current_user, cart_count)
│  ├─ security/
│  │  ├─ passwords.py            # hash_password(), verify_password()
│  │  ├─ sessions.py             # create/get/delete session, cookie set/clear, pending order storage
│  │  ├─ csrf.py                 # token issue/verify, CSRF middleware/dependency, API origin check
│  │  ├─ rate_limit.py           # Mongo fixed-window limiter
│  │  └─ deps.py                 # current_user, require_user_*, require_admin_*
│  ├─ models.py                  # Pydantic v2 schemas of stored documents, checked before every insert (D-56)
│  ├─ services/                  # business logic + input validation, the only layer touching collections
│  │  ├─ auth_service.py  category_service.py  product_service.py  upload_service.py
│  │  ├─ merch_service.py (banners + promo cards)  cart_service.py  order_service.py  catalog.py
│  │  ├─ whatsapp.py  dashboard_service.py  order_view.py
│  ├─ web/                       # server-rendered routers (HTML + HTMX partials)
│  │  ├─ storefront.py (home, shop, add-to-cart)  pages.py (about, contact)  common.py
│  │  ├─ auth.py  cart.py  checkout.py  orders.py  system.py (health + /uploads)
│  │  └─ admin/  dashboard.py  categories.py  products.py  merch.py (banners + promo cards)  orders.py
│  ├─ api/                       # JSON compatibility API (/api/*) — D-01
│  │  ├─ common.py  auth.py  category.py  product.py  cart.py  order.py  merch.py (banner + promo-card)
│  ├─ templates/                 # see §4 for every template
│  └─ static/
│     ├─ css/app.css             # Tailwind build output (committed build artefact)
│     ├─ js/htmx.min.js          # HTMX 2.x, local
│     ├─ js/app.js               # CSRF header, toasts, slider, steppers, modal/menu a11y, wishlist, live validation
│     └─ img/logo.svg  favicon.svg  art-*.svg
├─ tailwind/
│  └─ input.css                  # @import "tailwindcss"; @source "../app/templates"; @theme tokens
├─ bin/                          # tailwindcss standalone binary (git-ignored, fetched by script)
├─ scripts/
│  ├─ fetch_assets.py            # downloads the pinned Tailwind standalone CLI + HTMX
│  ├─ build_css.py               # runs the CLI (minified build / --watch)
│  └─ check_traceability.py      # verifies every FR row and referenced test exists
├─ tests/
│  ├─ conftest.py                # test settings, per-test Mongo DB, app + AsyncClient, login helpers, factories
│  ├─ factories.py
│  ├─ unit/                      # pure business rules
│  └─ routes/                    # page, partial and API tests
├─ uploads/                      # runtime, git-ignored (created at startup)
├─ docs/  PLAN.md  DECISIONS.md  REVIEW.md
├─ pyproject.toml                # deps + pytest config
├─ .env.example  .gitignore  README.md
```

---

## 3. Configuration (`.env`, names only)

`APP_ENV`, `APP_BASE_URL`, `PORT`, `MONGO_URI`, `MONGO_DB_NAME`, `SECRET_KEY`, `COOKIE_SECURE`, `SESSION_TTL_DAYS` (7), `CORS_ORIGINS`, `UPLOAD_DIR`, `MAX_UPLOAD_MB` (5), `MAX_BODY_MB` (10), `ADMIN_ORDERS_PAGE_SIZE` (25), `DISPLAY_TIMEZONE`, `LOG_LEVEL`, `WHATSAPP_NUMBER`, `FREE_DELIVERY_THRESHOLD` (1099), `BUSINESS_PHONE`, `BUSINESS_EMAIL`, `BUSINESS_ADDRESS`, `BUSINESS_HOURS`, `INSTAGRAM_URL`, `FACEBOOK_URL`, `YOUTUBE_VIDEO_ID`, `MAP_EMBED_URL`, `RATE_LIMIT_LOGIN_PER_15M` (5), `RATE_LIMIT_LOGIN_IP_PER_15M` (30), `RATE_LIMIT_REGISTER_PER_HOUR` (10), `TEST_MONGO_URI` (tests only).

---

## 4. Pages and routes

Access: **P** = public, **U** = logged-in user (any role), **A** = admin. "Guard" column = behaviour when not allowed (D-45, D-52).
All state-changing UI routes require CSRF (D-06). HTMX partials are under the page they belong to.

### 4.1 Website (site layout = header + footer)

| URL | Method | Template | Access | Guard / notes | HTMX partials used |
|---|---|---|---|---|---|
| `/` | GET | `pages/home.html` | P | — | `GET /_p/home/banners` → `partials/home/banners.html`; `GET /_p/home/promo-cards` → `partials/home/promo_cards.html` (+ mid-page banner OOB); `GET /_p/home/categories` → `partials/home/categories.html`; `GET /_p/home/products` → `partials/home/products.html` (uses `partials/product_card.html`) |
| `/shop` | GET | `pages/shop.html` | P | `?category`, `?search`, `?sort`; empty `search` → 303 `/shop` | `GET /shop/_results` → `partials/shop/results.html`; `GET /shop/_categories` → `partials/shop/categories.html` |
| `/about` | GET | `pages/about.html` | P | — | — |
| `/contact` | GET | `pages/contact.html` | P | — | `POST /contact` → `partials/contact_form.html` (errors) or `HX-Trigger: openWhatsApp` + reset form |
| `/login` | GET, POST | `pages/auth/login.html` | P | POST: rate-limited; success → redirect rules D-44 | POST (HTMX) → `partials/auth/login_form.html` on error, `HX-Redirect` on success |
| `/register` | GET, POST | `pages/auth/register.html` | P | POST rate-limited | POST (HTMX) → `partials/auth/register_form.html` on error, `HX-Redirect` on success |
| `/logout` | POST | — | P | Clears the session (works without one), redirect `/` + toast | — |
| `/cart` | GET | `pages/cart.html` | P (U content) | Guest → "Please Login" panel (FR-UI-029) | `GET /cart/_body` → `partials/cart/body.html` (lines + summary + delivery form) |
| `/cart/add` | POST | `partials/product_card.html` + OOB `partials/header_cart_badge.html` | U | Guest → 401 + `HX-Trigger` per source page (D-53) | (used by product cards on Home and Shop) |
| `/cart/items/{product_id}` | PUT | `partials/cart/body.html` + OOB badge | U | HTMX 401 → `HX-Redirect` login | quantity set |
| `/cart/items/{product_id}` | DELETE | same | U | same | remove line |
| `/cart/items/{product_id}/selected` | PUT | same | U | same | toggle selection |
| `/cart/selection` | PUT | same | U | same | select / deselect all |
| `/cart/checkout` | POST | `partials/cart/delivery_form.html` (errors) | U | Success: pending order in session, `HX-Trigger: openWhatsApp`, `HX-Redirect: /whatsapp-confirm` | — |
| `/cart/pending-order` | DELETE | `partials/cart/pending_banner.html` | U | Discard pending order | — |
| `/whatsapp-confirm` | GET | `pages/checkout/confirm.html` | U | Anon → `/login?redirect=%2Fwhatsapp-confirm`; no pending → `/cart` + toast | — |
| `/whatsapp-confirm` | POST | — | U | Creates the order; success `HX-Redirect: /my-orders` + toast; failure toast, pending kept | — |
| `/my-orders` | GET | `pages/orders/list.html` | U | Anon → `/login?redirect=%2Fmy-orders` | `GET /my-orders/_list` → `partials/orders/list.html` (load + Retry) |
| `/my-orders/{id}` | GET | `pages/orders/detail.html` | U (owner) | Anon → login; not owner/invalid/missing → `/my-orders` + toast "Order not found" | — |
| `/healthz`, `/api` | GET | JSON | P | `{"msg":"api is working"}` | — |
| `/uploads/{filename}` | GET | file | P | D-13 | — |
| `/static/*` | GET | file | P | — | — |
| (unknown) | * | `errors/404.html` | P | — | — |

### 4.2 Admin (admin layout = sidebar, no site header/footer)

Full-page GET as anonymous → `/login?redirect=<path>`; as non-admin → `/` + toast. HTMX / state-changing as non-admin → 403 + toast (D-52).

| URL | Method | Template | HTMX partials |
|---|---|---|---|
| `/admin` | GET | `admin/dashboard.html` | `GET /admin/_p/stats` → `admin/partials/dashboard_stats.html` (cards + status counts); `GET /admin/_p/recent-orders` → `admin/partials/recent_orders.html` |
| `/admin/categories` | GET | `admin/categories.html` | `GET /admin/categories/_table?q=` → `admin/partials/categories_table.html`; `GET /admin/categories/new`, `GET /admin/categories/{id}/edit` → `admin/partials/category_form.html` |
| `/admin/categories` | POST | — | create → table + toast, or form with errors |
| `/admin/categories/{id}` | PUT / DELETE | — | update → table / form errors; delete → table + toast (`hx-confirm`) |
| `/admin/products` | GET | `admin/products.html` | `GET /admin/products/_table?q=` → `admin/partials/products_table.html`; `GET /admin/products/new`, `GET /admin/products/{id}/edit` → `admin/partials/product_form.html` |
| `/admin/products` | POST | — | create |
| `/admin/products/{id}` | PUT / DELETE | — | update / delete |
| `/admin/banner` | GET | `admin/merch.html` | `GET /admin/banner/_list` → `admin/partials/merch_list.html`; form `admin/partials/merch_form.html` |
| `/admin/banner` | POST | — | create → reset form + list + toast |
| `/admin/banner/{id}` | DELETE | — | delete → list + toast |
| `/admin/promo-card` | GET | `admin/merch.html` | `GET /admin/promo-card/_list` → `admin/partials/merch_list.html`; form `admin/partials/merch_form.html` |
| `/admin/promo-card` | POST | — | create |
| `/admin/promo-card/{id}` | DELETE | — | delete |
| `/admin/orders` | GET | `admin/orders.html` | `GET /admin/orders/_table?q=&status=&page=` → `admin/partials/orders_table.html` (+ `orders_stats.html` OOB); `GET /admin/orders/{id}` → `admin/partials/order_modal.html` |
| `/admin/orders/{id}/status` | PUT | — | returns updated `admin/partials/order_row.html` (+ modal OOB if open) + toast |

### 4.3 Shared templates and components

`base.html` (document, meta CSRF, toast region, HTMX global indicator) · `layouts/site.html` · `layouts/admin.html` · `components/header.html` · `components/footer.html` · `components/ui.html` (macros: button, link_button, field, input, textarea, select, checkbox, file_input, field_error, alert, badge, card, modal, empty_state, error_state, skeleton, pagination, spinner) · `components/status_pill.html` · `components/order_timeline.html` · `partials/product_card.html` · `partials/header_cart_badge.html` · `partials/toast_oob.html` · `errors/404.html`, `errors/403.html`, `errors/500.html` · text template `whatsapp/order_message.txt`, `whatsapp/contact_message.txt`.

### 4.4 JSON compatibility API (`/api/*`, D-01)

| # | Method | Path | Access | Service call |
|---|---|---|---|---|
| 1 | POST | `/api/auth/register` | P (rate-limited) | `auth_service.register` |
| 2 | POST | `/api/auth/login` | P (rate-limited) | `auth_service.login` |
| 3 | GET | `/api/auth/me` | U | — |
| 4 | POST | `/api/auth/logout` | P | `sessions.delete` |
| 5 | POST | `/api/category/create-category` | A | `category_service.create` |
| 6 | GET | `/api/category/get-category` | P | `category_service.list_all` |
| 7 | PUT | `/api/category/update-category/{id}` | A | `category_service.update` |
| 8 | DELETE | `/api/category/delete-category/{id}` | A | `category_service.delete` |
| 9 | POST | `/api/product/create-product` | A | `product_service.create` |
| 10 | GET | `/api/product/get-product` | P | `product_service.list_all` |
| 11 | PUT | `/api/product/update-product/{id}` | A | `product_service.update` |
| 12 | DELETE | `/api/product/delete-product/{id}` | A | `product_service.delete` |
| 13 | GET | `/api/cart` | U | `cart_service.get` |
| 14 | POST | `/api/cart/add` | U | `cart_service.add` |
| 15 | PUT | `/api/cart/update` | U | `cart_service.set_quantity` |
| 16 | DELETE | `/api/cart/remove/{productId}` | U | `cart_service.remove` |
| 17 | PUT | `/api/cart/toggle` | U | `cart_service.set_selected` |
| 18 | PUT | `/api/cart/select-all` | U | `cart_service.select_all` (M-01) |
| 19 | DELETE | `/api/cart/clear` | U | `cart_service.clear` |
| 20 | POST | `/api/order/create` | U | `order_service.create_from_items` |
| 21 | GET | `/api/order/my-orders` | U | `order_service.list_for_user` |
| 22 | GET | `/api/order/my-orders/{id}` | U | `order_service.get_for_user` |
| 23 | GET | `/api/order/all` | A | `order_service.list_all` |
| 24 | PUT | `/api/order/status/{id}` | A | `order_service.change_status` |
| 25 | POST | `/api/banner/create-banner` | A | `banner_service.create` |
| 26 | GET | `/api/banner/get-banner` | P | `banner_service.list_active` |
| 27 | GET | `/api/banner/get-all-banner` | A | `banner_service.list_all` |
| 28 | DELETE | `/api/banner/delete-banner/{id}` | A | `banner_service.delete` |
| 29 | POST | `/api/promo-card/create-promo-card` | A | `promo_service.create` |
| 30 | GET | `/api/promo-card/get-promo-card` | P | `promo_service.list_active` |
| 31 | GET | `/api/promo-card/get-all-promo-card` | A | `promo_service.list_all` |
| 32 | DELETE | `/api/promo-card/delete-promo-card/{id}` | A | `promo_service.delete` |

API guard responses: no/invalid session → 401 `{"success":false,"message":"Please login first"}` / `"Invalid or expired session"` / `"User not found"`; non-admin → 403 `"Admin access required"`; bad origin on a write → 403 `"Request origin not allowed"`.

### 4.5 Guard behaviour matrix

| Request kind | Anonymous | Logged-in non-admin on admin route | CSRF/origin failure |
|---|---|---|---|
| Full page GET (user page) | 303 → `/login?redirect=<path>` (Cart: in-page panel) | — | — |
| Full page GET (admin page) | 303 → `/login?redirect=<path>` | 303 → `/` + toast "Admin access required" | — |
| HTMX request | 401 + `HX-Redirect: /login?redirect=<current page>` (add-to-cart: D-53) | 403 + toast | 403 + toast "Your session has expired…" |
| Non-HTMX form POST | 303 → login | 403 page | 403 page |
| `/api/*` | 401 JSON | 403 JSON | 403 JSON |

---

## 5. Data models → collections

All existing collections keep their BE §4 fields exactly (D-09). `createdAt`, `updatedAt` (UTC dates) and `__v` (int) are on every document.

| Collection | Pydantic model(s) | Fields (type) | Indexes |
|---|---|---|---|
| `users` | `UserDoc` | `_id` ObjectId · `name` str · `email` str (lowercase, trimmed) · `phone` str="" · `password` str (bcrypt) · `address` str="" · `city` str="" · `pincode` str="" · `role` "user"\|"admin"="user" | `email` unique |
| `categories` | `CategoryDoc` | `_id` · `name` str · `description` str="" · `image` str (`/uploads/…`) | `name` unique |
| `products` | `ProductDoc` | `_id` · `name` str · `category` ObjectId · `price` number ≥ 1 · `oldPrice` number ≥ 1 (**absent** when unset) · `stock` int ≥ 0 · `description` str="" · `image` str | — |
| `carts` | `CartDoc`, `CartItem` | `_id` · `user` ObjectId · `items` [ {`product` ObjectId, `quantity` int ≥ 1 = 1, `selected` bool = true} ] (no item `_id`) | `user` unique |
| `orders` | `OrderDoc`, `Customer`, `OrderItem`, `StatusDates` | `_id` · `orderId` str · `user` ObjectId · `customer` {name, mobile, address, city, pincode, message=""} · `items` [ {product ObjectId, name, image="", price, quantity, total} ] · `itemsTotal` · `shipping`=0 · `shippingStatus` "FREE"\|"PAYABLE_SEPARATELY"\|null · `grandTotal` · `paymentMethod`="WhatsApp Order" · `status` enum = "Pending" · `statusDates` {Pending, Confirmed, Processing, Shipped, Delivered, Cancelled: date\|null} · `expectedDelivery` date\|null | `orderId` unique; `user` |
| `banners` | `BannerDoc` | `_id` · `title` · `subtitle`="" · `image` · `buttonText`="Shop Now" · `buttonLink`="/shop" · `order` number=0 · `status` bool=true | — |
| `promocards` | `PromoCardDoc` | as banners + `background` str="#08aaa6" | — |
| `sessions` *(new, D-04)* | `SessionDoc` | `_id` str (sha256 of token) · `user` ObjectId · `createdAt` · `expiresAt` · `pendingOrder` object\|null (orderId, customer, items, itemsTotal, shipping, shippingStatus, grandTotal, createdAt) | `expiresAt` TTL (expireAfterSeconds 0); `user` |
| `rate_limits` *(new, D-07)* | — | `_id` str (bucket key) · `count` int · `expiresAt` date | `expiresAt` TTL |

Populate rules (API responses): cart `items[].product` → full product or `null`; order `items[].product` → full product or `null`; order `user` → user without `password` in create / all / status responses (FR-092/095/103), id string in my-orders responses (FR-093/094).

---

## 6. Traceability table

Status values: **Planned** → *Implemented* → *Tested*. Updated as each module finishes.
Test paths are relative to `tests/`. "Dec." = deviation or decision reference.

### 6.1 Backend FRs (BE §12)

| ID | Requirement (short) | Module | Route(s) | Template(s) | Planned test(s) | Dec. | Status |
|---|---|---|---|---|---|---|---|
| FR-001 | Listen on `PORT`, default 9000 | M0 | `python -m app` | — | unit/test_core.py::test_port_default_9000 | D-03 | Implemented + Tested |
| FR-002 | Health check JSON | M0 | `GET /healthz`, `GET /api` | — | routes/test_platform.py::test_healthz | D-02 | Implemented + Tested |
| FR-003 | CORS allow-origin + credentials | M0 | `/api/*` | — | routes/test_platform.py::test_cors_allowed_origin, ::test_cors_unknown_origin_no_headers | D-19 | Implemented + Tested |
| FR-004 | Preflight 204 | M0 | `OPTIONS /api/*` | — | routes/test_platform.py::test_cors_preflight_204 | D-19 | Implemented + Tested |
| FR-005 | 10 MB body limit → 413 | M0 | all | — | routes/test_platform.py::test_body_over_limit_413 | D-18 | Implemented + Tested |
| FR-006 | Serve `/uploads/<file>` | M4 | `GET /uploads/{filename}` | — | routes/test_platform.py::test_serves_file, ::test_missing_404, ::test_traversal_and_dotfiles_404 | D-13 | Implemented + Tested |
| FR-007 | 404 for unknown routes | M0 | * | `errors/404.html` | routes/test_platform.py::test_unknown_page_404_html, ::test_unknown_api_404_json | D-51 | Implemented + Tested |
| FR-008 | DB connect log / exit 1 | M0 | lifespan | — | routes/test_platform.py::test_startup_exits_when_db_unreachable | D-08 | Implemented + Tested |
| FR-009 | Indexes | M0 | lifespan | — | routes/test_platform.py::test_indexes_created | D-09 | Implemented + Tested |
| FR-010 | `createdAt`/`updatedAt`/`__v` | M0 | all writes | — | unit/test_core.py::test_new_doc_meta, ::test_touch_updates_updated_at_and_version; routes/test_api_cart.py::test_version_increments | D-09 | Implemented + Tested |
| FR-011 | ObjectId hex / ISO ms dates | M0 | `/api/*` | — | unit/test_core.py::test_objectid_and_datetime | D-11 | Implemented + Tested |
| FR-012 | Case-insensitive, optional trailing slash | M0 | middleware | — | routes/test_platform.py::test_case_insensitive_and_trailing_slash | D-17 | Implemented + Tested |
| FR-013 | Register: required fields → 400 | M2 | `POST /register`, `POST /api/auth/register` | `pages/auth/register.html` | routes/test_api_auth.py::test_register_missing_fields; routes/test_auth_pages.py::test_register_missing_fields | D-27 | Implemented + Tested |
| FR-014 | Password < 6 → 400 | M2 | same | same | routes/test_api_auth.py::test_register_short_password; routes/test_auth_pages.py::test_register_mismatch_and_short_password | D-05 | Implemented + Tested |
| FR-015 | Email trim + lowercase | M2 | register/login | — | routes/test_api_auth.py::test_email_normalised | — | Implemented + Tested |
| FR-016 | Duplicate email → 409 | M2 | register | same | routes/test_api_auth.py::test_register_duplicate_409; routes/test_auth_pages.py::test_register_duplicate_message | D-24 | Implemented + Tested |
| FR-017 | bcrypt cost 10 | M1 | — | — | unit/test_security.py::test_hash_is_2a_cost10, ::test_verifies_legacy_2a_hash, ::test_verifies_2b_hash | D-05 | Implemented + Tested |
| FR-018 | Role always `user` | M2 | register | — | routes/test_api_auth.py::test_register_ignores_role | — | Implemented + Tested |
| FR-019 | Trimmed name / phone | M2 | register | — | routes/test_api_auth.py::test_register_trims_fields | — | Implemented + Tested |
| FR-020 | Register sets cookie, 201 + user | M2 | register | — | routes/test_api_auth.py::test_register_success_sets_session | D-04, M-15 | Implemented + Tested |
| FR-021 | Register unexpected error → 500 generic | M2 | register | `errors/500.html` | routes/test_api_auth.py::test_register_unexpected_error_generic | D-20 | Implemented + Tested |
| FR-022 | Login required fields → 400 | M2 | `POST /login`, `POST /api/auth/login` | `pages/auth/login.html` | routes/test_api_auth.py::test_login_missing_fields | — | Implemented + Tested |
| FR-023 | Invalid credentials → 401 | M2 | login | same | routes/test_api_auth.py::test_login_invalid_credentials | — | Implemented + Tested |
| FR-024 | Login success, cookie + profile | M2 | login | — | routes/test_api_auth.py::test_login_success_profile_and_cookie | D-04 | Implemented + Tested |
| FR-025 | Login unexpected error → 500 generic | M2 | login | — | routes/test_api_auth.py::test_login_unexpected_error_generic | D-20 | Implemented + Tested |
| FR-026 | Session token, 7-day expiry | M1 | — | — | unit/test_security.py::test_session_expires_after_7_days, ::test_token_stored_hashed_and_session_loaded | D-04 | Implemented + Tested |
| FR-027 | Cookie attributes | M1 | — | — | unit/test_security.py::test_cookie_attributes | D-04 | Implemented + Tested |
| FR-028 | Token read from cookie only | M1 | — | — | routes/test_guards.py::test_authorization_header_ignored | D-04 | Implemented + Tested |
| FR-029 | No cookie → 401 "Please login first" | M1 | protected routes | — | routes/test_guards.py::test_api_no_cookie_401, ::test_page_redirects_to_login | D-45 | Implemented + Tested |
| FR-030 | Invalid/expired → 401 | M1 | protected | — | routes/test_guards.py::test_invalid_session_401, ::test_expired_session_401 | — | Implemented + Tested |
| FR-031 | User gone → 401 "User not found" | M1 | protected | — | routes/test_guards.py::test_deleted_user_401 | — | Implemented + Tested |
| FR-032 | Load user per request, DB role | M1 | protected | — | routes/test_guards.py::test_role_change_takes_effect_immediately | — | Implemented + Tested |
| FR-033 | Non-admin → 403 | M1 | admin routes | — | routes/test_guards.py::test_non_admin_api_403, ::test_non_admin_htmx_403, ::test_admin_page_non_admin_redirects_home | D-52 | Implemented + Tested |
| FR-034 | `GET /api/auth/me` | M2 | `GET /api/auth/me` | — | routes/test_api_auth.py::test_me_returns_profile, ::test_me_anonymous_401 | — | Implemented + Tested |
| FR-035 | Logout clears session, no auth needed | M2 | `POST /logout`, `POST /api/auth/logout` | — | routes/test_api_auth.py::test_logout_invalidates_session; routes/test_auth_pages.py::test_logout_redirects_home_with_toast | D-04 | Implemented + Tested |
| FR-036 | Never return password | M2 | all | — | routes/test_api_auth.py::test_password_never_returned; routes/test_api_order.py::test_populated_user_has_no_password | — | Implemented + Tested |
| FR-037 | Create category (multipart) | M5 | `POST /admin/categories`, `POST /api/category/create-category` | `admin/partials/category_form.html` | routes/test_admin_categories.py::test_create; routes/test_api_category.py::test_create | D-12 | Implemented + Tested |
| FR-038 | Blank name → 400 | M5 | same | same | routes/test_api_category.py::test_create_blank_name | — | Implemented + Tested |
| FR-039 | No image → 400 | M5 | same | same | routes/test_api_category.py::test_create_without_image | — | Implemented + Tested |
| FR-040 | Duplicate name → 409 | M5 | create/update | same | routes/test_api_category.py::test_create_duplicate_case_insensitive, ::test_rename_duplicate | D-24 | Implemented + Tested |
| FR-041 | 201 response shape | M5 | API create | — | routes/test_api_category.py::test_create_response_shape | D-21 | Implemented + Tested |
| FR-042 | List categories (public) | M5 | `GET /api/category/get-category` | — | routes/test_api_category.py::test_list_public_shape | D-21 | Implemented + Tested |
| FR-043 | Invalid id → 400 | M5 | update/delete | — | routes/test_api_category.py::test_invalid_id_400; routes/test_admin_categories.py::test_invalid_id_404 | D-20 | Implemented + Tested |
| FR-044 | Not found → 404 | M5 | update/delete | — | routes/test_api_category.py::test_not_found_404 | — | Implemented + Tested |
| FR-045 | Partial update, 200 | M5 | `PUT /admin/categories/{id}`, `PUT /api/category/update-category/{id}` | `admin/partials/category_form.html` | routes/test_api_category.py::test_update_partial; routes/test_admin_categories.py::test_update_keeps_image_when_none | — | Implemented + Tested |
| FR-046 | Replace image → delete old file | M5 | update | — | routes/test_api_category.py::test_update_image_deletes_old_file | D-35 | Implemented + Tested |
| FR-047 | Failed update → no orphan upload | M5 | update | — | routes/test_api_category.py::test_failed_update_leaves_no_file | D-12 | Implemented + Tested |
| FR-048 | Delete blocked when products exist → 409 | M5 | delete | — | routes/test_api_category.py::test_delete_with_products_409; routes/test_admin_categories.py::test_delete_with_products_message | — | Implemented + Tested |
| FR-049 | Delete doc + image, 200 + data | M5 | `DELETE /admin/categories/{id}`, API delete | — | routes/test_api_category.py::test_delete_removes_doc_and_file | — | Implemented + Tested |
| FR-050 | Create product (multipart) | M6 | `POST /admin/products`, `POST /api/product/create-product` | `admin/partials/product_form.html` | routes/test_admin_products.py::test_create; routes/test_api_product.py::test_create | — | Implemented + Tested |
| FR-051 | Required fields → 400 | M6 | create | same | routes/test_api_product.py::test_create_missing_required | — | Implemented + Tested |
| FR-052 | No image → 400 | M6 | create | same | routes/test_api_product.py::test_create_without_image | — | Implemented + Tested |
| FR-053 | Invalid / unknown category | M6 | create/update | same | routes/test_api_product.py::test_invalid_category_400, ::test_unknown_category_404 | — | Implemented + Tested |
| FR-054 | Numeric validation | M6 | create | same | unit/test_product_rules.py::test_price_stock_oldprice_rules; routes/test_api_product.py::test_create_invalid_numbers | D-25, D-26 | Implemented + Tested |
| FR-055 | Duplicate in category → 409 | M6 | create/update | same | routes/test_api_product.py::test_duplicate_in_category_409, ::test_update_duplicate_409 | D-24 | Implemented + Tested |
| FR-056 | 201 response | M6 | API create | — | routes/test_api_product.py::test_create_response_shape | — | Implemented + Tested |
| FR-057 | List products (public, category id string) | M6 | `GET /api/product/get-product` | — | routes/test_api_product.py::test_list_public_shape | D-21 | Implemented + Tested |
| FR-058 | Invalid id 400 / missing 404 | M6 | update/delete | — | routes/test_api_product.py::test_invalid_id_400, ::test_not_found_404 | — | Implemented + Tested |
| FR-059 | Partial update + messages | M6 | update | same | routes/test_api_product.py::test_update_field_messages | — | Implemented + Tested |
| FR-060 | `oldPrice: ""` unsets | M6 | update | same | routes/test_api_product.py::test_update_empty_old_price_unsets | D-25 | Implemented + Tested |
| FR-061 | oldPrice < price → 400 | M6 | create/update | same | routes/test_api_product.py::test_old_price_below_price_400 | D-25 | Implemented + Tested |
| FR-062 | Image replace cleanup / error cleanup | M6 | update | — | routes/test_api_product.py::test_update_image_replaces_file, ::test_update_failure_removes_new_file | D-12, D-35 | Implemented + Tested |
| FR-063 | 200 update response | M6 | update | — | routes/test_api_product.py::test_update_response_shape | — | Implemented + Tested |
| FR-064 | Delete doc + image | M6 | `DELETE /admin/products/{id}`, API delete | — | routes/test_api_product.py::test_delete_cleans_carts_and_unreferenced_image, ::test_delete_keeps_image_used_by_orders | D-35 | Implemented + Tested |
| FR-065 | Cart requires auth, own cart only | M8 | `/cart*`, `/api/cart*` | `pages/cart.html` | routes/test_api_cart.py::test_requires_auth; routes/test_cart_pages.py::test_guest_sees_login_panel | — | Implemented + Tested |
| FR-066 | GET creates empty cart | M8 | `GET /api/cart`, `GET /cart` | — | routes/test_api_cart.py::test_get_creates_empty_cart | D-28 | Implemented + Tested |
| FR-067 | Populated product / null | M8 | API cart responses | — | routes/test_api_cart.py::test_populated_and_missing_product | D-28 | Implemented + Tested |
| FR-068 | Add: missing productId → 400 | M8 | `POST /api/cart/add`, `POST /cart/add` | — | routes/test_api_cart.py::test_add_missing_product_id | — | Implemented + Tested |
| FR-069 | Add: unknown product → 404 | M8 | same | — | routes/test_api_cart.py::test_add_unknown_product, ::test_add_invalid_id_400 | D-20 | Implemented + Tested |
| FR-070 | Quantity default 1, < 1 → 400 | M8 | same | — | routes/test_api_cart.py::test_add_default_quantity, ::test_add_quantity_rules | D-26 | Implemented + Tested |
| FR-071 | Stock limit (incl. existing) | M8 | same | — | routes/test_api_cart.py::test_add_exceeds_stock, ::test_add_existing_line_increments_and_selects | — | Implemented + Tested |
| FR-072 | Increment + reselect / append | M8 | same | — | routes/test_api_cart.py::test_add_existing_line_increments_and_selects | — | Implemented + Tested |
| FR-073 | Update invalid data → 400 | M8 | `PUT /api/cart/update`, `PUT /cart/items/{id}` | — | routes/test_api_cart.py::test_update_invalid_data | D-26 | Implemented + Tested |
| FR-074 | Update: missing line → 404 | M8 | same | — | routes/test_api_cart.py::test_update_line_not_found | D-28 | Implemented + Tested |
| FR-075 | Update sets quantity (stock checked) | M8 | same | `partials/cart/body.html` | routes/test_api_cart.py::test_update_sets_quantity; routes/test_cart_pages.py::test_quantity_update | — | Implemented + Tested |
| FR-076 | Remove line (idempotent) | M8 | `DELETE /api/cart/remove/{id}`, `DELETE /cart/items/{id}` | same | routes/test_api_cart.py::test_remove_line, ::test_remove_absent_line_ok | D-28 | Implemented + Tested |
| FR-077 | Toggle selection | M8 | `PUT /api/cart/toggle`, `PUT /cart/items/{id}/selected` | same | unit/test_cart_rules.py::test_parse_selected; routes/test_api_cart.py::test_toggle | D-28 | Implemented + Tested |
| FR-078 | Toggle: missing line → 404 | M8 | same | — | routes/test_api_cart.py::test_toggle_missing_line_404 | — | Implemented + Tested |
| FR-079 | Clear cart | M8 | `DELETE /api/cart/clear` | — | routes/test_api_cart.py::test_clear | D-28 | Implemented + Tested |
| FR-080 | One cart per user | M8 | — | — | routes/test_api_cart.py::test_concurrent_get_single_cart; routes/test_platform.py::test_indexes_created | D-28 | Implemented + Tested |
| FR-081 | Order create requires auth | M10 | `POST /whatsapp-confirm`, `POST /api/order/create` | — | routes/test_api_order.py::test_create_requires_auth; routes/test_checkout.py::test_confirm_anonymous_redirects | — | Implemented + Tested |
| FR-082 | Customer details required | M10 | `POST /cart/checkout`, API create | `partials/cart/delivery_form.html` | routes/test_api_order.py::test_create_incomplete_customer; routes/test_checkout.py::test_delivery_validation_messages | D-27 | Implemented + Tested |
| FR-083 | At least one item | M10 | same | — | routes/test_api_order.py::test_create_no_items; routes/test_checkout.py::test_no_selected_items | — | Implemented + Tested |
| FR-084 | `product` or `productId` | M10 | API create | — | routes/test_api_order.py::test_create_accepts_product_or_product_id | M-22 | Implemented + Tested |
| FR-085 | Line total = price × qty | M10 | create | — | unit/test_order_rules.py::test_lines_priced_from_db | D-29 | Implemented + Tested |
| FR-086 | Invalid item → 400 | M10 | API create | — | routes/test_api_order.py::test_create_invalid_item, ::test_create_unknown_product | D-29 | Implemented + Tested |
| FR-087 | orderId format | M10 | checkout | — | unit/test_order_rules.py::test_order_id_format | D-34 | Implemented + Tested |
| FR-088 | Initial status, dates, expected delivery | M10 | create | — | unit/test_order_rules.py::test_new_order_status_and_dates, ::test_expected_delivery_72h | D-33 | Implemented + Tested |
| FR-089 | Totals / shipping / payment stored | M10 | create | — | unit/test_order_rules.py::test_totals_recomputed_shipping_status_threshold; routes/test_api_order.py::test_client_totals_ignored | D-29 | Implemented + Tested |
| FR-090 | Invalid shippingStatus handling | M10 | create | — | routes/test_api_order.py::test_client_shipping_status_ignored | D-29 | Implemented + Tested |
| FR-091 | Remove ordered lines from cart | M10 | create | — | unit/test_order_rules.py::test_cart_cleanup_quantities; routes/test_checkout.py::test_confirm_clears_ordered_lines_only | D-32 | Implemented + Tested |
| FR-092 | 201 with populated order | M10 | API create | — | routes/test_api_order.py::test_create_response_populated | — | Implemented + Tested |
| FR-093 | My orders, own only, newest first | M11 | `GET /my-orders`, `GET /api/order/my-orders` | `pages/orders/list.html` | routes/test_api_order.py::test_my_orders_own_newest_first; routes/test_my_orders.py::test_lists_only_own_orders | — | Implemented + Tested |
| FR-094 | Order detail owner only | M11 | `GET /my-orders/{id}`, `GET /api/order/my-orders/{id}` | `pages/orders/detail.html` | routes/test_api_order.py::test_detail_owner_only, ::test_detail_invalid_id_404; routes/test_my_orders.py::test_detail_other_user_redirects | D-50 | Implemented + Tested |
| FR-095 | All orders (admin) | M12 | `GET /admin/orders`, `GET /api/order/all` | `admin/orders.html` | routes/test_api_order.py::test_all_admin_only; routes/test_admin_orders.py::test_list_admin_only | — | Implemented + Tested |
| FR-096 | Status update admin only | M12 | `PUT /admin/orders/{id}/status`, `PUT /api/order/status/{id}` | — | routes/test_api_order.py::test_status_requires_admin; routes/test_admin_orders.py::test_status_non_admin_403 | — | Implemented + Tested |
| FR-097 | Invalid status → 400 | M12 | same | — | routes/test_api_order.py::test_status_invalid_value | — | Implemented + Tested |
| FR-098 | Unknown order → 404 | M12 | same | — | routes/test_api_order.py::test_status_order_not_found, ::test_status_invalid_id_400 | D-20 | Implemented + Tested |
| FR-099 | Stamp `statusDates[status]` | M12 | same | — | unit/test_order_rules.py::test_status_change_stamps_date_keeps_others | D-30 | Implemented + Tested |
| FR-100 | Cancel → expectedDelivery null | M12 | same | — | unit/test_order_rules.py::test_cancel_clears_expected_delivery | — | Implemented + Tested |
| FR-101 | Non-cancel with null delivery → now + 3 d | M12 | same | — | unit/test_order_rules.py::test_expected_delivery_restored_for_legacy_null | D-33 | Implemented + Tested |
| FR-102 | Transition policy | M12 | same | — | unit/test_order_rules.py::test_transition_matrix; routes/test_api_order.py::test_status_invalid_transition_400 | D-30 ⚠ | Implemented + Tested |
| FR-103 | Status response message + populated order | M12 | same | `admin/partials/order_row.html` | routes/test_api_order.py::test_status_response_shape | — | Implemented + Tested |
| FR-104 | Create banner | M7 | `POST /admin/banner`, `POST /api/banner/create-banner` | `admin/partials/merch_form.html` | routes/test_admin_merch.py::test_banner_defaults_and_reset; routes/test_api_merch.py::test_create | D-37 | Implemented + Tested |
| FR-105 | Title / image required | M7 | same | same | routes/test_api_merch.py::test_create_missing_title, ::test_create_missing_image | D-27 | Implemented + Tested |
| FR-106 | Defaults + status parsing | M7 | same | — | unit/test_merch_rules.py::test_defaults_and_status_parsing | D-37 | Implemented + Tested |
| FR-107 | 201 response | M7 | API create | — | routes/test_api_merch.py::test_create_response_shape | — | Implemented + Tested |
| FR-108 | Public list: active, sorted | M7 | `GET /api/banner/get-banner`, `/_p/home/banners` | `partials/home/banners.html` | routes/test_api_merch.py::test_public_list_active_sorted | — | Implemented + Tested |
| FR-109 | Admin list: all, sorted | M7 | `GET /api/banner/get-all-banner`, `/admin/banner/_list` | `admin/partials/merch_list.html` | routes/test_api_merch.py::test_all_admin_only_sorted | KI-01 | Implemented + Tested |
| FR-110 | Delete banner | M7 | `DELETE /admin/banner/{id}`, API delete | — | routes/test_api_merch.py::test_delete, ::test_delete_not_found_404, ::test_delete_invalid_id_400 | D-36 | Implemented + Tested |
| FR-111 | Create promo card | M7 | `POST /admin/promo-card`, `POST /api/promo-card/create-promo-card` | `admin/partials/merch_form.html` | routes/test_admin_merch.py::test_promo_defaults_and_reset; routes/test_api_merch.py::test_create | D-37 | Implemented + Tested |
| FR-112 | Title / image required | M7 | same | same | routes/test_api_merch.py::test_create_missing_title, ::test_create_missing_image | — | Implemented + Tested |
| FR-113 | Defaults incl. background | M7 | same | — | routes/test_api_merch.py::test_create | D-27 | Implemented + Tested |
| FR-114 | 201 response | M7 | API create | — | routes/test_api_merch.py::test_create_response_shape | — | Implemented + Tested |
| FR-115 | Public list active, sorted | M7 | `GET /api/promo-card/get-promo-card`, `/_p/home/promo-cards` | `partials/home/promo_cards.html` | routes/test_api_merch.py::test_public_list_active_sorted | — | Implemented + Tested |
| FR-116 | Admin list all, sorted | M7 | `GET /api/promo-card/get-all-promo-card`, `/admin/promo-card/_list` | `admin/partials/merch_list.html` | routes/test_api_merch.py::test_all_admin_only_sorted | KI-01 | Implemented + Tested |
| FR-117 | Delete promo card | M7 | `DELETE /admin/promo-card/{id}`, API delete | — | routes/test_api_merch.py::test_delete, ::test_delete_not_found_404 | D-36 | Implemented + Tested |
| FR-118 | Single file in field `image` | M4 | 6 upload points | — | unit/test_security.py::test_wrong_field_or_multiple_files_rejected | D-12 | Implemented + Tested |
| FR-119 | Allowed types | M4 | same | — | unit/test_security.py::test_type_detected_by_magic_bytes, ::test_disallowed_type_rejected | D-12 ⚠ | Implemented + Tested |
| FR-120 | Size limit | M4 | same | — | unit/test_security.py::test_oversize_rejected_413 | D-12 ⚠ | Implemented + Tested |
| FR-121 | Stored name pattern, `/uploads/<name>` | M4 | same | — | unit/test_security.py::test_stored_name_pattern_and_relative_path | D-12 | Implemented + Tested |
| FR-122 | Relative image paths in responses | M4 | all | — | unit/test_security.py::test_stored_name_pattern_and_relative_path; routes/test_api_product.py::test_create_response_shape | — | Implemented + Tested |

### 6.2 Frontend FR-UIs (FE §9)

| ID | Requirement (short) | Module | Route(s) | Template(s) | Planned test(s) | Dec. | Status |
|---|---|---|---|---|---|---|---|
| FR-UI-001 | Header/footer on site routes, not admin | M3 | all site routes; `/admin/*` | `layouts/site.html`, `layouts/admin.html` | routes/test_layout.py::test_site_pages_have_header_footer; routes/test_admin_dashboard.py::test_sidebar_links | — | Implemented + Tested |
| FR-UI-002 | Scroll to top on navigation | M3 | all | `base.html` | routes/test_layout.py::test_navigation_is_full_page | — | Implemented + Tested |
| FR-UI-003 | Toasts top-centre 3 s | M3 | all | `base.html`, `partials/toast_oob.html` | routes/test_layout.py::test_toast_region_config, ::test_htmx_toast_trigger_header | D-14 | Implemented + Tested |
| FR-UI-004 | Active nav link (HOME exact) | M3 | site | `components/header.html` | routes/test_layout.py::test_active_nav_link | — | Implemented + Tested |
| FR-UI-005 | Cart badge: sum, hidden at 0, 99+ | M3/M8 | site | `partials/header_cart_badge.html` | routes/test_layout.py::test_cart_badge_hidden_zero_and_99_plus | — | Implemented + Tested |
| FR-UI-006 | Header search → `/shop?search=` | M3 | `GET /shop` | `components/header.html` | routes/test_shop.py::test_header_search_targets_shop, ::test_empty_search_redirects_to_shop | D-48 | Implemented + Tested |
| FR-UI-007 | Login link vs My Orders / name / logout | M3 | site | `components/header.html` | routes/test_layout.py::test_header_guest_vs_user | — | Implemented + Tested |
| FR-UI-008 | Admin links only for admins | M3 | site | same | routes/test_layout.py::test_header_admin_links_only_for_admin | — | Implemented + Tested |
| FR-UI-009 | Mobile menu with same actions | M3 | site | same | routes/test_layout.py::test_mobile_menu_actions | — | Implemented + Tested |
| FR-UI-010 | Session check | M1 | all | — | routes/test_guards.py::test_user_resolved_per_request | D-45 | Implemented + Tested |
| FR-UI-011 | Cookie auth only, no Authorization header | M1 | all | — | routes/test_guards.py::test_authorization_header_ignored | D-04 | Implemented + Tested |
| FR-UI-012 | Login empty → "Please enter email and password" | M2 | `POST /login` | `partials/auth/login_form.html` | routes/test_auth_pages.py::test_login_empty_fields | — | Implemented + Tested |
| FR-UI-013 | Login posts email (trimmed) + password | M2 | `POST /login` | same | routes/test_auth_pages.py::test_login_success_trims_email | — | Implemented + Tested |
| FR-UI-014 | "Login Failed" alert + toast | M2 | `POST /login` | same | routes/test_auth_pages.py::test_login_failure_alert_and_toast | — | Implemented + Tested |
| FR-UI-015 | Post-login redirect rules | M2 | `POST /login` | — | routes/test_auth_pages.py::test_login_redirect_rules, ::test_login_rejects_open_redirect | D-44 | Implemented + Tested |
| FR-UI-016 | Error cleared on edit | M2 | `/login` | `partials/auth/login_form.html`, `app.js` | routes/test_auth_pages.py::test_login_error_has_clear_on_input_hook | — | Implemented + Tested |
| FR-UI-017 | Live register validation messages | M2 | `/register` | `partials/auth/register_form.html`, `app.js` | routes/test_auth_pages.py::test_register_live_validation_hooks, ::test_register_mismatch_and_short_password | — | Implemented + Tested |
| FR-UI-018 | "Please fill all required fields" | M2 | `POST /register` | same | routes/test_auth_pages.py::test_register_missing_fields | — | Implemented + Tested |
| FR-UI-019 | Register sends trimmed fields, no confirm stored | M2 | `POST /register` | same | routes/test_auth_pages.py::test_register_stores_trimmed_no_confirm | — | Implemented + Tested |
| FR-UI-020 | Register → logged in, toast, `/` | M2 | `POST /register` | — | routes/test_auth_pages.py::test_register_success_logs_in | — | Implemented + Tested |
| FR-UI-021 | Register failure message | M2 | `POST /register` | same | routes/test_auth_pages.py::test_register_duplicate_message | — | Implemented + Tested |
| FR-UI-022 | Logout → toast "Logout successful", `/` | M2 | `POST /logout` | — | routes/test_auth_pages.py::test_logout_redirects_home_with_toast | — | Implemented + Tested |
| FR-UI-023 | Busy labels / disabled buttons | M2 | login/register/logout | forms, `components/header.html` | routes/test_auth_pages.py::test_submit_buttons_busy_labels | — | Implemented + Tested |
| FR-UI-024 | "Checking admin access..." | M1 | `/admin/*` | — | routes/test_guards.py::test_admin_guard_resolves_before_render | D-45 | Implemented + Tested |
| FR-UI-025 | Anonymous `/admin/*` → login | M1 | `/admin/*` | — | routes/test_guards.py::test_admin_page_anonymous_redirects_login | D-44 | Implemented + Tested |
| FR-UI-026 | Non-admin `/admin/*` → `/` | M1 | `/admin/*` | — | routes/test_guards.py::test_admin_page_non_admin_redirects_home | D-52 | Implemented + Tested |
| FR-UI-027 | `/my-orders` anon → login?redirect | M11 | `GET /my-orders` | — | routes/test_my_orders.py::test_anonymous_redirects_to_login | — | Implemented + Tested |
| FR-UI-028 | `/whatsapp-confirm` anon → login?redirect | M10 | `GET /whatsapp-confirm` | — | routes/test_checkout.py::test_confirm_anonymous_redirects | — | Implemented + Tested |
| FR-UI-029 | Cart "Please Login" panel | M8 | `GET /cart` | `pages/cart.html` | routes/test_cart_pages.py::test_guest_sees_login_panel | — | Implemented + Tested |
| FR-UI-030 | Home loads 4 public sources | M9 | `GET /`, `/_p/home/*` | `pages/home.html` | routes/test_home.py::test_home_shell_and_partials_load | D-46 | Implemented + Tested |
| FR-UI-031 | Banner slider (order, 4 s, arrows, dots) | M9 | `/_p/home/banners` | `partials/home/banners.html`, `app.js` | routes/test_home.py::test_banner_slider_markup | — | Implemented + Tested |
| FR-UI-032 | "No banners available" | M9 | same | same | routes/test_home.py::test_no_banners_message | — | Implemented + Tested |
| FR-UI-033 | CTA only with title | M9 | same | same | routes/test_home.py::test_banner_cta_requires_title | — | Implemented + Tested |
| FR-UI-034 | `buttonLink` navigation rule | M9 | banners, promo cards | same | unit/test_core.py::test_cta_href_resolution | D-27 | Implemented + Tested |
| FR-UI-035 | Promo card rendering + defaults | M9 | `/_p/home/promo-cards` | `partials/home/promo_cards.html` | routes/test_home.py::test_promo_cards_render_with_defaults | — | Implemented + Tested |
| FR-UI-036 | Category tiles → `/shop?category=` | M9 | `/_p/home/categories` | `partials/home/categories.html` | routes/test_home.py::test_category_tiles_link_to_shop | — | Implemented + Tested |
| FR-UI-037 | Latest 8 products | M9 | `/_p/home/products` | `partials/home/products.html` | routes/test_home.py::test_latest_eight_products | — | Implemented + Tested |
| FR-UI-038 | Skeleton / error + Retry / empty | M9 | `/_p/home/*` | `components/ui.html` | routes/test_home.py::test_sections_empty_messages, ::test_section_error_with_retry | D-46 | Implemented + Tested |
| FR-UI-039 | Mid-page promo banner | M9 | `/_p/home/banners` | `partials/home/banners.html` | routes/test_home.py::test_mid_page_banner | — | Implemented + Tested |
| FR-UI-040 | Guest add on Home → toast, login after 1 s | M9 | `POST /cart/add` | `partials/product_card.html` | routes/test_home.py::test_guest_add_to_cart_redirects_to_login | D-53 | Implemented + Tested |
| FR-UI-041 | ₹ en-IN price format | M9 | — | filters | unit/test_core.py::test_inr | D-15 | Implemented + Tested |
| FR-UI-042 | Discount badge + struck old price | M9 | cards | `partials/product_card.html` | unit/test_core.py::test_discount_percent; routes/test_shop.py::test_card_discount_badge | — | Implemented + Tested |
| FR-UI-043 | Stock text / sold out / disabled button | M9 | cards | same | routes/test_shop.py::test_out_of_stock_card | — | Implemented + Tested |
| FR-UI-044 | Quantity 1..stock | M9 | cards, `POST /cart/add` | same | routes/test_shop.py::test_quantity_stepper_bounds; routes/test_api_cart.py::test_add_exceeds_stock | — | Implemented + Tested |
| FR-UI-045 | Shop loads all categories + products | M9 | `GET /shop` | `pages/shop.html` | routes/test_shop.py::test_shop_lists_all | D-48 | Implemented + Tested |
| FR-UI-046 | Filter by `?category` | M9 | `GET /shop/_results` | `partials/shop/results.html` | routes/test_shop.py::test_filter_by_category | — | Implemented + Tested |
| FR-UI-047 | Sidebar sets/removes category, closes drawer | M9 | `/shop` | `partials/shop/categories.html` | routes/test_shop.py::test_sidebar_links_set_category | — | Implemented + Tested |
| FR-UI-048 | Per-category counts | M9 | `/shop` | same | routes/test_shop.py::test_category_counts | — | Implemented + Tested |
| FR-UI-049 | Search box ↔ `?search` | M9 | `/shop` | `pages/shop.html` | routes/test_shop.py::test_search_param_prefills_and_pushes_url | D-48 | Implemented + Tested |
| FR-UI-050 | Search name / category / description | M9 | `/shop/_results` | — | unit/test_shop_filter.py::test_search_matches_fields_case_insensitive | — | Implemented + Tested |
| FR-UI-051 | Sort options | M9 | `/shop/_results` | — | unit/test_shop_filter.py::test_sort_options | — | Implemented + Tested |
| FR-UI-052 | Heading + "{n} products found" | M9 | `/shop/_results` | `partials/shop/results.html` | routes/test_shop.py::test_heading_and_count | — | Implemented + Tested |
| FR-UI-053 | "No Candles Found" + View All | M9 | same | same | routes/test_shop.py::test_no_candles_found | — | Implemented + Tested |
| FR-UI-054 | Guest add on Shop → banner + toast | M9 | `POST /cart/add` | same | routes/test_shop.py::test_guest_add_shows_message | D-53 | Implemented + Tested |
| FR-UI-055 | Success message + qty reset | M9 | `POST /cart/add` | `partials/product_card.html` | routes/test_shop.py::test_add_success_message_and_reset | — | Implemented + Tested |
| FR-UI-056 | Wishlist heart | M9 | cards | `partials/product_card.html`, `app.js` | routes/test_shop.py::test_wishlist_toggle_markup | D-43 | Implemented + Tested |
| FR-UI-057 | Cart reflects logged-in user | M8 | `GET /cart` | `pages/cart.html` | routes/test_cart_pages.py::test_cart_belongs_to_user | — | Implemented + Tested |
| FR-UI-058 | Drop lines without product | M8 | `GET /cart` | `partials/cart/body.html` | routes/test_cart_pages.py::test_missing_product_lines_hidden_and_pruned | D-28 | Implemented + Tested |
| FR-UI-059 | Out-of-stock add refused | M8 | `POST /cart/add` | `partials/product_card.html` | routes/test_cart_pages.py::test_add_out_of_stock_message | — | Implemented + Tested |
| FR-UI-060 | Add → cart replaced from server | M8 | `POST /cart/add` | + badge OOB | routes/test_cart_pages.py::test_add_updates_badge | — | Implemented + Tested |
| FR-UI-061 | "Your Cart Is Empty" | M8 | `GET /cart` | `partials/cart/body.html` | routes/test_cart_pages.py::test_empty_cart_state | — | Implemented + Tested |
| FR-UI-062 | Line list with totals | M8 | same | same | routes/test_cart_pages.py::test_lines_show_unit_and_item_total | — | Implemented + Tested |
| FR-UI-063 | −/+ with bounds | M8 | `PUT /cart/items/{id}` | same | routes/test_cart_pages.py::test_quantity_buttons_bounds | D-47 | Implemented + Tested |
| FR-UI-064 | Remove | M8 | `DELETE /cart/items/{id}` | same | routes/test_cart_pages.py::test_remove_line | — | Implemented + Tested |
| FR-UI-065 | Items total over selected lines | M8 | — | same | unit/test_cart_rules.py::test_items_total_selected_only | — | Implemented + Tested |
| FR-UI-066 | FREE vs Pay Separately + amount needed | M8 | — | same | unit/test_cart_rules.py::test_free_delivery_threshold; routes/test_cart_pages.py::test_delivery_messages | — | Implemented + Tested |
| FR-UI-067 | Grand total = items total | M8 | — | same | unit/test_cart_rules.py::test_grand_total_equals_items_total | — | Implemented + Tested |
| FR-UI-068 | Delivery form prefill | M10 | `GET /cart` | `partials/cart/delivery_form.html` | routes/test_checkout.py::test_delivery_form_prefilled_from_user | — | Implemented + Tested |
| FR-UI-069 | Digits-only mobile (10) / pincode (6) | M10 | `POST /cart/checkout` | same | unit/test_core.py::test_digits_normalisation; routes/test_checkout.py::test_inputs_restricted | — | Implemented + Tested |
| FR-UI-070 | Delivery validation messages + scroll | M10 | `POST /cart/checkout` | same | routes/test_checkout.py::test_delivery_validation_messages | — | Implemented + Tested |
| FR-UI-071 | Mobile / pincode patterns | M10 | same | — | unit/test_core.py::test_mobile_and_pincode_patterns | D-27 | Implemented + Tested |
| FR-UI-072 | "Please select at least one product." | M10 | same | — | routes/test_checkout.py::test_no_selected_items | — | Implemented + Tested |
| FR-UI-073 | Store pending order | M10 | `POST /cart/checkout` | — | routes/test_checkout.py::test_checkout_stores_pending_order_in_session | D-39 | Implemented + Tested |
| FR-UI-074 | shippingStatus by threshold | M10 | — | — | unit/test_cart_rules.py::test_shipping_status_threshold | D-29 | Implemented + Tested |
| FR-UI-075 | WhatsApp message + new tab | M10 | `POST /cart/checkout` | `whatsapp/order_message.txt` | unit/test_whatsapp.py::test_order_message_sections; routes/test_checkout.py::test_checkout_triggers_open_whatsapp | D-34, D-39 | Implemented + Tested |
| FR-UI-076 | Reach confirm page after WhatsApp | M10 | `POST /cart/checkout` → `/whatsapp-confirm` | — | routes/test_checkout.py::test_checkout_redirects_to_confirm, ::test_cart_shows_pending_banner | D-39 ⚠ | Implemented + Tested |
| FR-UI-077 | Missing pending → `/cart` + toast | M10 | `GET /whatsapp-confirm` | — | routes/test_checkout.py::test_confirm_without_pending_redirects_to_cart | — | Implemented + Tested |
| FR-UI-078 | Confirm page shows details | M10 | same | `pages/checkout/confirm.html` | routes/test_checkout.py::test_confirm_page_shows_details | — | Implemented + Tested |
| FR-UI-079 | "Send WhatsApp Again" | M10 | same | same | routes/test_checkout.py::test_send_again_link_contains_order_id | D-34 | Implemented + Tested |
| FR-UI-080 | Create order on confirm | M10 | `POST /whatsapp-confirm` | — | routes/test_checkout.py::test_confirm_creates_order | D-29 | Implemented + Tested |
| FR-UI-081 | Post-success: cart cleaned, pending cleared, toast, `/my-orders` | M10 | same | — | routes/test_checkout.py::test_confirm_success_flow | D-32 | Implemented + Tested |
| FR-UI-082 | Failure: message, pending kept | M10 | same | — | routes/test_checkout.py::test_confirm_failure_keeps_pending | — | Implemented + Tested |
| FR-UI-083 | Buttons disabled, "Placing Order..." | M10 | same | `pages/checkout/confirm.html` | routes/test_checkout.py::test_confirm_buttons_busy_markup | — | Implemented + Tested |
| FR-UI-084 | Load my orders (`orders`) | M11 | `GET /my-orders/_list` | `partials/orders/list.html` | routes/test_my_orders.py::test_lists_only_own_orders | — | Implemented + Tested |
| FR-UI-085 | "No Orders Yet" | M11 | same | same | routes/test_my_orders.py::test_no_orders_state, ::test_error_state_with_retry | D-49 | Implemented + Tested |
| FR-UI-086 | Order card contents | M11 | same | same | routes/test_my_orders.py::test_order_card_contents | — | Implemented + Tested |
| FR-UI-087 | Current-status label/date | M11 | — | `components/status_pill.html` | unit/test_order_view.py::test_current_status_label | — | Implemented + Tested |
| FR-UI-088 | Card links to `/my-orders/{_id}` | M11 | same | same | routes/test_my_orders.py::test_order_card_links_to_detail | — | Implemented + Tested |
| FR-UI-089 | Detail load / error redirect | M11 | `GET /my-orders/{id}` | `pages/orders/detail.html` | routes/test_my_orders.py::test_detail_page, ::test_detail_not_found_redirects_with_toast | D-50 | Implemented + Tested |
| FR-UI-090 | 5-step tracking | M11 | same | `components/order_timeline.html` | unit/test_order_view.py::test_tracking_steps | — | Implemented + Tested |
| FR-UI-091 | Cancelled 3-step + notice | M11 | same | same | unit/test_order_view.py::test_cancelled_tracking; routes/test_my_orders.py::test_cancelled_notice | — | Implemented + Tested |
| FR-UI-092 | Delivery details + summary + shipping label | M11 | same | `pages/orders/detail.html` | unit/test_order_view.py::test_shipping_label; routes/test_my_orders.py::test_detail_summary | — | Implemented + Tested |
| FR-UI-093 | Date formats | M3 | — | filters | unit/test_core.py::test_dates_en_in | D-14 | Implemented + Tested |
| FR-UI-094 | Contact form → WhatsApp | M3 | `POST /contact` | `partials/contact_form.html` | routes/test_static_pages.py::test_contact_validation, ::test_contact_triggers_whatsapp; unit/test_whatsapp.py::test_contact_message | — | Implemented + Tested |
| FR-UI-095 | Contact details + socials | M3 | `GET /contact` | `pages/contact.html` | routes/test_static_pages.py::test_contact_details | D-41, D-42 | Implemented + Tested |
| FR-UI-096 | About page | M3 | `GET /about` | `pages/about.html` | routes/test_static_pages.py::test_about_content_and_links | D-40 | Implemented + Tested |
| FR-UI-097 | Admin sidebar | M13 | `/admin/*` | `layouts/admin.html` | routes/test_admin_dashboard.py::test_sidebar_links | — | Implemented + Tested |
| FR-UI-098 | Dashboard loads; error shown | M13 | `/admin/_p/*` | `admin/dashboard.html` | routes/test_admin_dashboard.py::test_section_error_isolated | D-46 | Implemented + Tested |
| FR-UI-099 | Counts + Delivered Revenue | M13 | `/admin/_p/stats` | `admin/partials/dashboard_stats.html` | routes/test_admin_dashboard.py::test_counts_and_delivered_revenue | — | Implemented + Tested |
| FR-UI-100 | Counts per status | M13 | same | same | routes/test_admin_dashboard.py::test_status_counts | — | Implemented + Tested |
| FR-UI-101 | 5 most recent orders | M13 | `/admin/_p/recent-orders` | `admin/partials/recent_orders.html` | routes/test_admin_dashboard.py::test_recent_orders | — | Implemented + Tested |
| FR-UI-102 | Refresh with "Refreshing..." | M13 | `/admin/_p/*` | `admin/dashboard.html` | routes/test_admin_dashboard.py::test_refresh_markup | — | Implemented + Tested |
| FR-UI-103 | Categories list + search | M5 | `/admin/categories/_table` | `admin/partials/categories_table.html` | routes/test_admin_categories.py::test_list_and_search | — | Implemented + Tested |
| FR-UI-104 | Image type/size messages | M5 | create/update | `admin/partials/category_form.html` | routes/test_admin_categories.py::test_image_type_and_size_messages | D-12 | Implemented + Tested |
| FR-UI-105 | Name / image required messages | M5 | same | same | routes/test_admin_categories.py::test_form_validation_messages | — | Implemented + Tested |
| FR-UI-106 | Multipart create/update | M5 | `POST`/`PUT` | same | routes/test_admin_categories.py::test_create, ::test_update_keeps_image_when_none | — | Implemented + Tested |
| FR-UI-107 | Success messages + refresh | M5 | same | table | routes/test_admin_categories.py::test_success_messages | — | Implemented + Tested |
| FR-UI-108 | Confirmed delete | M5 | `DELETE` | table | routes/test_admin_categories.py::test_delete_flow | — | Implemented + Tested |
| FR-UI-109 | Product table + search | M6 | `/admin/products/_table` | `admin/partials/products_table.html` | routes/test_admin_products.py::test_list_and_search | D-25 | Implemented + Tested |
| FR-UI-110 | Product validation order + messages | M6 | create/update | `admin/partials/product_form.html` | routes/test_admin_products.py::test_validation_order_and_messages | D-25 | Implemented + Tested |
| FR-UI-111 | Multipart create/update | M6 | `POST`/`PUT` | same | routes/test_admin_products.py::test_create, ::test_update | — | Implemented + Tested |
| FR-UI-112 | Edit prefill | M6 | `GET /admin/products/{id}/edit` | same | routes/test_admin_products.py::test_edit_form_prefilled | — | Implemented + Tested |
| FR-UI-113 | Confirmed delete + message | M6 | `DELETE` | table | routes/test_admin_products.py::test_delete_flow | — | Implemented + Tested |
| FR-UI-114 | Banner form validation + fields | M7 | `POST /admin/banner` | `admin/partials/merch_form.html` | routes/test_admin_merch.py::test_banner_validation_messages | — | Implemented + Tested |
| FR-UI-115 | Form defaults + reset after upload | M7 | banner/promo create | forms | routes/test_admin_merch.py::test_banner_defaults_and_reset; routes/test_admin_merch.py::test_promo_defaults_and_reset | — | Implemented + Tested |
| FR-UI-116 | Banner list + confirmed delete | M7 | `/admin/banner/_list` | `admin/partials/merch_list.html` | routes/test_admin_merch.py::test_list_and_delete | D-37 | Implemented + Tested |
| FR-UI-117 | Promo validation + fields | M7 | `POST /admin/promo-card` | `admin/partials/merch_form.html` | routes/test_admin_merch.py::test_promo_validation_messages | — | Implemented + Tested |
| FR-UI-118 | Colour picker + coloured cards | M7 | same | `admin/partials/merch_list.html` | routes/test_admin_merch.py::test_colour_picker_and_background | D-27 | Implemented + Tested |
| FR-UI-119 | Success toasts | M7 | create/delete | — | routes/test_admin_merch.py::test_success_toasts | — | Implemented + Tested |
| FR-UI-120 | Load all orders | M12 | `/admin/orders/_table` | `admin/partials/orders_table.html` | routes/test_admin_orders.py::test_table_lists_orders_paginated | D-16 | Implemented + Tested |
| FR-UI-121 | Order stats | M12 | same | `admin/partials/orders_stats.html` | routes/test_admin_orders.py::test_stats_over_all_orders | — | Implemented + Tested |
| FR-UI-122 | Search + status filter | M12 | same | table | routes/test_admin_orders.py::test_search_and_status_filter | — | Implemented + Tested |
| FR-UI-123 | Status change via select | M12 | `PUT /admin/orders/{id}/status` | `admin/partials/order_row.html` | routes/test_admin_orders.py::test_status_change_row_and_toast, ::test_invalid_transition_toast | D-30 | Implemented + Tested |
| FR-UI-124 | Modal refreshed with returned order | M12 | same | `admin/partials/order_modal.html` | routes/test_admin_orders.py::test_modal_updated_oob | — | Implemented + Tested |
| FR-UI-125 | Modal contents + timeline | M12 | `GET /admin/orders/{id}` | same | routes/test_admin_orders.py::test_modal_contents; unit/test_order_view.py::test_admin_timeline_labels | D-38 | Implemented + Tested |
| FR-UI-126 | Show server `message` | M3 | all HTMX | `partials/toast_oob.html` | routes/test_error_display.py::test_service_error_message_in_toast | D-20 | Implemented + Tested |
| FR-UI-127 | Failure semantics | M3 | all HTMX | — | routes/test_error_display.py::test_htmx_error_status_codes | D-20 | Implemented + Tested |
| FR-UI-128 | Image URL resolution | M3 | — | `image_url` filter | unit/test_core.py::test_image_url_resolution | K-29 | Implemented + Tested |

### 6.3 Cross-cutting checks (constraint 5) — also tracked

| Check | Test(s) |
|---|---|
| CSRF on every state-changing UI route | routes/test_csrf.py::test_all_unsafe_ui_routes_require_csrf (enumerates the router) |
| API origin check on writes | routes/test_csrf.py::test_api_write_requires_allowed_origin |
| Role checks on every admin route | routes/test_guards.py::test_all_admin_routes_require_admin (enumerates the router) |
| Rate limiting | routes/test_rate_limit.py::test_login_limited, ::test_register_limited |
| Security headers / CSP | routes/test_platform.py::test_security_headers |
| No secrets in code; startup fails without SECRET_KEY | unit/test_core.py::test_secret_key_required |

---

## 7. Build sequence

**Phase 2 — Foundation**
1. `pyproject.toml`, `.gitignore`, `.env.example`, settings, logging.
2. DB lifecycle (`AsyncMongoClient`, ping, exit-on-failure), `ensure_indexes`, document helpers, serialization.
3. App factory, middleware (request id, path normalisation, body limit, security headers, API CORS), error handlers, 404/403/500 templates.
4. Tailwind v4 standalone CLI (fetch + build scripts, `tailwind/input.css` with design tokens), local HTMX, `app.js` base (CSRF header, toasts, indicator), `base.html` / `site.html` / `admin.html`, header/footer shells.
5. Security: passwords, sessions, CSRF, rate limiter, guards, safe redirects.
6. Upload service + `/uploads` serving.
7. Test harness: per-test Mongo database on `TEST_MONGO_URI`, app with lifespan, `AsyncClient`, login helpers, factories. Foundation tests green.

**Phase 3 — Modules (each: models → service → routes → templates/partials → tests; traceability updated)**
1. M2 Auth (pages + API)
2. M3 Layout dynamics + About + Contact
3. M5 Categories
4. M6 Products
5. M7 Banners & promo cards
6. M8 Cart (service, API, page, add-to-cart endpoint)
7. M9 Storefront Home & Shop
8. M10 Checkout & order creation (WhatsApp flow + API create)
9. M11 My Orders & Order Details
10. M12 Admin Orders
11. M13 Admin Dashboard
12. M14 CLI

**Phase 4** design system pass across all templates (tokens, components, responsive 375/768/1280, a11y). **Phase 5** full unit + route test sweep and fixes. **Phase 6** page-by-page review in `docs/REVIEW.md`. **Phase 7** README, final traceability, open items.

---

## 8. Test strategy

- `pytest` + `pytest-asyncio` (auto mode) + `httpx.AsyncClient(ASGITransport)` + `asgi-lifespan` to run the real startup.
- Tests need a running MongoDB (`TEST_MONGO_URI`, default `mongodb://localhost:27017`). Each test session uses a fresh database `akrf_test_<random>`, collections are emptied between tests and the database is dropped at the end. Production data is never touched.
- Uploads go to a `tmp_path` `UPLOAD_DIR`. Image fixtures are tiny generated PNG/JPEG/WebP byte strings plus spoofed files (e.g. `text/html` named `.png`).
- Helpers: `login_as(client, role)` creates a user + session and sets the cookie; `csrf(client)` reads the token from a page; factories for categories, products, carts, orders, banners and promo cards.
- Each route test covers: success, validation error, unauthenticated, wrong role (where applicable), and CSRF missing.
- Router-enumeration tests make sure no unsafe UI route lacks CSRF and no `/admin` or admin `/api` route lacks the admin guard.

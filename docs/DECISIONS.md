# DECISIONS — AK Royal Flames (FastAPI + Jinja2 + HTMX rebuild)

Sources:
- **BE** = `FEATURES_AND_FR.md` (backend spec: FR-001…FR-122, BR-01…BR-37, KI-01…KI-31)
- **FE** = `FRONTEND_FEATURES_AND_FR.md` (frontend spec: FR-UI-001…FR-UI-128, K-01…K-33, §10.2–§10.4)

Both files are in the repository root, not in `docs/` as the brief said. They were left where they are.

Legend:
- **FIX**: a Known Issue. The correct behaviour is implemented, not the bug.
- **RESOLVED**: an ambiguity or mismatch. The safest reasonable behaviour was chosen, and the rule is explained.
- **⚠ REVIEW**: a decision that changes documented behaviour or adds something new. It is implemented as written here unless a reviewer says otherwise.
- **❓ OPEN**: needs a human decision. The default shown is what gets built until someone answers.

---

## 0. Questions that need a human decision (summary)

| ID | Question | Default that will be built |
|---|---|---|
| Q-01 | Should the JSON API under `/api/*` be kept alongside the server-rendered UI? (D-01) | **Yes.** It is kept for parity and coexistence: thin routers over the same services, with Known Issues fixed. |
| Q-02 | Order status transition rules (KI-07 vs FR-102). | Forward-only plus Cancel. Delivered and Cancelled are terminal (D-30). |
| Q-03 | Should placing an order decrement stock? (KI-06, FE §10.3) | **No decrement.** Stock is validated at checkout and at order creation only (D-31). |
| Q-04 | Upload policy: JPEG/PNG/WebP only, ≤ 5 MB, videos rejected (KI-09, FR-119/120). | As stated. Existing video files on disk are still served (D-12). |
| Q-05 | Existing logged-in users must log in again once after cut-over, because JWT cookies are replaced by server sessions (D-04). | Accepted. |
| Q-06 | Missing features listed in KI-23: profile editing, customer order cancel, banner/promo edit or toggle, password reset. | **Not built** (nothing invented). Can be added later. |
| Q-07 | Brand assets `/images/logo.png`, `candle1.jpg`, `candle2.jpg` and `favicon.svg` are not in this workspace. | An SVG wordmark and favicon will be designed, and About/Contact will use CSS/SVG artwork. Real files dropped into `app/static/img/` replace these with no code change (D-40). |
| Q-08 | Footer vs Contact business details conflict (K-26). | Contact-page values are used everywhere, set through `.env` (D-41). |
| Q-09 | Case-insensitive uniqueness for category names and product names (KI-31). | Enforced for **new** writes. Existing case-duplicates are left untouched (D-24). |
| Q-10 | Wishlist persistence (K-23). | Per-browser `localStorage`, with no server storage (D-43). |
| Q-11 | Pagination on the admin orders table (not in the spec). | 25 per page. Stats are still computed over all orders (D-16). |
| Q-12 | Display timezone for dates (spec used the browser's local time). | `Asia/Kolkata`, configurable (D-14). |
| Q-13 | **Action:** the old `.env` with real credentials was committed (KI-03). | Rotate the MongoDB password and the old JWT secret. This cannot be done from code. |
| Q-14 | Registration phone: validate as an Indian mobile when provided (K-30)? | Yes, `^[6-9]\d{9}$` when non-empty (D-27). |
| Q-15 | Database name: Mongoose uses the database in `MONGO_URI`, or **`test`** if none is given. | Same rule, with optional override `MONGO_DB_NAME` (D-08). Please confirm which database production uses. |

---

## 1. Architecture and cross-cutting decisions

| ID | Topic | Decision | Status |
|---|---|---|---|
| D-01 | Shape of the new app | One FastAPI app replaces **both** the React SPA and the Express API. The UI is server-rendered (Jinja2 + HTMX). Business logic lives in a service layer. A **JSON compatibility API** under `/api/*` reproduces the BE contracts (§6) as thin routers over the same services, with all Known Issues fixed. This keeps every BE FR implementable and testable, and lets the old SPA or other clients keep working during cut-over. | ⚠ REVIEW / ❓ Q-01 |
| D-02 | Health check (FR-002) | `/` is now the Home page (FR-UI-030), so the health check moves to **`GET /healthz`** → `200 {"msg":"api is working"}`. `GET /api` returns the same body for API clients. | ⚠ REVIEW |
| D-03 | Port (FR-001) | `PORT` defaults to `9000`, read by the `python -m app` launcher. In production Uvicorn runs behind a reverse proxy (README). | RESOLVED |
| D-04 | Auth mechanism (FR-026–FR-028, KI-02, KI-05) | **Server-side sessions** replace the stateless JWT. Login or register creates a random 256-bit token. Only its SHA-256 is stored, in the new collection `sessions` (with `user`, `createdAt`, `expiresAt` and a TTL index). Cookie: `akrf_session`, `HttpOnly`, `Secure` (setting `COOKIE_SECURE`, default `true`; `false` only for local http), `SameSite=Lax`, `Path=/`, `Max-Age=604800`, host-only. What users see stays the same: cookie-only auth, the `Authorization` header is ignored, the session has a fixed 7-day life with no sliding renewal (BR-05), and the role is re-read from `users` on every request (FR-032). Logout **deletes** the session, so it really ends (KI-05). The session id is rotated on login (no session fixation). No hard-coded secret exists; `SECRET_KEY` (≥ 32 chars) is required at startup (KI-02). Old `accessToken` JWT cookies are ignored, so users log in once again (Q-05). | ⚠ REVIEW |
| D-05 | Password hashing (FR-017, §5.2) | `bcrypt` library, cost **10**. New hashes use the **`$2a$`** prefix (`gensalt(rounds=10, prefix=b"2a")`), so they stay byte-compatible with the old Node service if both run against the same DB. Verification accepts `$2a$`, `$2b$` and `$2y$`. The password is truncated to 72 bytes when verifying, matching the bcryptjs behaviour that produced the existing hashes. New passwords must be 6–72 UTF-8 bytes (`"Password must be at least 6 characters"` / `"Password must be at most 72 characters"`). Hashing runs in a worker thread. | RESOLVED |
| D-06 | CSRF (constraint 5, FE §10.4.4) | **HTML/HTMX:** a signed double-submit token. An HttpOnly cookie `akrf_csrf` holds a random value. Pages render an HMAC-bound token in `<meta name="csrf-token">` and in hidden `csrf_token` fields. HTMX sends it as the `X-CSRF-Token` header (set globally in `app.js`). Every POST/PUT/PATCH/DELETE outside `/api` must carry it, otherwise the response is 403 ("Your session has expired. Please refresh the page and try again."). **`/api/*`:** the old SPA sends no token (FE §10.4.4), so state-changing API calls need an `Origin` (or `Referer`) in the allow-list (`APP_BASE_URL` + `CORS_ORIGINS`) together with the `SameSite=Lax` cookie. A missing or foreign origin gets 403 JSON. | RESOLVED |
| D-07 | Rate limiting (constraint 5) | Fixed-window counters in the new collection `rate_limits` (TTL index), so limits hold across several Uvicorn workers. Login: 5 failed attempts per email+IP per 15 min, and 30 attempts per IP per 15 min. Register: 10 per IP per hour. Exceeding a limit returns 429 `"Too many attempts. Please try again in N minutes."` (inline error / JSON). The client IP comes from the proxy headers trusted by Uvicorn (`--forwarded-allow-ips`). There are no OTP endpoints. | RESOLVED |
| D-08 | Database selection | `MONGO_URI` is required. Database = `MONGO_DB_NAME` if set (an explicit override, used by the test suite so it can never touch real data), else the path component of the URI, else `test`, which is Mongoose's default, so existing data is found. The local development database found on this machine is `ak_royal_flames`. Startup awaits `ping`. On failure it logs `MongoDB connection failed: <msg>` and exits with code 1 (FR-008). Success logs `MongoDB connected successfully`. | ⚠ REVIEW (Q-15) |
| D-09 | Existing collections and fields | The 7 collections keep their exact names and fields (`users`, `categories`, `products`, `carts`, `orders`, `banners`, `promocards`). No field is renamed, added or removed. Unknown fields are never written. `createdAt`/`updatedAt` are BSON dates (UTC). `__v` is written as `0` on insert and incremented (`$inc`) whenever an array field changes (cart `items`), matching Mongoose. Only two **new** collections are added: `sessions` and `rate_limits` (D-04, D-07). | RESOLVED |
| D-10 | Numeric types | Matches the Node BSON serializer: integral values are stored as int (int32/int64), others as double. `price`, `oldPrice`, `stock`, `quantity`, `total`, `itemsTotal`, `shipping`, `grandTotal` and `order` follow this rule. Reads accept int or double. | RESOLVED |
| D-11 | Serialization (FR-011) | JSON: ObjectId → 24-char lowercase hex; dates → ISO-8601 UTC with milliseconds and `Z`. `__v`, `createdAt` and `updatedAt` are included wherever the BE spec shows them. | RESOLVED |
| D-12 | Uploads (FR-118–FR-122, KI-08, KI-09, FE §10.4.5, M-02) | One file, field **`image`**, on the six upload points (admin UI + API). Accepted: **JPEG, PNG, WebP**, detected from the file's **magic bytes** (the client MIME type is not trusted). Max **5 MB** (`MAX_UPLOAD_MB`). Videos and GIF are rejected (the UI only renders images; FE accepts WebP, BE rejected it). Stored name: `<epochMillis>-<random 0–1 000 000 000>.<ext>`, where the extension comes from the detected type (`.jpg`/`.png`/`.webp`), never from client input. Stored DB value: `/uploads/<name>` (relative, FR-122). The folder (`UPLOAD_DIR`, default `uploads`) is created at startup. Validation runs **before** anything is written to disk, and a write is rolled back if the DB operation fails, so there are no orphans (KI-08). Errors return 400 (bad type/field) or 413 (too large) with a readable message, never 500 HTML (KI-10). | ⚠ REVIEW (Q-04) |
| D-13 | Serving `/uploads` (FR-006) | `GET /uploads/{filename}`: a single path segment only. Dotfiles, `..` and separators are rejected (404). Every existing file (any extension, including legacy videos) is still served. Headers: `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none'; img-src 'self'; media-src 'self'; sandbox`, `Cache-Control: public, max-age=0` with ETag/Last-Modified (as before). A missing file returns 404. | RESOLVED |
| D-14 | Dates in the UI (FR-UI-093) | Stored in UTC. Shown in `DISPLAY_TIMEZONE` (default `Asia/Kolkata`) using `en-IN` style: `05 Oct 2026` and `05 Oct 2026, 09:15 am`. Missing or invalid dates show `-`. | ⚠ REVIEW (Q-12) |
| D-15 | Money format (FR-UI-041) | `₹` + Indian digit grouping (`1,23,456.5`), at most 2 decimals, trailing zeros dropped. Python implementation, unit-tested. | RESOLVED |
| D-16 | Pagination (BR-37) | Storefront and `/api/*` lists stay unpaginated, as specified. **Admin Orders** table: 25 per page (`ADMIN_ORDERS_PAGE_SIZE`), and the search, status filter and stat cards work over the full set. Categories and products: no pagination (small catalogue) but server-side search. | ⚠ REVIEW (Q-11) |
| D-17 | Route matching (FR-012) | A middleware strips a trailing `/` (except on `/` itself) and lower-cases the path's static segments for routing, for all routes except `/uploads/*` and `/static/*` (filenames are case-sensitive). ObjectId parsing is case-insensitive. | RESOLVED |
| D-18 | Body limits (FR-005, BR-36) | JSON / urlencoded bodies are capped at 10 MB (`MAX_BODY_MB`), giving **413** (JSON on `/api`, the HTML error page otherwise). Multipart bodies are capped at `MAX_UPLOAD_MB + 1 MB`. Malformed JSON gives 400 JSON `"Invalid JSON body"`. | RESOLVED |
| D-19 | CORS (FR-003, FR-004, KI-30) | CORS applies only to `/api/*`. The allow-list is `CORS_ORIGINS` (comma-separated, exact origins). A matching `Origin` is echoed with `Access-Control-Allow-Credentials: true` and `Vary: Origin`. A non-matching origin gets no CORS headers. Never `*` with credentials. Preflight: 204, methods `GET,HEAD,PUT,PATCH,POST,DELETE`, requested headers echoed. The SSR UI is same-origin and needs no CORS. | FIX |
| D-20 | Error responses (KI-10, KI-11, FE §10.4.8) | `/api/*` always returns JSON (`{"success":false,"message":...}` plus `"error":true` on category/product endpoints, as in their envelope). Pages return the branded templates `errors/404.html`, `403.html`, `500.html` (and an inline 429 message). HTMX requests get a toast through `HX-Trigger` instead of a page swap. 500 messages are generic (`"Something went wrong. Please try again."`); raw exception text, stack traces and DB errors are **never** sent, only logged with a request id. | FIX |
| D-21 | API envelopes (KI-17) | The exact keys of each BE endpoint are kept, so existing clients still parse them. Category and product list responses **also** get `"success": true` (the FE spec expects it, and it is additive). | FIX |
| D-22 | Logging (§11.3, K-33) | stdlib `logging`, one line per event, with a request id (`X-Request-ID` echoed). Startup, DB connect, guard failures and handler errors are logged with labels similar to BE §11.3. Passwords, cookies, tokens and full request payloads are never logged. Customer PII is not logged at INFO level. | RESOLVED |
| D-55 | Undocumented legacy index | The real `orders` collection also has `orderReference_1` (unique, **sparse**), which is not in BE §4.8 and is not used by any document. Being sparse, it does not affect new orders. Startup never drops or changes indexes it does not own, so it is left untouched. | RESOLVED |
| D-56 | Where Pydantic v2 is used | Request input (forms and API bodies) is validated by small explicit validators (`app/core/validators.py` and the services), because both specs pin exact user-facing messages and validation order, which a generic Pydantic error would not reproduce. Pydantic v2 defines the **stored-document schemas** (`app/models.py`: users, categories, products, carts, orders, banners, promocards) and every new document is validated against them before insert, so a wrong type or enum value can never reach the shared database. Settings also use pydantic-settings. | RESOLVED |
| D-57 | Contact form fallback link | After a valid contact submission the form is cleared (FR-UI-094) and a small "If WhatsApp didn't open, tap here" link is shown, because some mobile browsers block the automatic new tab. The spec had no success message; this one is a fallback and adds no new data flow. | ⚠ REVIEW (minor) |
| D-23 | Admin bootstrap (BR-04) | No web endpoint creates admins (unchanged). An **offline CLI** is added for operators: `python -m app.cli promote-admin <email>` / `demote-admin <email>`. | ⚠ REVIEW (addition) |

---

## 2. Catalogue, cart, order and merchandising rules

| ID | Topic | Decision | Status |
|---|---|---|---|
| D-24 | Name uniqueness (BR-06, BR-08, KI-31) | Category names: unique after trimming, compared **case-insensitively** for new creates and renames (the DB index stays as it is). Product names: unique within a category, case-insensitive, checked on **create and update**, excluding the product itself (KI-16). A duplicate-key race gives 409, not 500 (KI-29). | ⚠ REVIEW (Q-09) |
| D-25 | Old price (BR-10, KI-16, M-24) | `oldPrice`, if set, must be ≥ 1 **and ≥ price**, on create and on update (FE §5.12 already enforces this on both). On update the check runs only when the request changes `price` or `oldPrice`, so legacy documents that break the rule do not block unrelated edits such as a stock change (the second half of KI-16). An empty string means "no old price": omitted on create, `$unset` on update (FR-060, K-18). Messages: API/BE `"Old price cannot be less than price"`; admin form `"Old price must be greater than or equal to selling price"`. | FIX |
| D-26 | Numeric validation (KI-12, KI-13) | `price`: finite and ≥ 1 (decimals allowed). `stock`: integer ≥ 0. Cart and order `quantity`: **integer ≥ 1** and ≤ stock. Non-numeric, NaN, booleans and non-string text fields return 400 with the documented messages, never 500. | FIX |
| D-27 | Text and format validation (KI-14, KI-15, FE §10.4.6–7) | Text is trimmed, then checked as required (whitespace-only → the "required" message, never 500). Email: basic syntax `local@domain.tld`, ≤ 254 chars (login does no format check, so legacy accounts can still sign in). Phone (register, optional): `^[6-9]\d{9}$` when non-empty (K-30, Q-14). Order `customer.mobile` `^[6-9]\d{9}$` and `customer.pincode` `^\d{6}$` are now enforced on the server too. `buttonLink`: either an in-site path starting with a single `/` (not `//`, no backslashes) or an absolute `http://`/`https://` URL; anything else (`javascript:`, `data:` …) → 400 `"Button link must start with / or http(s)://"`. `background`: `#rgb` or `#rrggbb`. Text lengths are capped (name/title 120, description 2000, message 500). Legacy DB values that break these rules are made safe when rendered: links fall back to `/shop`, colours to `#08aaa6`. | FIX |
| D-28 | Cart consistency (KI-19, KI-20, KI-29, M-01) | One cart per user via an atomic upsert (`find_one_and_update`, `upsert=True`), with a retry on duplicate-key (KI-29). A missing cart is treated as an **empty cart** everywhere: update and toggle return 404 `"Product not found in cart"`, remove and clear return 200 with the (empty) populated cart. Clear always returns a populated cart. Toggle parses `true/false`, `"true"/"false"`, `"on"/"off"` and `1/0`; a missing value selects (FR-077 default). **Select-all** is added (`PUT /api/cart/select-all` from FE §6.2.6, plus the UI). Lines whose product no longer exists are hidden (FR-UI-058) and pruned when the cart is loaded. | FIX |
| D-29 | Server-priced orders (KI-06, FE §10.4.2, M-09) | Order lines are built **on the server**. In the UI they come from the user's *selected* cart lines. In the API, `items[].product`/`productId` + `quantity` are read and everything else the client sends is ignored. For each line the product must exist; `name`, `image` and `price` are snapshotted from the DB product; `total = price × quantity`. `itemsTotal = Σ total`; `shipping = 0`; `shippingStatus = "FREE"` if `itemsTotal ≥ FREE_DELIVERY_THRESHOLD` (1099), else `"PAYABLE_SEPARATELY"`; `grandTotal = itemsTotal`; `paymentMethod = "WhatsApp Order"`. Client totals and `shippingStatus` are ignored (this replaces FR-089/FR-090 "as supplied"). Each line's quantity must be ≤ current stock, otherwise 400 `"Only N items available for <name>"`. | FIX |
| D-30 | Order status lifecycle (KI-07, BR-28, FR-102, K-17) | Allowed moves: **Pending → Confirmed / Processing / Shipped / Delivered / Cancelled**; **Confirmed → Processing / Shipped / Delivered / Cancelled**; **Processing → Shipped / Delivered / Cancelled**; **Shipped → Delivered / Cancelled**. **Delivered** and **Cancelled** are terminal. Forward skips are allowed (skipped steps keep `null` dates and show as "—"). Setting the current status again returns 400 `"Order is already <status>"`. Any other move returns 400 `"Cannot change order status from <A> to <B>"`. Since no status is entered twice, timestamps are never overwritten. `statusDates[new] = now`. Cancel sets `expectedDelivery = null` (FR-100). FR-101 is kept for legacy orders whose `expectedDelivery` is null. The admin UI only lists allowed next statuses, asks for confirmation before **Cancelled** and **Delivered**, and disables only the row being updated. Trade-off: a mistaken "Delivered" or "Cancelled" cannot be undone in the UI. | ⚠ REVIEW (Q-02) |
| D-31 | Stock on order (BR-27, FE §10.3) | Stock is **checked** at checkout and at order creation (D-29) and is **not decremented** or reserved. This is the same as today. The business confirms each order manually on WhatsApp, and decrementing would also need rules for cancel and restock that neither spec defines. | ❓ OPEN (Q-03) |
| D-32 | Cart cleanup after an order (BR-26, KI-21, K-11, FR-091) | The server removes only the cart lines that were ordered. UI checkout orders the full quantity of each selected line, so those lines are removed. API orders reduce a matching line by the ordered quantity and remove it at ≤ 0. Unselected lines stay. The client-side removal loop (FE §5.6) is no longer needed. | FIX |
| D-33 | Expected delivery (BR-25, KI-26, FE §10.3) | `expectedDelivery = createdAt + 72 h`, using UTC arithmetic, so there is no daylight-saving drift. | FIX |
| D-34 | Order id (BR-23, K-09, FE §10.3) | Format kept: `AKRF-<epochMillis>-<1000–9999>`. It is generated **at checkout**, when the pending order is created, and the same id is used in the WhatsApp message (first send **and** "Send WhatsApp Again") and stored on the order. The unique index protects it; on a collision the order is retried with a new id and the message would show a stale id, which is extremely unlikely and logged. | FIX |
| D-35 | Product delete side-effects (KI-22) | Deleting a product also `$pull`s its lines from every cart. Order snapshots are kept. The product's image file is deleted **only if no order item still refers to that image path**, so order history keeps its pictures. The same rule applies when an image is replaced. | FIX |
| D-36 | Banner / promo delete order (KI-27) | The document is deleted first, then the file (best effort; failures are logged). A file-system error can no longer leave a broken record. | FIX |
| D-37 | Banner / promo `status` (FR-104/106, M-17) | The admin create form gets an **"Active (show on storefront)"** checkbox, checked by default, matching the BE `status` field. The admin list shows an Active/Inactive badge. Parsing: `true`, `"true"`, `"on"` or `"1"` → true; when the field is omitted the default is true; any other supplied value → false (BR-34). There is still no edit or toggle endpoint (BR-35, Q-06). | ⚠ REVIEW |
| D-38 | Admin read of single orders | The admin order modal loads `GET /admin/orders/{id}` (admin-only), so the modal no longer depends on the cached list. API: unchanged (no single-order admin endpoint). | RESOLVED |

---

## 3. UI flow decisions

| ID | Topic | Decision | Status |
|---|---|---|---|
| D-39 | WhatsApp checkout redesign (FR-UI-073–083, K-06, K-07, K-08, K-10) | 1. The Cart's "Place Order on WhatsApp" sends the delivery form by HTMX POST to `/cart/checkout`, and the button is disabled with "Processing…" while it runs (K-06). 2. The server validates the form and the selected lines (D-29), then stores the **pending order in the user's server session**, not in `localStorage`, which fixes K-08: it is scoped to the user and cleared on logout. 3. The response's `HX-Trigger: openWhatsApp` opens the `wa.me` link in a new tab; the request comes from the click, so popup blockers allow it. `HX-Redirect` then moves the current tab to `/whatsapp-confirm`. 4. The confirm page always offers an "Open WhatsApp" button, in case the popup was blocked or WhatsApp opened in the same tab on mobile (K-10). 5. There is **no** `visibilitychange` auto-redirect, so the K-07 loop cannot happen. "I Haven't Sent It" returns to `/cart`, which shows a "You have a pending WhatsApp order: Continue / Discard" banner. This meets FR-UI-076's intent (getting the user to the confirm page) more reliably than the original mechanism. | ⚠ REVIEW |
| D-40 | Brand assets (FE §2.4) | The logo, candle photos and favicon are not available (Q-07). Built: an SVG flame wordmark "AK Royal Flames" (`static/img/logo.svg`), an SVG favicon, and decorative SVG/CSS artwork where the About and Contact pages showed photos. File names are centralised in one template macro, so real assets can replace them. | ❓ OPEN (Q-07) |
| D-41 | Business details (K-26) | One source in settings: `BUSINESS_PHONE` (+91 92882 45292), `BUSINESS_EMAIL` (akroyalflames@gmail.com), `BUSINESS_ADDRESS` (Delhi, India), `BUSINESS_HOURS` (Monday - Sunday: 9:00 AM - 9:00 PM), `WHATSAPP_NUMBER` (919288245292), `INSTAGRAM_URL` (https://www.instagram.com/akroyalflames/), `FACEBOOK_URL` (https://www.facebook.com/). The footer and Contact page both use them. The newsletter form that was commented out stays out. | ⚠ REVIEW (Q-08) |
| D-42 | Contact map (K-27) | Optional `MAP_EMBED_URL` (must be `https://www.google.com/maps/embed?...`). When it is set, an iframe is shown. When it is not set, the map block is left out entirely instead of showing placeholder text. | ⚠ REVIEW |
| D-43 | Wishlist (FR-UI-056, K-23) | Client-side only: a heart toggle stored in `localStorage["akrf_wishlist"]` (product ids). There is no server storage or API, so nothing new is added to the DB. | ⚠ REVIEW (Q-10) |
| D-44 | Login redirects (FR-UI-015, K-12) | A `redirect` parameter is honoured only when it is a safe in-site path (starts with a single `/`, no scheme/host, no `\`), otherwise it is ignored (open-redirect protection). Order: safe `redirect` (admins included; a non-admin with an `/admin…` redirect goes to `/`) → admin → `/admin` → `/`. Admin guard redirects go to `/login?redirect=<requested path>`. | FIX |
| D-45 | Session-state UI (FR-UI-010, FR-UI-024, K-32) | The session is checked on **every** request on the server, so a UI "loading session" state cannot occur ("Checking admin access..." from FR-UI-024 is never needed: the guard runs before rendering). An expired session sends HTML requests to `/login?redirect=…`; HTMX requests get `HX-Redirect` to the same place. | RESOLVED |
| D-46 | Home & Dashboard sections (K-15, K-16, FR-UI-038, FR-UI-098) | Each section (banners, promo cards, categories, products; dashboard stats, status counts, recent orders) loads on its own as an HTMX partial (`hx-trigger="load"`) with skeleton placeholders. One failing section shows its own error box and a **Retry** button, and the others are unaffected. | FIX |
| D-47 | Cart actions (FR-UI-063/064, K-04) | −/+/Remove/select go through HTMX with `hx-sync="closest form:queue last"` and disabled controls while in flight. Server errors (such as an over-stock quantity) show as a toast, and the cart re-renders from the server's state. | FIX |
| D-48 | Shop state in URL (FR-UI-049, K-22) | Search, category and sort are query parameters. Each change re-renders the results through HTMX with `hx-push-url`, so the URL always matches what is on screen and can be shared. Filtering and sorting happen on the server, with the same rules as FR-UI-046/050/051. `/shop?search=` (empty) normalises to `/shop` (FR-UI-006). | FIX |
| D-49 | My Orders error state (K-14) | A failed load shows an error box with Retry, not "No Orders Yet". | FIX |
| D-50 | Order detail access (K-13, FR-094) | `/my-orders/{id}`: an anonymous visitor is sent to `/login?redirect=…`. An invalid id, someone else's order or a missing order all render the same message: redirect to `/my-orders` with the toast "Order not found" (FR-UI-089), so ownership is not revealed. | FIX |
| D-51 | 404 page (K-24, FR-007) | A branded 404 page with header and footer for unknown HTML routes. JSON 404 `{"success":false,"message":"Not found"}` for unknown `/api/*` routes. | FIX |
| D-52 | Admin non-admin access (FR-UI-026, constraint 5) | Full-page `/admin/*` GET as a non-admin → redirect to `/` with the toast "Admin access required" (FR-UI-026). Every admin HTMX/state-changing route → **403** (toast); every admin API route → 403 JSON `"Admin access required"`. The role is always checked on the server. | RESOLVED |
| D-53 | Guest add-to-cart (FR-UI-040, FR-UI-054) | The two pages keep their documented behaviours. Home: toast "Please login first to add products to cart", then redirect to `/login` after 1 s (the redirect carries `?redirect=/`). Shop: status banner + toast "Please login first to add products to cart." with no redirect. | RESOLVED |
| D-54 | YouTube embed & CSP | Content-Security-Policy on pages: `default-src 'self'; img-src 'self' data:; frame-src https://www.youtube.com https://www.google.com; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`. All JS lives in static files (no inline scripts). `'unsafe-inline'` for styles is only needed for the per-card background colours, which are validated (D-27). | RESOLVED |

---

## 4. Backend ↔ frontend cross-check (mismatches found)

| ID | Mismatch | Resolution |
|---|---|---|
| M-01 | FE calls `PUT /api/cart/select-all`. BE has no such endpoint. | Added (D-28). |
| M-02 | FE allows WebP; BE rejects it with a 500 HTML page. Sizes: FE 5 MB vs BE 100 MB. Banner/promo FE `image/*` with no limit. | Unified policy (D-12). |
| M-03 | FE needs JSON for every response. BE returns HTML for upload errors, 404, 413 and bad JSON. | JSON on `/api/*` (D-20). |
| M-04 | FE treats catalogue and merchandising writes and `get-all-*` as admin-only. BE has no auth (KI-01). | Admin enforced (KI-01). |
| M-05 | FE needs cross-origin cookies. BE cookie is `Secure=false; SameSite=Lax` and CORS is a single origin. | SSR is same-origin. API CORS allow-list (D-19); Secure cookie (D-04). |
| M-06 | FE `BASE_URL` port 5000 vs BE default 9000. | Not relevant to SSR (same origin). `PORT` default 9000 kept (D-03). |
| M-07 | FE expects `success:true` on category/product lists; BE Style C omits it. | Added (D-21). |
| M-08 | FE prefers a populated `category {_id,name}`; BE returns an id string. | API keeps the id string (BE contract; FE handles both). SSR resolves names on the server. |
| M-09 | FE expects the backend to re-validate prices; BE trusts the client. | Server pricing (D-29). |
| M-10 | BE `GET /` is the health check; FE `/` is Home. | D-02. |
| M-11 | FE order reference `AKRF-YYYYMMDD-NNNN` (client-only) vs BE `AKRF-<ms>-<rand>`. | D-34. |
| M-12 | FE checkout mobile regex vs no phone validation at registration. | D-27 / Q-14. |
| M-13 | FE autofills `address/city/pincode` from the user, but BE never writes them. | Autofill uses them when present. No profile editing (Q-06). |
| M-14 | BE supports line selection (`toggle`) but FE has no UI, while totals count only selected lines (K-05). | A selection checkbox per line plus "Select all" is added to the Cart page (D-28). New lines default to selected. |
| M-15 | FE register response example has `_id`; BE register returns `id` and omits the address fields (KI-18). | API auth responses return `id` **and** `_id` plus the full profile (`name,email,phone,address,city,pincode,role`). |
| M-16 | FE leaves the `expectedDelivery` rule undefined; BE uses +3 days. | BE rule, UTC (D-33). |
| M-17 | Banner `status` exists in BE but not in the FE form. | Active checkbox (D-37). |
| M-18 | Stock on order: undefined in FE, not decremented in BE. | D-31 / Q-03. |
| M-19 | FE reads `items[]._id` on order details (React key); BE order items have no `_id`. | Not relevant to SSR (index used). No field added. |
| M-20 | FE status-update toast example "Order status updated" vs BE "Order status changed to <status>". | BE message used (FR-103). |
| M-21 | FE client-side "Old price must be ≥ selling price" on create; BE has no check on create. | Enforced on both (D-25). |
| M-22 | FE pending order items use `_id`, the API payload uses `productId`, BE accepts `product` or `productId`. | API accepts `product` or `productId` (FR-084). The UI builds lines on the server. |
| M-23 | FE "Admin" pages expected; BE has no way to create admins. | CLI (D-23). |
| M-24 | BE upload errors are 500; FE shows the message verbatim. | 400/413 with readable messages (D-12). |
| M-25 | FE Login sends admins to `/admin` and ignores `?redirect`; the guard's `state.from` is lost. | D-44. |
| M-26 | FE expects orders newest-first without sorting them; BE sorts `my-orders` and `all` descending. | Kept (server sort `createdAt` desc). |

---

## 5. Backend Known Issues (BE §13): resolution

| KI | Resolution | Ref |
|---|---|---|
| KI-01 | Admin guard on every category/product/banner/promo write and on `get-all-*`, in the API and the UI. | D-52 |
| KI-02 | No fallback secret. `SECRET_KEY` is required (≥ 32 chars), and startup fails fast without it. JWT not used. | D-04 |
| KI-03 | `.env` is git-ignored; `.env.example` lists names only. **Rotate leaked credentials** (Q-13). | — |
| KI-04 | `Secure` cookie, same-origin UI. | D-04 |
| KI-05 | Server-side sessions; logout deletes the session. | D-04 |
| KI-06 | Server-side pricing, product existence and stock check. | D-29, D-31 |
| KI-07 | Transition rules. | D-30 |
| KI-08 | Validate before writing; roll back files on failure. | D-12 |
| KI-09 | Magic-byte detection; JPEG/PNG/WebP only. | D-12 |
| KI-10 | JSON errors on the API; 4xx statuses; no stack traces. | D-20 |
| KI-11 | Invalid ObjectId → 400 (API) / 404 page (UI); generic 500 messages. | D-20 |
| KI-12 | Integer quantities ≥ 1; NaN → 400. | D-26 |
| KI-13 | Strict types → 400. | D-26, D-27 |
| KI-14 | Trim, then required → 400. | D-27 |
| KI-15 | Format validation for email, phone, mobile, pincode, link and colour. | D-27 |
| KI-16 | `oldPrice ≥ price` and duplicate-name check on create and update. | D-24, D-25 |
| KI-17 | `success` added; keys kept. | D-21 |
| KI-18 | Full profile in the register response. | M-15 |
| KI-19 | A missing cart is an empty cart; clear is always populated. | D-28 |
| KI-20 | Proper boolean parsing on toggle. | D-28 |
| KI-21 | Only ordered lines and quantities are removed. | D-32 |
| KI-22 | Carts are cleaned on product delete; images kept while referenced by orders. | D-35 |
| KI-23 | Not invented (Q-06). | — |
| KI-24 | No unused config or dependencies. `GOOGLE_MAPS_API_KEY` is not read (optional `MAP_EMBED_URL` instead, D-42). | — |
| KI-25 | Not relevant (simple `find`). | — |
| KI-26 | UTC + 72 h. | D-33 |
| KI-27 | DB ping awaited before serving; doc deleted first, then file. | D-08, D-36 |
| KI-28 | Production Uvicorn command (no file-watcher); upload dir auto-created; README notes a persistent volume for `uploads/`. | D-12 |
| KI-29 | Atomic upserts, duplicate-key → 409, orderId retry. | D-24, D-28, D-34 |
| KI-30 | CORS allow-list, never `*` with credentials. | D-19 |
| KI-31 | Case-insensitive uniqueness for new writes. | D-24 |

---

## 6. Frontend Known Issues (FE §10.1): resolution

| K | Resolution | Ref |
|---|---|---|
| K-01 | Not relevant: SSR is same-origin; the base URL comes from `.env` (`APP_BASE_URL`, used for CSRF/CORS checks only). | — |
| K-02 | Home add-to-cart shows the real server result (HTMX swap of the card + toast). | D-47 |
| K-03 | One shared product-card partial; no dead component. | — |
| K-04 | Cart actions disable controls, queue requests and show errors. | D-47 |
| K-05 | Selection UI added. | M-14 |
| K-06 | Place-order button disabled while processing. | D-39 |
| K-07 | No visibility-based redirect loop; pending-order banner on the cart. | D-39 |
| K-08 | Pending order stored in the user's server session. | D-39 |
| K-09 | Same order id in the message, the resend and the DB. | D-34 |
| K-10 | User is sent straight to the confirm page, with a fallback "Open WhatsApp" button. | D-39 |
| K-11 | Server removes ordered lines; no client loop. | D-32 |
| K-12 | Safe `redirect` honoured for everyone. | D-44 |
| K-13 | Server-side guard and ownership check. | D-50 |
| K-14 | Distinct error state. | D-49 |
| K-15 | Independent sections. | D-46 |
| K-16 | Independent dashboard sections. | D-46 |
| K-17 | Transition rules, confirmation, per-row disabling. | D-30 |
| K-18 | `""` old price means none/clear. | D-25 |
| K-19 | Old price shown only when set and greater than the price (cards), or when set (admin table, never `₹0`/`₹`). | D-25 |
| K-20 | Server-side upload validation. Edit still not provided (BR-35, Q-06). | D-12 |
| K-21 | Not relevant: the form is re-rendered by the server after upload. | — |
| K-22 | URL kept in sync. | D-48 |
| K-23 | `localStorage` wishlist. | D-43 |
| K-24 | Branded 404. | D-51 |
| K-25 | Not relevant (no SPA). | — |
| K-26 | One source for business details. | D-41 |
| K-27 | Optional map embed. | D-42 |
| K-28 | Not relevant. | — |
| K-29 | One `image_url` filter for every image (absolute, `data:` or root-relative paths; anything else is shown as a placeholder icon). | — |
| K-30 | Phone validated at registration. | D-27 |
| K-31 | Server sort newest-first. | M-26 |
| K-32 | Session checked per request. | D-45 |
| K-33 | No PII in logs; no client-side console logging. | D-22 |

FE §10.4 security items: (1) admin authorization → D-52; (2) never trust client prices → D-29; (3) order ownership → D-50; (4) CORS and CSRF → D-06, D-19; (5) uploads → D-12, D-13; (6) `buttonLink` schemes → D-27; (7) registration validation → D-05, D-27; (8) no internal details in messages → D-20.

FE §10.3 ambiguities: expected delivery → D-33; orderId → D-34; stock → D-31; cart add is **additive** (BE §6.5.2, FR-072); category delete with products → blocked with 409 (BR-07); banner order → server sort by `order` then newest (BR-32); public vs admin lists → `status` flag (BR-32); `/me` when logged out → 401 JSON.

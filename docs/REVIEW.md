# REVIEW — page-by-page review (Phase 6)

## Evidence used for every entry

- **Automated route tests:** `pytest`, 444 passing. Every page and partial has success, validation, unauthenticated and wrong-role tests where those apply. Router-walking tests prove that every state-changing UI route rejects requests without CSRF, every `/api` write rejects foreign origins, and every admin route returns 403 for customers (`tests/routes/test_guards.py`).
- **Browser review:** `python scripts/ui_review.py <out>` seeds a demo database (`akrf_demo_review`, never real data) and loads every page as guest, customer and admin at **375 / 768 / 1280 px**. Final run: **60 captures, 0 issues.** That means no console errors, no failed requests (images and partials included), no horizontal overflow, every form control labelled and every image with `alt`. It also runs end-to-end flows in Chromium: shop add-to-cart, live search (URL stays in sync), cart +/− and selection, the WhatsApp popup, order confirmation, and an admin status change with confirmation.
- **Visual check** of the captured screenshots: brand palette, type scale, spacing, cards, tables, badges, modal and empty states.

Checklist keys: **FR** requirement IDs · **AC** access control · **ACT** actions and edge cases · **VAL** validation messages · **STATE** empty / loading / error states · **RESP** 375/768/1280 · **A11Y** basics · **CLEAN** no console errors, broken links/images or unhandled exceptions.
✅ = verified · n/a = not applicable.

## Problems found during review and fixed

| # | Page | Problem | Fix | Verified by |
|---|---|---|---|---|
| R-1 | All site pages (logged in, 768 px) | Header overflowed by 79 px (nav + search + cart + name chip + dashboard + logout). | For logged-in users between 768 and 1023 px, the logo shows only the flame mark. The name chip stays (FR-UI-007). | UI review: 0 overflow at 768 px |
| R-2 | Admin → Orders | Status `<select>` inherited `hx-include="#order-filters"` from the panel, so the filter's empty `status` was also sent and the change failed with "Invalid order status". | `hx-disinherit="hx-include"` on the panel. The server also takes the first `status` value. | Browser flow ("Order status changed to Confirmed"); `test_status_uses_first_value_when_duplicated`, `test_orders_panel_does_not_leak_filters` |
| R-3 | Admin → Orders, Cart | `hx-disabled-elt="this"` on value-carrying inputs (status select, checkboxes) could drop their own value from the request. | Inputs get a CSS busy state instead (`[&.htmx-request]` / `:has(.htmx-request)`). Only buttons are disabled. | Browser flows |
| R-4 | Shop | Pushed URLs carried empty parameters (`?category=&sort=default`). | The server sends a canonical `HX-Push-Url` (`/shop?search=lavender`). | Browser flow "search url" |
| R-5 | Order Details | Products card stretched to the height of the side column (empty space). | `self-start`. | Screenshot |
| R-6 | Admin → Orders (1280 px) | Order IDs wrapped over 3 lines; columns pushed off-screen. | Monospace, non-wrapping order id; product names truncated with a tooltip. The table still scrolls horizontally inside its card on narrow screens. | Screenshot |
| R-7 | Test harness | Rare MongoDB server-selection timeout while creating per-test databases under load. | Test settings use a 20 s server-selection timeout. | Full suite run |

---

## Website pages

### Home `/` + partials `/_p/home/banners`, `/_p/home/promo-cards`, `/_p/home/categories`, `/_p/home/products` — ✅ PASSED
- **FR:** FR-UI-030–FR-UI-044, FR-108, FR-115, D-46.
- **AC:** public. Add-to-cart follows the guest rule (toast, then `/login` after 1 s). ✅
- **ACT:** slider (4 s auto-advance, arrows/dots, pauses on hover/focus, no arrows for one banner); CTA only when a title exists; unsafe `buttonLink` falls back to `/shop`; promo cards on their colour; category tiles link to `/shop?category=`; latest 8 by `createdAt`; mid-page banner as an out-of-band swap. ✅
- **VAL:** add-to-cart quantity limited to 1..stock on the client and re-checked on the server. ✅
- **STATE:** skeletons while loading; each section has its own error box + Retry + toast (one failure doesn't blank the others); empty messages "No banners available", "No categories available yet.", "No products available yet.". ✅
- **RESP / A11Y / CLEAN:** ✅ (carousel roles, slide labels, focusable controls only on the visible slide, `alt` on every image, decorative SVGs `aria-hidden`).

### Shop `/shop` + partial `/shop` (HX-Target `shop-results`) — ✅ PASSED
- **FR:** FR-UI-006, FR-UI-042–FR-UI-056, D-48.
- **AC:** public. ✅
- **ACT:** category / search / sort run on the server and stay in the URL (`hx-push-url` + canonical `HX-Push-Url`); `?search=` (empty) redirects to `/shop`; mobile category drawer closes on selection; wishlist heart persisted per browser. ✅
- **STATE:** "No Candles Found" + View All; category / product error boxes with Retry; status banner (dismissible). ✅
- **RESP / A11Y / CLEAN:** ✅ (drawer reached by a labelled button; `aria-current` on the active category; results region `aria-live`).

### Product card + `POST /cart/add` — ✅ PASSED
- **FR:** FR-UI-040–FR-UI-044, FR-UI-054, FR-UI-055, FR-UI-059, FR-UI-060, FR-068–FR-072.
- **ACT:** "Add to Cart" → "Adding..." → "Add More"; quantity resets to 1; header badge updated out-of-band; out-of-stock refused without changing the cart; over-stock shows "Only N items available". ✅
- **AC:** guest (Home) toast + redirect; guest (Shop) banner + toast; CSRF required. ✅

### About `/about` — ✅ PASSED
- **FR:** FR-UI-096, D-40. Static content, CTAs to `/shop`. **RESP / A11Y / CLEAN:** ✅

### Contact `/contact` + `POST /contact` — ✅ PASSED
- **FR:** FR-UI-094, FR-UI-095, D-41, D-42, D-57.
- **VAL:** server-side required fields + email format, inline errors, values kept. ✅
- **ACT:** opens `wa.me/919288245292` with the formatted message; form cleared; fallback link shown; map only when `MAP_EMBED_URL` is set. ✅
- **AC / CLEAN:** public, CSRF required. ✅

### Login `/login` + `POST /login` — ✅ PASSED
- **FR:** FR-013–FR-025 (UI side), FR-UI-012–FR-UI-016, FR-UI-023, D-07, D-44.
- **VAL:** "Please enter email and password"; "Login Failed" alert + toast; error clears on edit; email value kept. ✅
- **ACT:** redirect rules (admin → `/admin`, safe `?redirect` honoured, open redirects rejected); session rotated; rate limited (429 message inline). ✅
- **STATE:** "Logging in..." with the button disabled. ✅

### Register `/register` + `POST /register` — ✅ PASSED
- **FR:** FR-UI-017–FR-UI-021, FR-UI-023, D-27.
- **VAL:** live checks (≥ 6 chars, passwords match); "Please fill all required fields"; duplicate email; Indian mobile format when given; values kept. ✅
- **ACT:** logged in immediately → `/` with "Account created successfully!". ✅

### Logout `POST /logout` — ✅ PASSED
- **FR:** FR-035, FR-UI-022. Session deleted on the server (replaying the old token fails); pending WhatsApp order discarded with the session; "Logout successful". ✅

### Cart `/cart` + `PUT /cart/items/{id}`, `DELETE /cart/items/{id}`, `PUT /cart/items/{id}/selected`, `PUT /cart/selection` — ✅ PASSED
- **FR:** FR-065–FR-080 (UI side), FR-UI-029, FR-UI-057–FR-UI-067, D-28, D-47.
- **AC:** guest sees the "Please Login" panel (Login → `/login?redirect=%2Fcart`); HTMX actions for a guest send `HX-Redirect` to login; CSRF required. ✅
- **ACT:** −/+ with bounds; Remove; per-line selection + Select all (new, M-14); lines of deleted products hidden and pruned; summary, selected count and header badge refreshed out-of-band; requests queued (`hx-sync`); server errors shown as toasts; empty cart switches the page to the empty state. ✅
- **STATE:** "Your Cart Is Empty"; free / pay-separately boxes with the amount still needed; mobile fixed bar. ✅
- **RESP / A11Y / CLEAN:** ✅ (checkbox and quantity controls labelled per product).

### Checkout `POST /cart/checkout`, `DELETE /cart/pending-order` — ✅ PASSED
- **FR:** FR-UI-068–FR-UI-076, D-29, D-34, D-39.
- **VAL:** exact delivery messages; invalid fields highlighted and scrolled into view; "Please select at least one product."; stock re-checked. ✅
- **ACT:** pending order stored in the user's server session; WhatsApp opened in a new tab with the real order id; redirect to the confirm page; pending-order banner on the cart (Continue / Discard); no redirect loop. ✅
- **STATE:** "Processing..." with both place-order buttons disabled. ✅

### WhatsApp Confirm `/whatsapp-confirm` + `POST /whatsapp-confirm` — ✅ PASSED
- **FR:** FR-081–FR-092 (UI side), FR-UI-028, FR-UI-077–FR-UI-083.
- **AC:** anonymous → login with redirect; no / invalid pending order → `/cart` + toast. ✅
- **ACT:** confirm creates the order (quoted prices, same order id), cleans the ordered cart lines, clears the pending order, → `/my-orders` with "Order placed successfully!"; failure (e.g. stock changed) keeps the pending order and shows the message; "Send WhatsApp Again" carries the order id; "I Haven't Sent It" → cart. ✅
- **STATE:** "Placing Order..." with all actions disabled. ✅

### My Orders `/my-orders` + `/my-orders/_list` — ✅ PASSED
- **FR:** FR-093, FR-UI-027, FR-UI-084–FR-UI-088, D-49.
- **AC:** anonymous → `/login?redirect=%2Fmy-orders`; only the user's own orders, newest first. ✅
- **STATE:** "Loading orders..."; "No Orders Yet" + Start Shopping; a separate error box + Retry (no misleading empty state). ✅

### Order Details `/my-orders/{id}` — ✅ PASSED
- **FR:** FR-094, FR-UI-089–FR-UI-093, D-50.
- **AC:** owner only; other / invalid / missing → `/my-orders` + "Order not found". ✅
- **ACT:** 5-step tracking (done / current / upcoming, "Preparing" / "On the way" / "Delivered" tags) or the 3-step cancelled timeline + notice; IST dates; shipping label rules. ✅
- **RESP / A11Y:** timeline vertical on mobile, horizontal from `sm`; `aria-current="step"`. ✅

### Error pages 404 / 403 / 500 / other — ✅ PASSED
- **FR:** FR-007, D-20, D-51. Branded pages with header and footer and links home / to the shop; JSON for `/api`; no stack traces or internal messages. ✅

### `/uploads/{file}`, `/healthz`, `/api` — ✅ PASSED
- **FR:** FR-002, FR-006, D-02, D-13. Traversal and dotfiles → 404; sandboxed CSP; legacy file names (any case or extension) served. ✅

## Admin pages (sidebar layout; all require admin)

Shared: anonymous → `/login?redirect=…`; customer full page → `/` + "Admin access required"; customer HTMX / API → 403; CSRF on every change; mobile top bar + slide-in sidebar with overlay, Esc to close. ✅

### Dashboard `/admin` + `/admin/_p/stats`, `/admin/_p/recent-orders`, `/admin/_p/dashboard` — ✅ PASSED
- **FR:** FR-UI-097–FR-UI-102, D-46. Counts, delivered revenue, six status counts, 5 recent orders with customer fallbacks; Refresh ("Refreshing..."); each section fails on its own with Retry (no misleading zeros). ✅

### Categories `/admin/categories` + `_table`, `new`, `{id}/edit`, `POST`, `PUT`, `DELETE` — ✅ PASSED
- **FR:** FR-037–FR-049, FR-UI-103–FR-UI-108, D-12, D-24.
- **VAL:** name required / case-insensitive unique; image required on create; JPG / PNG / WebP ≤ 5 MB checked in the browser and on the server (magic bytes); values kept on error. ✅
- **ACT:** live search, Refresh, add / edit with preview, delete with confirmation (blocked while products exist, message shown). ✅
- **STATE:** skeleton; "No categories found"; error + Retry. ✅

### Products `/admin/products` + partials — ✅ PASSED
- **FR:** FR-050–FR-064, FR-UI-109–FR-UI-113, D-25, D-35.
- **VAL:** documented order and messages; old price ≥ price; duplicate name per category; "Please create a category first.". ✅
- **ACT:** edit prefill (no `.0`), blank old price clears it, delete cleans carts and keeps images still used by orders. ✅

### Banners `/admin/banner` and Promotional Cards `/admin/promo-card` + `_list`, `POST`, `DELETE` — ✅ PASSED
- **FR:** FR-104–FR-117, FR-UI-114–FR-UI-119, D-27, D-36, D-37.
- **VAL:** "Please enter banner title" / "Please enter title", image required, safe link, hex colour. ✅
- **ACT:** Active checkbox; form resets to defaults after upload; list refreshed out-of-band; confirmed delete; cards drawn on their background colour. ✅
- **STATE:** "Loading banners..." / "Loading..."; "No banners found." / "No promotional cards found."; error + Retry. ✅

### Orders `/admin/orders` + `_table`, `{id}` (modal), `{id}/status` — ✅ PASSED (after R-2, R-3, R-6)
- **FR:** FR-095–FR-103, FR-UI-120–FR-UI-125, D-16, D-30, D-38.
- **ACT:** stats over all orders; search (name / mobile / order id) + status filter + pagination; the status select offers only allowed next states, asks before Cancelled / Delivered, resets on cancel or error, disables only its own row; terminal orders read-only; modal (native `<dialog>`: Esc closes, focus moves to the close button) refreshed after a change made from it. ✅
- **STATE:** "Loading orders..."; "No orders found / Try changing your search or status filter."; error + Retry. ✅

## JSON compatibility API `/api/*` (32 endpoints) — ✅ PASSED
- **FR:** FR-001–FR-122 API contracts with the Known-Issue fixes in DECISIONS §5.
- Envelope keys as specified (+ `success` on lists); admin-only writes; origin check on writes; CORS allow-list; JSON on every error, including 404 / 413 / bad JSON / uploads; generic 500 text. ✅

## Final test run after review fixes

`444 passed` (`python -m pytest`), traceability check `250 rows, 0 problems`, UI review `60 captures, 0 with issues`.

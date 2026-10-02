# AK Royal Flames — Frontend Features, API Contract & Functional Requirements

> **Purpose.** This document describes everything this React frontend does and everything it **sends to and expects from** its backend. The goal is a new backend that works with this frontend with **no frontend code changes**.
>
> **Backend-neutral.** Nothing here assumes a backend technology. Only HTTP behaviour, JSON shapes, cookies and status codes are described.
>
> **Source of truth.** Everything below comes from reading the code on branch `frontend-candle`, including the uncommitted change in `src/utils/adminApi.js`. Field names, paths and messages are copied exactly from the code. Where the code is buggy or ambiguous, this document describes what the code actually does, and the problem is listed in §10.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Configuration](#2-configuration)
3. [Routes / Pages](#3-routes--pages)
4. [Authentication Handling](#4-authentication-handling)
5. [Feature-by-Feature Breakdown](#5-feature-by-feature-breakdown)
6. [API Contract Expected by the Frontend](#6-api-contract-expected-by-the-frontend)
7. [State Management](#7-state-management)
8. [Third-Party Integrations in the UI](#8-third-party-integrations-in-the-ui)
9. [Functional Requirements List](#9-functional-requirements-list)
10. [Known Issues / Ambiguities](#10-known-issues--ambiguities)
11. [Coverage Checklist](#11-coverage-checklist)

---

## 1. Overview

**AK Royal Flames** is a single-page web shop for handmade candles, aimed at Indian customers (prices in ₹ with the `en-IN` locale, 10-digit Indian mobile numbers, 6-digit pincodes). There is no online payment. Orders are placed by sending a **WhatsApp message** to the business, and the customer then confirms the order in the web app, which saves it to the backend.

### 1.1 Tech facts relevant to integration

| Aspect | Value |
|---|---|
| Framework | React 19 SPA (Vite 8), client-side routing with `react-router-dom` v7 (`BrowserRouter`, i.e. HTML5 history URLs) |
| HTTP client | Native `fetch` only (no axios, no interceptors, no websockets) |
| Auth transport | **Cookies only**: every request uses `credentials: "include"`. No `Authorization` header, and no token is stored in JS. |
| Request bodies | `application/json` (auth, cart, orders) or `multipart/form-data` (admin create/update with image upload) |
| Response bodies | Always parsed with `response.json()`, so **every** response, including errors and DELETEs, must be JSON (exception: logout, whose body is never read) |
| Notifications | `react-hot-toast` `<Toaster position="top-center" toastOptions={{ duration: 3000 }}>` |
| Dev server | `vite --host 0.0.0.0`, port `5173` |

### 1.2 User types

| User type | How identified | Capabilities |
|---|---|---|
| **Guest** (not logged in) | `user === null` in AuthContext | Browse home/shop/about/contact, search & filter products, send a contact message via WhatsApp, register, log in. Cannot add to cart, view the cart, or place or view orders. |
| **Customer** (logged in) | `user` object present, `user.role !== "admin"` | Everything a guest can do, plus a server-side cart, placing WhatsApp orders, and viewing own order list, details and tracking. |
| **Admin** | `user.role === "admin"` | Everything a customer can do, plus the admin panel at `/admin`: dashboard, category CRUD, product CRUD, banner create/delete, promo-card create/delete, viewing all orders and changing order status. |

### 1.3 Main journeys

1. **Browse → Add to cart:** Home or Shop → pick quantity → "Add to Cart" (login required) → header cart badge updates.
2. **Checkout via WhatsApp:** Cart → fill delivery details → "Place Order on WhatsApp" → WhatsApp opens in a new tab with a pre-filled message → the user comes back to the tab → automatic redirect to `/whatsapp-confirm` → "I Have Sent WhatsApp Order" → order created in backend → ordered items removed from cart → `/my-orders`.
3. **Track order:** My Orders → order card → Order Details with a horizontal tracking timeline.
4. **Admin catalogue management:** `/admin/categories`, `/admin/products`, `/admin/banner`, `/admin/promo-card`.
5. **Admin order fulfilment:** `/admin/orders` → change status (Pending → Confirmed → Processing → Shipped → Delivered, or Cancelled). The customer sees the change in My Orders.

---

## 2. Configuration

### 2.1 Environment variables

**None.** The code has no `import.meta.env.*` or `process.env.*` references and no `.env*` files. Everything is hard-coded.

### 2.2 Base API URL logic

There is **no shared config**. A `BASE_URL` constant is declared separately in 7 files:

| File | Line | Current value | Used? |
|---|---|---|---|
| `src/utils/adminApi.js` | 1 | `"http://localhost:5000"` (uncommitted edit; the committed version is `"https://devakroyalflames.in"`, which is now commented out on line 2) | Yes. Used by `adminApi()` and `imageUrl()` (catalogue, banners, promo cards, admin orders, dashboard, image URLs everywhere) |
| `src/context/AuthContext.jsx` | 10 | `"http://localhost:5000"` | Yes (auth) |
| `src/context/CartContext.jsx` | 13 | `"http://localhost:5000"` | Yes (cart) |
| `src/pages/WhatsAppConfirm.jsx` | 16 | `"http://localhost:5000"` | Yes (`POST /api/order/create`) |
| `src/pages/MyOrders.jsx` | 25–26 | `"http://localhost:5000"` | Yes (orders list and image prefix) |
| `src/pages/OrderDetails.jsx` | 24 | `"http://localhost:5000"` | Yes (order details and image prefix) |
| `src/pages/Cart.jsx` | 33 | `"http://localhost:5000"` | **No** (declared, never used) |

**URL construction:** in every case the URL is `` `${BASE_URL}${endpoint}` ``, where `endpoint` always starts with `/api/...`. No trailing slash is added, and there is no versioning or proxy.

**Implication for the new backend:** to work without code changes, the backend must be reachable at the origin(s) above (`http://localhost:5000` in dev; `https://devakroyalflames.in` if the committed `adminApi.js` is restored), with all routes under `/api`.

### 2.3 Image URL resolution (`imageUrl()` in `src/utils/adminApi.js`)

```js
imageUrl(path):
  if (!path)                                     → ""
  if path.startsWith("http") or startsWith("data:") → path (unchanged)
  else                                           → BASE_URL + path
```

The backend must therefore return image fields either as:
- an **absolute URL** (`http://…` / `https://…`), or
- a **root-relative path starting with `/`** (e.g. `"/uploads/products/abc.jpg"`), served as a static file at `BASE_URL + path`.

`MyOrders.jsx` and `OrderDetails.jsx` don't use `imageUrl()`. They apply their own rule: `image.startsWith("http") ? image : BASE_URL + image`.

### 2.4 Hard-coded URLs, numbers and business constants

| Constant | Value | Location |
|---|---|---|
| WhatsApp business number | `919288245292` | `Cart.jsx:35`, `WhatsAppConfirm.jsx:17`, `Footer.jsx:30`, `Contact.jsx:41-42` |
| Free-delivery threshold | `1099` (₹) | `Cart.jsx:37` (`FREE_DELIVERY_LIMIT`) |
| Shipping charge | `0` (always; delivery is "paid separately" below the threshold) | `Cart.jsx:179` |
| WhatsApp order URL (cart) | `https://wa.me/919288245292?text=…` | `Cart.jsx:488-490` |
| WhatsApp order URL (resend) | `https://api.whatsapp.com/send?phone=919288245292&text=…` | `WhatsAppConfirm.jsx:188-190` |
| WhatsApp contact URL | `https://wa.me/919288245292?text=…` | `Contact.jsx:106-110` |
| WhatsApp footer URL | `https://api.whatsapp.com/send?phone=919288245292&text=Hello AK Royal Flames, I would like to know more about your candles.` | `Footer.jsx:63-66` |
| YouTube embed | `https://www.youtube.com/embed/dJJCayBThvY?autoplay=1&mute=1&loop=1&playlist=dJJCayBThvY&start=0&end=60&controls=0&rel=0&playsinline=1` | `Home.jsx:1180` |
| Instagram | `https://www.instagram.com/akroyalflames/` (footer), `https://www.instagram.com/` (contact page) | `Footer.jsx:60-61`, `Contact.jsx:433` |
| Facebook | `https://www.facebook.com/` | `Footer.jsx:155`, `Contact.jsx:445` |
| Footer email/phone/address | `your-email@example.com`, `+91 92882 45292`, `Your Store Address, India` | `Footer.jsx:28-31` |
| Contact page email/phone/address/hours | `akroyalflames@gmail.com`, `+91 9288245292`, `Delhi, India`, `Monday - Sunday: 9:00 AM - 9:00 PM` | `Contact.jsx:27-37` |
| Static images | `/images/logo.png`, `/images/candle1.jpg`, `/images/candle2.jpg`, `/favicon.svg` (served by the frontend host from `public/`) | various |

### 2.5 Third-party keys

There are **no API keys** anywhere: no maps key, payment key or analytics ID. The Contact page has a map placeholder only (§8).

---

## 3. Routes / Pages

The app has **16 routes**, defined in `src/App.jsx`. There is **no catch-all/404 route**, so unknown paths render nothing inside the router.

**Layouts**
- `WebsiteLayout` = `<Header/>` + page + `<Footer/>` (all public/customer routes).
- `AdminProtectedRoute` → `AdminLayout` (sidebar + `<Outlet/>`, no website header/footer).
- `ScrollToTop` scrolls to the top on every `pathname` change.

| # | Path | Page component | Purpose | Access | Roles | Behaviour when not allowed |
|---|---|---|---|---|---|---|
| 1 | `/` | `pages/Home.jsx` | Banner slider, promo cards, categories, latest 8 products, video | Public | All | — |
| 2 | `/shop` | `pages/Shop.jsx` | Full catalogue, category filter, search, sort. Query params `?category=<categoryId>` and `?search=<text>` | Public | All | — |
| 3 | `/about` | `pages/About.jsx` | Static brand page | Public | All | — |
| 4 | `/contact` | `pages/Contact.jsx` | Contact info + contact form sent via WhatsApp | Public | All | — |
| 5 | `/cart` | `pages/Cart.jsx` | Cart, delivery form, WhatsApp checkout | Soft-protected (in-page) | Logged-in | Shows a "Please Login" panel with **Login** (→ `/login?redirect=%2Fcart`) and **Create Account** (→ `/register`) buttons. No automatic redirect. |
| 6 | `/login` | `pages/Login.jsx` | Login form. Reads `?redirect=` | Public | All | — (an already logged-in user can still see it) |
| 7 | `/register` | `pages/Register.jsx` | Registration form | Public | All | — |
| 8 | `/my-orders` | `pages/MyOrders.jsx` | Customer's orders | Soft-protected (in-page effect) | Logged-in | After auth finishes loading, `navigate("/login?redirect=%2Fmy-orders")` |
| 9 | `/my-orders/:id` | `pages/OrderDetails.jsx` | One order with tracking. `:id` = order `_id` | **Not guarded in UI**; relies on the backend | Logged-in (owner) | If the API call fails (e.g. 401/404): error toast, then `navigate("/my-orders")`, which then redirects to login if not logged in |
| 10 | `/whatsapp-confirm` | `pages/WhatsAppConfirm.jsx` | Confirm the WhatsApp order and create it in the backend | Soft-protected (in-page effect) | Logged-in | `navigate("/login?redirect=%2Fwhatsapp-confirm", { replace: true })`. Also redirects to `/cart` if there's no valid `pendingWhatsAppOrder` in localStorage |
| 11 | `/admin` (index) | `admin/Dashboard.jsx` | Stats + recent orders | Protected | `admin` | See guard below |
| 12 | `/admin/categories` | `admin/Category.jsx` | Category CRUD | Protected | `admin` | See guard below |
| 13 | `/admin/products` | `admin/Product.jsx` | Product CRUD | Protected | `admin` | See guard below |
| 14 | `/admin/orders` | `admin/Orders.jsx` | All orders, status updates | Protected | `admin` | See guard below |
| 15 | `/admin/banner` | `admin/Banner.jsx` | Banner create/list/delete | Protected | `admin` | See guard below |
| 16 | `/admin/promo-card` | `admin/PromoCard.jsx` | Promo-card create/list/delete | Protected | `admin` | See guard below |

**Admin guard (`src/admin/AdminProtectedRoute.jsx`):**
1. While `AuthContext.loading` is true, it renders "Checking admin access...".
2. If `user` is null: `<Navigate to="/login" replace state={{ from: location.pathname }} />`. `Login` never reads `state.from` (see §10).
3. If `user.role !== "admin"`: `<Navigate to="/" replace />`.
4. Otherwise it renders `<Outlet/>`.

**Admin sidebar menu** (`AdminLayout.jsx`): Dashboard `/admin`, Categories `/admin/categories`, Products `/admin/products`, Orders `/admin/orders`, Banners `/admin/banner`, Promotional Cards `/admin/promo-card`, and "Back to Website" `/`. On mobile there's a top bar "AK Royal Flames Admin" with a hamburger toggle and an overlay.

---

## 4. Authentication Handling

### 4.1 Mechanism (cookie session)

- **No token in JavaScript.** Nothing is written to localStorage, sessionStorage or `document.cookie` for auth.
- **Every** request (auth, cart, catalogue, orders, admin) is sent with `credentials: "include"`, so the browser attaches cookies for the API origin.
- **No `Authorization` header** is ever sent.
- The backend must therefore:
  - On successful **login** and **register**, set a session cookie (e.g. `Set-Cookie` with `HttpOnly`) that identifies the user.
  - On **logout**, clear or invalidate that cookie.
  - Read that cookie on every protected endpoint.
  - Because the frontend (`:5173`) and the API (`:5000`, or another domain) are **different origins**, answer CORS with `Access-Control-Allow-Origin: <exact frontend origin>` (not `*`) and `Access-Control-Allow-Credentials: true`, and handle preflight `OPTIONS` for `Content-Type: application/json` requests and for `PUT`/`DELETE`. The cookie's `SameSite`/`Secure` attributes must allow it to be sent on these cross-origin `fetch` calls in the deployed setup.

### 4.2 Session bootstrap

`AuthProvider` (`src/context/AuthContext.jsx`) runs `getCurrentUser()` once on mount:

- `GET {BASE_URL}/api/auth/me` with credentials.
- If `response.ok && data.success`, then `user = data.user`. Otherwise `user = null`. A network error also gives `user = null`.
- `loading` starts `true` and becomes `false` once the call finishes.
- So the frontend expects `/api/auth/me` to return **non-2xx or `success:false` when not logged in**. Either works: a `401` with JSON, or a `200` with `{ "success": false }`.

### 4.3 Login (`/login`)

1. The user enters `email` and `password`.
2. Client validation: if `!email.trim() || !password`, the inline error and toast both read **"Please enter email and password"**.
3. `login(email.trim(), password)` sends `POST /api/auth/login` with JSON `{ email, password }`.
4. Failure (`!response.ok || !data.success`) throws `data.message || "Login failed"`. The page shows that message in a red box titled **"Login Failed"** and also as a toast. If the error has no message, the fallback is "Invalid email or password".
5. Success: `user = data.user`, toast **"Login successful!"**, then:
   - if `result.user.role === "admin"` → `navigate("/admin")`
   - else if `?redirect=` is present → `navigate(redirect)`
   - else → `navigate("/")`
6. The button reads "Logging in..." and is disabled while the request is in flight. Editing either field clears the error.

### 4.4 Registration (`/register`)

Fields: `name` (text, required), `email` (type=email, required), `phone` (text, optional), `password` (required), `confirmPassword` (required, never sent).

Live validation while typing:
- Password `1..5` chars → "Password must be at least 6 characters"
- Confirm doesn't match → "Passwords do not match"

On submit:
- Any of name/email/password/confirmPassword empty (name and email are trimmed) → toast "Please fill all required fields"
- `password.length < 6` → inline + toast "Password must be at least 6 characters"
- mismatch → inline + toast "Passwords do not match"
- Then `POST /api/auth/register` with JSON `{ name: trimmed, email: trimmed, phone: trimmed, password }`.
- Failure throws `data.message || "Registration failed"`, shown as a toast. The page-level fallback is "Registration failed. Please try again.".
- Success: `user = data.user` (**the user counts as logged in right away**, so the backend must set the session cookie on register), toast **"Account created successfully!"**, then `navigate("/")`.

### 4.5 Logout

- Triggered from the Header (desktop icon button or mobile "Logout" button).
- `POST /api/auth/logout` with credentials and no body. **The response body is not read**, and network errors are caught and only logged.
- `user` is set to `null` regardless of the response. That triggers `CartContext` to clear the cart.
- Toast **"Logout successful"**, the mobile menu closes, then `navigate("/")`. The mobile button shows "Logging out..." while in progress.

### 4.6 401/403 and token expiry

- **There's no global 401/403 handler.** Each caller treats any non-2xx (or `success:false`) as an error and shows the response's `message`.
- After the initial `/api/auth/me` call the frontend never re-checks the session. If the session expires mid-use, the UI still believes the user is logged in until a reload. API calls then fail and show the server's `message` in a toast or inline error.
- The backend should therefore return a **JSON body with a human-readable `message`** on 401/403 (e.g. `{ "success": false, "message": "Please login to continue" }`), because that text is shown to users directly.

### 4.7 Role usage in the UI

`user.role` is compared against the exact string `"admin"`.

| Place | Behaviour |
|---|---|
| `AdminProtectedRoute` | Only `role === "admin"` can render `/admin/*` |
| `Login` | Admins always go to `/admin` after login, and `?redirect` is ignored for them |
| `Header` (desktop) | The user-name chip links to `/admin` for admins and to `/` otherwise. An extra dashboard icon link to `/admin` is shown only for admins |
| `Header` (mobile) | An "Admin Dashboard" link is shown only for admins |

### 4.8 `user` object fields read by the UI

| Field | Where used |
|---|---|
| `name` | Header chip and mobile "Welcome" block, My Orders "Welcome, {name}", Cart name autofill |
| `role` | See §4.7 |
| `phone` | Cart `mobile` autofill |
| `address`, `city`, `pincode` | Cart autofill (optional. If the backend doesn't return them, the fields stay empty) |

---

## 5. Feature-by-Feature Breakdown

### 5.1 Global Header (`src/components/Header.jsx`)

- **Logo** (`/images/logo.png`) links to `/`.
- **Desktop nav** (md+): HOME `/` (exact match), SHOP `/shop`, ABOUT `/about`, CONTACT `/contact`. The active link is highlighted.
- **Search toggle** (magnifier icon) opens a search bar with the input placeholder "Search candles..." and a **Search** button. Submitting navigates to `/shop?search=<encodeURIComponent(trimmed)>`, or to `/shop` if the query is empty, then closes the search and mobile menu. No API call is made.
- **Cart icon** links to `/cart`. The badge shows `cartCount` (sum of all cart item quantities, selected or not) and is hidden when 0. It shows "99+" above 99.
- **Logged out:** a "Login" button links to `/login` (sm+).
- **Logged in:** "My Orders" links to `/my-orders`. The user-name chip (truncated) links to `/admin` for admins and `/` otherwise. Admins also get a dashboard icon linking to `/admin`. The logout icon is disabled while logging out.
- **Mobile menu** (hamburger, below md): the same nav links. Logged out: "Login". Logged in: a "Welcome {name}" card, "My Orders", "Admin Dashboard" (admins only), and "Logout"/"Logging out...".

### 5.2 Global Footer (`src/components/Footer.jsx`)

Static content only, with **no API calls**:
- Logo, brand description, a "Follow Us" row (Instagram `akroyalflames`, Facebook root, WhatsApp link), "@akroyalflames".
- Quick Links: Home, Shop All Candles, About Us, Contact Us, Shopping Cart.
- Contact Us: address, `tel:` phone link, WhatsApp link, `mailto:` email (placeholder values, see §10).
- "Stay Connected" text. **The newsletter form is commented out.** `handleSubscribe` (a mailto link) exists but is unreachable.
- Brand strip "Light up your moments with AK Royal Flames" and "© {current year} AK Royal Flames. All rights reserved." / "Made with ♥ for candle lovers".

### 5.3 Home (`/`, `src/pages/Home.jsx`)

**On mount, 4 API calls in parallel:**
- `GET /api/category/get-category` → `categories`
- `GET /api/product/get-product` → `products`
- `GET /api/banner/get-banner` and `GET /api/promo-card/get-promo-card` via `Promise.all`. **If either fails, both lists are cleared** and one error toast is shown.

**Sections**

1. **Hero slider.** One slide per banner, in the order the API returns them (no client sort).
   - Image: `imageUrl(banner.image)`. Alt text: `banner.title` or "Candle banner N".
   - `banner.title` is shown as the H1 if present. `banner.subtitle` is shown if present.
   - The CTA button appears **only if `banner.title`** is present. Its label is `banner.buttonText || "Shop Now"`. On click: if `buttonLink` starts with `/`, it navigates in-app. If another non-empty value, it does `window.location.href = buttonLink`. If empty, it navigates to `/shop`.
   - Auto-advances every **4000 ms** when there's more than one banner. Prev/next arrows and dot indicators work. Arrows do nothing when there's one banner or none.
   - Empty: "No banners available".
2. **Promo cards.** Grid of 1, 2 or 3 columns. Each card has background colour `card.background || "#08aaa6"`, image `imageUrl(card.image)`, `card.title`, `card.subtitle`, and a pill labelled `card.buttonText || "Shop Now"`. Clicking uses the same `buttonLink` rule as the banners. Nothing is shown when the list is empty.
3. **Shop by Category.**
   - Loading: 10 skeleton tiles.
   - Error: red box with the message and a **Retry** button (re-calls the categories endpoint). The error also shows as a toast. Fallback message "Unable to load categories".
   - Empty: "No categories available yet."
   - Otherwise a tile per category: `imageUrl(category.image)` (cart icon if no image) and `category.name`. Clicking goes to `/shop?category=<category._id>`.
   - A "View All" link goes to `/shop`.
4. **Our Candle Collection.** The **latest 8 products**, sorted by `createdAt` descending on the client.
   - Loading: 8 skeletons.
   - Error: message + **Retry** + toast. Fallback "Unable to load products".
   - Empty: "No products available yet."
   - **Product card:** image (cart icon fallback), a "Save {discount}%" badge when `oldPrice > price` (discount = `round((oldPrice − price) / oldPrice × 100)`), a "Sold Out" badge when `stock <= 0`, name, description (2 lines), price `₹x` (`en-IN`), struck-through `oldPrice` when greater than price, and "{stock} In Stock" or "Out of Stock".
   - Quantity stepper (only when in stock): minimum 1, maximum `stock`.
   - "Add to Cart" button (disabled when out of stock). Labels: "Out of Stock" / "Add More" (after a success) / "Add to Cart".
   - "View All Products" buttons go to `/shop`.
5. **Promo banner.** If there's at least one banner, `banners[0].image` is shown again as a full-width clickable image (same `buttonLink` rule).
6. **Video.** YouTube iframe (autoplay, muted, loop, first 60 s).
7. **Community banner.** "Join Our Candle Making Community" with an "Explore Now" button to `/shop`.

**Add to cart on Home:**
- Not logged in: toast "Please login first to add products to cart", then `navigate("/login")` after 1000 ms. The card shows "Please login first".
- Logged in: it calls `CartContext.addToCart(product, quantity)` **without awaiting it**. The request does go out (`POST /api/cart/add`), but the UI result is wrong (see §10, item K-02).

### 5.4 Shop (`/shop`, `src/pages/Shop.jsx`)

**On mount:** `GET /api/category/get-category` and `GET /api/product/get-product` (independent calls, each with its own loading and error state and an error toast).

**URL state:**
- `?category=<id>` selects a category. Absent means "all".
- `?search=<text>` sets the initial search box value and stays in sync whenever the URL changes (e.g. from the Header search).

**UI:**
- Banner "Find Your Perfect Glow" with a Home › Shop breadcrumb.
- **Category sidebar** (sticky on desktop, a slide-in drawer on mobile opened by the "Categories" button):
  - "All Products" with a count of all products.
  - One row per category with its image (sparkle icon fallback), name, and "{n} products". The count is computed on the client by matching `product.category` to `category._id`.
  - Loading: 5 skeleton rows.
  - Error: message + Retry.
  - Empty: "No categories available."
  - Selecting a category updates `?category` (without scroll reset) and closes the drawer.
- **Search input** (client-side, case-insensitive). It matches product `name`, the resolved category name, or `description`. A clear "×" button appears when there's text. **The search box doesn't write back to the URL.**
- **Sort** select: `default` = "Featured" (newest `createdAt` first), `low` = "Price: Low to High", `high` = "Price: High to Low", `name` = "Name: A to Z".
- Heading: the selected category name, or "All Candles". Subtext "Loading products..." or "{n} products found". A cart-count pill links to `/cart`.
- **Status message banner** (green or red, dismissible) shows the last add-to-cart result.
- **Products error:** message + Retry.
- **Grid** of product cards:
  - Category label: `product.category.name` if populated, otherwise looked up in `categories` by id, otherwise "Candles".
  - Wishlist heart (**local state only**, no API, lost on navigation).
  - "{discount}% OFF" badge, "SOLD OUT" overlay, price, old price, "● {stock} In Stock" / "● Out of Stock".
  - Quantity stepper (1..stock) and "Add to Cart" / "Adding..." / "Out of Stock".
- **Empty state:** "No Candles Found" / "Try another search or category." with a "View All Candles" button that clears search, sort, `category` and `search`.
- Bottom promo "Find Your Perfect Candle" with a "Contact Us" button to `/contact`.

**Add to cart on Shop** (awaited properly):
- Not logged in: the banner and a toast both read **"Please login first to add products to cart."** No redirect.
- Success: the banner and toast read `result.message || "Product added to cart"`. The quantity resets to 1.
- Failure: the banner and toast show the error message, with fallbacks "Unable to add product to cart" (banner) and "Unable to add product" (toast).

### 5.5 Cart (`/cart`, `src/pages/Cart.jsx`)

**States:**
- Auth loading: spinner "Loading cart...".
- Not logged in: "Please Login" / "Please login to view your personal cart and place an order." with **Login** (→ `/login?redirect=%2Fcart`) and **Create Account** (→ `/register`).
- Empty cart (`cart.length === 0`): "Your Cart Is Empty" / "Add your favourite candles to continue." with a "Continue Shopping" button to `/shop`.
- Main view: a sticky header "My Cart", "{selectedQuantity} item(s) selected", and a back arrow (`navigate(-1)`).

**Cart items list** (all cart items are listed, selected or not):
- Image (`imageUrl`), name, "Unit Price: ₹x", "Item Total: ₹(price × qty)".
- **−** is disabled at qty ≤ 1 and calls `PUT /api/cart/update { productId, quantity: qty-1 }`.
- **+** is disabled when `stock > 0 && qty >= stock` and calls `PUT /api/cart/update { productId, quantity: qty+1 }`.
- **Remove** calls `DELETE /api/cart/remove/:productId`.
- No loading indicators and no error handling on these actions (see §10).
- **There's no UI to toggle item selection**, but totals only count items whose `selected` isn't `false`.

**Delivery Details form** (`id="customer-details"`):

| Field (`name`) | Input | Client normalisation | Validation (on submit) → error text |
|---|---|---|---|
| `name` | text, placeholder "Enter your full name" | trimmed on submit | empty → "Please enter your full name." |
| `mobile` | tel, placeholder "10 digit mobile number" | non-digits stripped, max 10 chars | empty → "Please enter your mobile number."; not `/^[6-9]\d{9}$/` → "Please enter a valid 10 digit mobile number." |
| `address` | textarea (3 rows), placeholder "House/Flat No., Street, Area..." | trimmed | empty → "Please enter your complete address." |
| `city` | text, placeholder "Your city" | trimmed | empty → "Please enter your city." |
| `pincode` | text, placeholder "6 digit pincode" | non-digits stripped, max 6 chars | empty → "Please enter your pincode."; not `/^\d{6}$/` → "Please enter a valid 6 digit pincode." |
| `message` | textarea (2 rows), label "Order Note (Optional)", placeholder "Any special instruction?" | trimmed | none |

- Fields are auto-filled once from `user.name`, `user.phone`, `user.address`, `user.city` and `user.pincode`. Values the user has already typed are never overwritten.
- Typing in a field clears that field's error.
- If validation fails, the page smooth-scrolls to `#customer-details`.

**Order Summary (client-side calculations):**
- `itemsTotal = subtotal = Σ(price × quantity)` over **selected** items.
- `isFreeShipping = itemsTotal >= 1099`.
- `shippingCharge = 0` (constant).
- `amountForFreeDelivery = max(1099 − itemsTotal, 0)`.
- `grandTotal = itemsTotal + 0`.
- "Items ({selectedQuantity})" ₹itemsTotal. "Delivery": **"FREE"** (green) or **"Pay Separately"** (orange).
- Below the threshold, an orange box reads "Delivery charges not included / Actual delivery charges will be paid separately to the delivery person at the time of delivery." plus "Add ₹X more to get FREE delivery". There's also a footnote "*Grand Total does not include delivery charge…".
- At or above the threshold, a green box reads "🎉 FREE delivery applied / Your order value is ₹1099 or above."
- Grand Total.
- Button **"Place Order on WhatsApp"** (desktop) and a fixed mobile bar showing the Grand Total with **"Place Order"**. Helper text: "Your order details will be saved and sent to AK Royal Flames WhatsApp."

**Place Order on WhatsApp (`placeOrderOnWhatsApp`):** no API call at this step.
1. Not logged in: toast "Please login first to place your order.", then go to `/login?redirect=%2Fcart`.
2. No selected items: toast "Please select at least one product."
3. Validate the form (above).
4. Save the **pending order** to `localStorage["pendingWhatsAppOrder"]`:
   ```json
   {
     "customer": { "name": "...", "mobile": "9876543210", "address": "...", "city": "...", "pincode": "110001", "message": "" },
     "items": [ { "_id": "<productId>", "name": "...", "image": "/uploads/x.jpg", "price": 499, "quantity": 2 } ],
     "itemsTotal": 998,
     "shipping": 0,
     "shippingStatus": "PAYABLE_SEPARATELY",
     "grandTotal": 998
   }
   ```
   `shippingStatus` is `"FREE"` when `itemsTotal >= 1099`, otherwise `"PAYABLE_SEPARATELY"`.
5. Generate a client-only **order reference** `AKRF-YYYYMMDD-NNNN` (UTC date + 4 random digits). It's only used in the WhatsApp text and never sent to the backend.
6. Build a formatted WhatsApp message (sections: ORDER INFORMATION with the reference and total items; CUSTOMER DETAILS; PRODUCT DETAILS with qty, unit price and item total per line; PAYMENT SUMMARY; a FREE DELIVERY or DELIVERY CHARGES note; an optional CUSTOMER NOTE; a thank-you line). Open `https://wa.me/919288245292?text=<encoded>` in a new tab.
7. Toast "WhatsApp opened. Send the message and return here."
8. **Return detection:** while `/cart` is mounted, a `visibilitychange` listener waits for the document to become visible. If `pendingWhatsAppOrder` exists, it calls `navigate("/whatsapp-confirm")` after 300 ms.

### 5.6 WhatsApp Confirm (`/whatsapp-confirm`, `src/pages/WhatsAppConfirm.jsx`)

**On mount:**
- Reads `localStorage["pendingWhatsAppOrder"]`:
  - Missing: toast "No pending WhatsApp order found." and `navigate("/cart", { replace: true })`.
  - Not an object, or `items` empty or not an array: the key is removed, toast "Pending order data is invalid.", then `/cart`.
  - JSON parse error: the key is removed, toast "Unable to load pending order.", then `/cart`.
- Auth: if not logged in once auth has loaded, `navigate("/login?redirect=%2Fwhatsapp-confirm", { replace: true })`.

**UI:**
- Loading: "Loading order...".
- Back link "Back to Cart".
- Header "WhatsApp Order" / "Please make sure you have sent the order details on WhatsApp."
- Green info box "Did you send the WhatsApp message?".
- Customer Details (Name, Mobile, Address, City, Pincode; "-" if empty).
- "Ordered Products" (name, quantity, unit price, line total).
- Order Summary (Items Total, Shipping "FREE"/"Pay Separately", Grand Total).
- Buttons:
  - **"I Have Sent WhatsApp Order"** (shows a spinner and "Placing Order..." while busy).
  - **"Send WhatsApp Again"** reopens WhatsApp via `https://api.whatsapp.com/send?phone=…&text=…`. The rebuilt message has **no** order reference or ORDER INFORMATION section and no delivery-charge paragraph.
  - **"I Haven't Sent It"** goes to `/cart` and keeps the pending order (see §10).
- Footnote "Your cart will be updated only after the order is successfully confirmed."
- Fallback view "No Pending Order" with a "Go Back To Cart" button.

**Confirm (`confirmWhatsAppOrder`):**
1. Guards: not logged in → toast "Please login first." and redirect to login. No pending order → "Pending order information not found." → `/cart`. No items → "No products found in this order." → `/cart`.
2. `POST /api/order/create` with the payload in §6.6.1.
3. Failure: toast with `data.message || "Failed to create order."` (or the network error message, with fallback "Unable to place order."). The user stays on the page and the pending order is kept.
4. Success:
   - For each ordered product id, call `DELETE /api/cart/remove/:productId` in sequence. **Errors are swallowed**, since the backend may already have removed them.
   - `GET /api/cart` (`fetchCart`).
   - Remove `localStorage["pendingWhatsAppOrder"]`.
   - Toast **"Order placed successfully!"**.
   - After 300 ms, `navigate("/my-orders", { replace: true })`.

### 5.7 My Orders (`/my-orders`, `src/pages/MyOrders.jsx`)

- Once auth has loaded and there's no user, it redirects to `/login?redirect=%2Fmy-orders`.
- Otherwise it calls `GET /api/order/my-orders` and sets `orders = data.orders || []`. Errors show a toast (`data.message || "Failed to load orders"`, fallback "Unable to load orders") and the page then renders the empty state.
- Loading: spinner "Loading orders...".
- Header: back arrow, "My Orders", "Welcome, {user.name}".
- Empty: "No Orders Yet" / "Your WhatsApp orders will appear here." with a "Start Shopping" button to `/shop`.
- Otherwise "{n} Order(s)", then for each order **in API order (no client sort)**:
  - Clickable header to `/my-orders/{order._id}`: "Order ID" with `order.orderId`, and a status pill (colour and icon by status).
  - "Order Date" `formatDate(order.createdAt)`.
  - "Expected Delivery" `formatDate(order.expectedDelivery)`, shown only if the status isn't `Cancelled` and the field is truthy.
  - Current status date: label "Order Placed" for Pending, otherwise "{status} On". Value `statusDates[status]` (for Pending, falls back to `createdAt`), otherwise "Not available".
  - If `Delivered` and `statusDates.Delivered` is set, a green box "Delivered on {datetime}".
  - The first 3 items: image (http → as-is, else `BASE_URL + image`; package icon fallback), name, "Qty: {quantity} × ₹{price}", and `₹{item.total}`. Then "+N more product(s)".
  - "Grand Total" `₹{order.grandTotal}` and a chevron link to the details page.
- Date formats: `formatDate` uses `en-IN` `{day:"2-digit", month:"short", year:"numeric"}` (e.g. "05 Oct 2026"). `formatDateTime` adds `hour`/`minute` (2-digit). Invalid or missing dates show "-".

### 5.8 Order Details (`/my-orders/:id`, `src/pages/OrderDetails.jsx`)

- Calls `GET /api/order/my-orders/:id` and sets `order = data.order`. On error: toast (`data.message || "Unable to get order"`, fallback "Unable to load order"), then `navigate("/my-orders")`.
- Loading: "Loading order...". If `order` is null: "Order not found" with a "My Orders" button.
- Header: back arrow, "Order Details", and `order.orderId`.
- **Current status** card: a pill with the status, plus the current status date (same rule as My Orders, using `formatDateTime`).
- **Expected Delivery** (not shown when Cancelled; only when the field is set).
- **Cancelled box:** "Order Cancelled / Cancelled on {statusDates.Cancelled}".
- **Tracking:**
  - Cancelled: 3 steps, "Order Placed" (`statusDates.Pending || createdAt`), "Confirmed" (done if `statusDates.Confirmed`, otherwise "Pending"), and "Cancelled" (`statusDates.Cancelled`).
  - Otherwise 5 steps: Pending ("Order Placed", `statusDates.Pending || createdAt`), Confirmed, Processing, Shipped, Delivered. Each step is marked by the index of the current status (Pending 0 … Delivered 4; unknown → 0). Steps before the current one show green ticks, the current step is highlighted, and later steps are grey. Each step shows its `statusDates[key]` datetime or "Pending". The current step gets a tag: "Preparing" (Processing), "On the way" (Shipped), or "Delivered".
- **Products:** image (same rule as My Orders), name, "Qty: n", "₹price × n", and `₹item.total`.
- **Delivery Details:** `customer.name`, `customer.mobile`, `customer.address`, and "`city`, `pincode`".
- **Order Summary:**
  - Items Total `itemsTotal`.
  - Shipping: if `shippingStatus === "FREE"` → "FREE"; if `"PAYABLE_SEPARATELY"` → "PAYABLE SEPARATELY"; else if `shipping > 0` → `₹shipping`; else "PAYABLE SEPARATELY".
  - The matching orange or green info box.
  - Grand Total.
- "Back to My Orders" button.

### 5.9 About (`/about`) and Contact (`/contact`)

- **About:** static. Hero, "Our Story" (image `/images/candle2.jpg`), "Our Mission", 4 feature cards (Made With Love, Quality Materials, Premium Collection, Beautiful Designs), and a CTA banner. Both "Explore Collection" and "Shop Now" are plain `<a href="/shop">` links (full page reload).
- **Contact:**
  - Static info cards: Call Us, Email Us, Visit Us, Working Hours.
  - Image `/images/candle1.jpg`, a business details block with `tel:` and `mailto:` links, and social links.
  - A map **placeholder** reading "Add your business Google Maps embed here".
  - **Contact form** (no API):

    | Field | Type | Required (HTML) |
    |---|---|---|
    | `name` | text | yes ("Full Name *") |
    | `email` | email | yes ("Email Address *") |
    | `phone` | tel | no |
    | `subject` | text | yes ("Subject *") |
    | `message` | textarea (5 rows) | yes ("Your Message *") |

    On submit it builds the WhatsApp text "*AK ROYAL FLAMES - CONTACT MESSAGE*…" (phone falls back to "Not provided"), opens `https://wa.me/919288245292?text=…` with `noopener,noreferrer`, and clears the form. No success message is shown.

### 5.10 Admin — Dashboard (`/admin`, `src/admin/Dashboard.jsx`)

- **On mount:** `Promise.all` of `GET /api/product/get-product`, `GET /api/category/get-category` and `GET /api/order/all`. **If any one fails, all three lists are emptied** and a red error box shows `err.message || "Unable to load dashboard"`.
- Arrays are pulled out of each response by the tolerant `getArray` (§6.0.3).
- Loading: "Loading dashboard...". "Refresh" button shows "Refreshing..." with a spinning icon.
- **Stat cards:**
  - Products = `products.length`
  - Categories = `categories.length`
  - Total Orders = `orders.length`
  - **Delivered Revenue** = Σ `grandTotal` over orders with `status === "Delivered"` ("Only delivered orders")
- **Order Status cards:** counts for Pending, Confirmed, Processing, Shipped, Delivered and Cancelled.
- **Recent Orders:** the 5 newest by `createdAt`. Columns:
  - Order: `orderId`, or the last 8 characters of `_id`
  - Customer: `customer.name || user.name || "-"` and `customer.mobile || customer.phone || user.phone || "-"`
  - Items: Σ `items[].quantity`, shown as "Items"
  - Amount: `grandTotal`
  - Status pill: `status || "Pending"`
  - Date: `createdAt`
- Badge "{n} Total". Empty: "No orders yet / Customer orders will appear here."

### 5.11 Admin — Categories (`/admin/categories`, `src/admin/Category.jsx`)

- **List:** `GET /api/category/get-category` shown in `DataTable` titled "Categories ({count})" with subtitle "Manage your categories".
  - Columns: Image (`imageUrl(category.image)`), Category Name, Description (`—` if empty), and Actions (edit/delete).
  - Client search on `name` and `description`, placeholder "Search categories...".
  - Buttons: "Add New" and "Refresh".
  - Loading: "Loading...". Empty: "No categories found".
  - Fetch error: red alert with `err.message || "Failed to fetch categories"`.
- **Add/Edit form** (replaces the table while open):
  - Title "Add Category"/"Edit Category", subtitle "Create a new category"/"Update category details".
  - **Category Image:** file input, `accept="image/jpeg,image/png,image/webp"`. Required on create only. Shows a preview ("Click to change image"). On edit the hint reads "Leave the image unchanged to keep the current image."
    - Type not in `[image/jpeg, image/png, image/webp]` → "Only JPG, PNG and WebP images are allowed"
    - Size > 5 MB (5 × 1024 × 1024) → "Image must be under 5 MB"
  - **Category Name** (`name`, required, placeholder "Scented Candles"). Blank after trim → "Category name is required".
  - **Description** (`description`, textarea, optional).
  - Create without an image → "Please upload a category image".
  - Buttons: "Save Category" / "Update Category" / "Saving..." and "Cancel". The × close button is disabled while saving.
- **Submit:** `POST /api/category/create-category` or `PUT /api/category/update-category/:id` with multipart `name`, `description` (trimmed, possibly `""`), and `image` only when a new file was chosen.
  - If the response has `data._id`, the row is inserted at the top (create) or replaced (edit) straight away.
  - The form closes, a green message shows "Category created successfully" / "Category updated successfully", and the list is refetched.
  - Error: red alert with `err.message || "Failed to save category"`.
- **Delete:** `window.confirm('Are you sure you want to delete "{name}"?')`, then `DELETE /api/category/delete-category/:id`. The row is removed and "Category deleted successfully" is shown. Error: `err.message || "Failed to delete category"`. While a delete is running, all delete buttons are hidden.

### 5.12 Admin — Products (`/admin/products`, `src/admin/Product.jsx`)

- **On mount:** `GET /api/product/get-product` (sets `products = result.data || []`) and `GET /api/category/get-category` (fills the category dropdown).
- **Table** "Products ({count})":
  - Image.
  - Product Name.
  - Category: `product.category.name` if populated, otherwise looked up by id, otherwise "—".
  - Price: "₹{price}", plus a struck-through "₹{oldPrice}" whenever `oldPrice != null`.
  - Stock: the number in green, or "Out of stock" in red when ≤ 0.
  - Actions.
  - Search on `name` and category name, placeholder "Search products...". Empty: "No products found".
- **Form fields:**

  | Field (`name`) | Input | Validation → message |
  |---|---|---|
  | `image` | file, `accept="image/jpeg,image/png,image/webp"` | wrong type → "Only JPG, PNG and WebP images are allowed"; > 5 MB → "Image must be under 5 MB"; missing on create → "Please upload a product image" |
  | `name` | text, required, placeholder "Rose Scented Candle" | blank → "Product name is required" |
  | `category` | select of `categories` (value = `_id`), first option "Select Category" | empty → "Please select a category"; shows "Please create a category first." when there are no categories |
  | `price` | number, min 1, required | `""`, non-finite, or < 1 → "Please enter a valid price" |
  | `oldPrice` | number, min 1, optional | if non-empty and (non-finite or < price) → "Old price must be greater than or equal to selling price" |
  | `stock` | number, min 0, step 1, required | `""`, non-integer, or < 0 → "Please enter valid stock" |
  | `description` | textarea | none |

  Validation runs in this order: name → category → image (create) → price → stock → oldPrice.
- **Submit:** `POST /api/product/create-product` or `PUT /api/product/update-product/:id`, multipart (§6.4). Then the list is refetched, the form closes, and "Product created successfully" / "Product updated successfully" is shown. Errors show `err.message`.
  - Buttons: "Upload Product" / "Update Product" / "Saving...".
- **Edit prefill:** `category = product.category?._id || product.category`. `price`, `oldPrice` and `stock` use `?? ""`. Preview is `imageUrl(product.image)`.
- **Delete:** confirm `Are you sure you want to delete "{name}"?`, then `DELETE /api/product/delete-product/:id`. The row is removed and "Product deleted successfully" is shown.

### 5.13 Admin — Banners (`/admin/banner`, `src/admin/Banner.jsx`)

- Page title "Banner Management".
- **Form "Add New Banner"** (create only; there's **no edit**):

  | Field | Input | Default | Validation |
  |---|---|---|---|
  | `title` | text, placeholder "Luxury Scented Candles" | `""` | blank → toast "Please enter banner title" |
  | `subtitle` | text, placeholder "Beautiful handmade candles" | `""` | — |
  | `buttonText` | text | `"Shop Now"` | — |
  | `buttonLink` | text, placeholder "/shop" | `"/shop"` | — |
  | `order` | number | `0` | — |
  | `image` | file, `accept="image/*"`, `id="banner-image"` | — | missing → toast "Please select banner image" (no type or size check) |

- **Submit:** `POST /api/banner/create-banner` (multipart). Success toast "Banner uploaded successfully", the form resets, and the list is refetched. Error toast `error.message || "Failed to upload banner"`. The button reads "Upload Banner" / "Uploading...".
- **List "All Banners":** `GET /api/banner/get-all-banner`.
  - Each card shows the image, `title`, `subtitle`, "Button: {buttonText}", "Order: {order}", and a **Delete** button.
  - Loading "Loading banners...", empty "No banners found.", load error toast `error.message || "Failed to load banners"`.
- **Delete:** confirm "Are you sure you want to delete this banner?", then `DELETE /api/banner/delete-banner/:id`. Toast "Banner deleted successfully" and refetch. Error toast `error.message || "Delete failed"`.

### 5.14 Admin — Promotional Cards (`/admin/promo-card`, `src/admin/PromoCard.jsx`)

- Page title "Promotional Card Management".
- **Form "Add Promotional Card"** (create only):

  | Field | Input | Default | Validation |
  |---|---|---|---|
  | `title` | text, placeholder "Luxury Scented Candles" | `""` | blank → toast "Please enter title" |
  | `subtitle` | text, placeholder "Bring fragrance into your home" | `""` | — |
  | `buttonText` | text | `"Shop Now"` | — |
  | `buttonLink` | text, placeholder "/shop" | `"/shop"` | — |
  | `background` | `type="color"` (value like `#08aaa6`) | `"#08aaa6"` | — |
  | `order` | number | `0` | — |
  | `image` | file, `accept="image/*"`, `id="promo-image"` | — | missing → toast "Please select image" |

- **Submit:** `POST /api/promo-card/create-promo-card` (multipart). Toast "Promotional card uploaded", form reset, refetch. Error toast `error.message || "Upload failed"`. The button reads "Upload Promotional Card" / "Uploading...".
- **List "All Promotional Cards":** `GET /api/promo-card/get-all-promo-card`.
  - Each card has background `card.background || "#08aaa6"` and shows the image, `title`, `subtitle`, "Button: {buttonText}", and a **Delete** button.
  - Loading "Loading...", empty "No promotional cards found.", load error toast `error.message || "Failed to load promo cards"`.
- **Delete:** confirm "Are you sure you want to delete this card?", then `DELETE /api/promo-card/delete-promo-card/:id`. Toast "Promotional card deleted" and refetch. Error toast `error.message || "Delete failed"`.

### 5.15 Admin — Orders (`/admin/orders`, `src/admin/Orders.jsx`)

- **Load:** `GET /api/order/all` and sets `orders = result.orders || result.data || []` (must be an array). Error: red box with `err.message || "Unable to load orders"`. Loading: "Loading orders...". "Refresh" re-fetches with a spinning icon.
- Header "Orders" / "Manage customer WhatsApp orders".
- **Stats** (client-side): Total Orders, Pending, Processing, Delivered, Cancelled.
- **Search** (client-side, case-insensitive) on `customer.name`, `customer.mobile` and `orderId`, placeholder "Search by order ID, name or mobile...".
- **Status filter:** "All Status" or one of `Pending | Confirmed | Processing | Shipped | Delivered | Cancelled`.
- **Table columns** (in API order, no client sort):

  | Column | Content |
  |---|---|
  | Order | `orderId` (or the last 8 characters of `_id`), with `paymentMethod || "WhatsApp Order"` underneath |
  | Customer | `customer.name`, `customer.mobile` |
  | Products | "{items.length} product(s)" and the comma-joined item names |
  | Total | `₹grandTotal` |
  | Status | a `<select>` of the 6 statuses with value `status || "Pending"`, coloured by status. **Changing it immediately calls the status update.** |
  | Order Date | date and time from `createdAt` |
  | Expected Delivery | `expectedDelivery` date, or "-" |
  | Action | a **View** button that opens a modal |

- Empty: "No orders found" / "Try changing your search or status filter."
- **Status update:** `PUT /api/order/status/:_id` with JSON `{ "status": "<new>" }`.
  - Success: toast `result.message || "Order status updated"`. If the response has `order` (or `data.order`) and the modal is showing that order, the modal is replaced with it. Then the list is re-fetched quietly.
  - Error toast: `err.message || "Unable to update order status"`.
  - While updating, **every** status select is disabled.
- **Order modal:**
  - Header with `orderId` (or `_id`) and a × close button.
  - "Order Received" (`createdAt` datetime) and "Expected Delivery".
  - Customer Details: name, mobile, address, and "city - pincode".
  - Current Order Status, with another status `<select>`.
  - **Order Timeline:** for each of the 6 statuses, the label (Order Pending, Order Confirmed, Processing, Shipped, Delivered, Cancelled) with `statusDates[key]`. If missing, it shows "Not available" for Pending and "Not {key lowercased} yet" for the others. The current status gets a "Current" tag.
  - Products: image, name, "Qty", "Price", and the line total `item.total ?? price × quantity`.
  - Totals: Items Total, Shipping ("FREE" or "Pay Separately"), Grand Total.
  - **Customer Note** (`customer.message`) if present.
  - Order Date and Expected Delivery again at the bottom.

### 5.16 Shared admin component — `DataTable` (`src/components/DataTable.jsx`)

A generic table used by Categories and Products: title with count, "Manage your {title lowercased}", optional "Add New" and "Refresh" (disabled while loading), a client-side search box filtering over `searchKeys` (strings or functions) or column `searchValue`, Edit (pencil) and Delete (trash) actions, a "Loading..." state and a configurable empty message. It makes no API calls itself.

### 5.17 Unused component — `AddToCartButton` (`src/components/AddToCartButton.jsx`)

Exported but **not imported anywhere**. If it were used it would call `addToCart` synchronously (same bug as Home, §10 K-02).

---

## 6. API Contract Expected by the Frontend

### 6.0 Conventions that apply to every endpoint

#### 6.0.1 Transport
- Base: `{BASE_URL}` (§2.2). Paths below are appended exactly as written.
- All requests: `credentials: "include"` (cookies sent).
- JSON requests send the header `Content-Type: application/json`.
- Multipart requests set **no** `Content-Type` header manually; the browser sets `multipart/form-data; boundary=…`.
- No other custom headers.

#### 6.0.2 Response envelope and error reading

There are three slightly different client wrappers:

| Wrapper | Used by | Failure condition | Error text shown |
|---|---|---|---|
| `adminApi()` (`utils/adminApi.js`) | Catalogue, banners, promo cards, admin orders, dashboard, Home, Shop | `!response.ok \|\| result.success === false` | `result.message \|\| "Something went wrong"` |
| `request()` (`context/CartContext.jsx`) | All cart calls | `!response.ok \|\| data.success === false` | `data.message \|\| "Cart request failed"` |
| Inline `fetch` | Auth, order create, my-orders, order details | `!response.ok \|\| !data.success` (**`success` must be truthy**) | `data.message \|\| <per-call fallback>` |

Requirements that follow from this:
1. **Every response body must be valid JSON**, including errors (4xx/5xx), 404s and DELETE responses. All wrappers call `response.json()` **before** checking the status, so an empty body or HTML error page makes the user see a JSON parse error (e.g. "Unexpected token '<'…"). The only exception is `POST /api/auth/logout`, whose body is never read.
2. Successful responses should include **`"success": true`**. It's mandatory for auth, order-create, my-orders and order-details, and recommended everywhere else.
3. Errors should return a non-2xx status, **and/or** `"success": false`, **plus a human-readable `"message"`**. That string is shown verbatim in toasts or inline alerts.
4. Successful mutations may include `"message"`. It's displayed for cart add (Shop page) and order status update.

**Canonical error example**
```json
{ "success": false, "message": "Product is out of stock" }
```

#### 6.0.3 Tolerant list extraction (Dashboard only)

`Dashboard.getArray(result, keys)` returns the first array it finds, in this order: `result` itself, `result.data`, `result.data.data`, `result.data.orders`, `result.data.products`, `result.data.categories`, then `result[key]` for each key passed in (`["products","product"]`, `["categories","category"]`, `["orders","order"]`). **Other pages are stricter**, so the formats documented below are the ones to implement.

#### 6.0.4 Identifiers and common field conventions
- Every entity is identified by **`_id`** (a string). The UI uses it for React keys, URL params (`/my-orders/:id`, `?category=`), select values, and path params on update/delete.
- Images: an absolute URL, or a root-relative path beginning with `/` (§2.3).
- Dates (`createdAt`, `expectedDelivery`, `statusDates.*`): any string accepted by `new Date(...)`. **ISO-8601** is recommended.
- Money and quantity fields are read through `Number(...)`, so numbers or numeric strings both work. Numbers are recommended.
- Order `status` values are **case-sensitive**: `"Pending" | "Confirmed" | "Processing" | "Shipped" | "Delivered" | "Cancelled"`.
- `user.role` must be exactly `"admin"` for administrators. Any other value (e.g. `"user"`) means a customer.

---

### 6.1 Auth

#### 6.1.1 `GET /api/auth/me`
- **Trigger:** `AuthProvider` mount (every full page load).
- **Request:** no body, cookies only.
- **Response used:**
  ```json
  {
    "success": true,
    "user": {
      "_id": "665f...",
      "name": "Asha Kumar",
      "email": "asha@example.com",
      "phone": "9876543210",
      "role": "user",
      "address": "12 MG Road",
      "city": "Delhi",
      "pincode": "110001"
    }
  }
  ```
  Fields actually read: `success`, `user` (stored as is), `user.name`, `user.role`, `user.phone`, and optionally `user.address`, `user.city`, `user.pincode`. `_id` and `email` aren't read but are reasonable to include.
- **Not logged in:** any non-2xx status, or `success:false`, sets `user = null`. The body must still be JSON (otherwise the parse error is caught, which also gives `user = null`, so that case is harmless).
- **Errors:** not shown to the user (only logged).

#### 6.1.2 `POST /api/auth/register`
- **Trigger:** Register form submit.
- **Headers:** `Content-Type: application/json`.
- **Body:**
  ```json
  { "name": "Asha Kumar", "email": "asha@example.com", "phone": "9876543210", "password": "secret1" }
  ```
  `phone` may be `""`. All values are strings; name, email and phone are trimmed.
- **Success response (must also set the session cookie):**
  ```json
  { "success": true, "message": "Registered", "user": { "_id": "...", "name": "Asha Kumar", "role": "user", "phone": "9876543210" } }
  ```
  `user` becomes the logged-in user immediately.
- **Error:** `message` is shown in a toast. Fallback "Registration failed", then "Registration failed. Please try again.". A typical case is a duplicate email.

#### 6.1.3 `POST /api/auth/login`
- **Trigger:** Login form submit.
- **Headers:** `Content-Type: application/json`.
- **Body:** `{ "email": "asha@example.com", "password": "secret1" }` (email trimmed).
- **Success (must set the session cookie):**
  ```json
  { "success": true, "user": { "_id": "...", "name": "Asha Kumar", "role": "admin" } }
  ```
  `user.role` decides where the user lands (`"admin"` goes to `/admin`).
- **Error:** `message` is shown in the "Login Failed" box and a toast. Fallback "Login failed".

#### 6.1.4 `POST /api/auth/logout`
- **Trigger:** Header logout button.
- **Request:** no body, no `Content-Type`.
- **Response:** ignored entirely (any status or body). The backend should clear or invalidate the session cookie.

---

### 6.2 Cart (all require a logged-in user)

**Common cart response shape.** After every cart call except `clear`, the client reads `result.data?.items || result.cart?.items || []`, then normalises it:

```json
{
  "success": true,
  "message": "Product added to cart",
  "data": {
    "items": [
      {
        "product": {
          "_id": "prod1",
          "name": "Rose Jar Candle",
          "image": "/uploads/products/rose.jpg",
          "price": 499,
          "oldPrice": 699,
          "stock": 12,
          "description": "Hand-poured soy wax",
          "category": "cat1"
        },
        "quantity": 2,
        "selected": true
      }
    ]
  }
}
```

- `items[].product` **must be a populated product object** (not just an id). Items whose `product` is null or missing are dropped (e.g. a deleted product).
- Fields read from `product`: `_id`, `name`, `image`, `price`, `oldPrice`, `stock`, `description`, `category` (category is carried along but never displayed from the cart).
- `quantity` (defaults to 1 if missing). `selected` (anything other than literal `false` counts as selected).
- The alternative key `cart.items` is also accepted instead of `data.items`.
- The **product `_id` is the cart line identifier** in every cart call.

#### 6.2.1 `GET /api/cart`
- **Trigger:** `CartProvider` whenever `user` changes (once auth has loaded and the user is non-null); after an order is confirmed on `/whatsapp-confirm`. Not called when logged out (the cart is cleared locally).
- **Response:** the common cart shape (`message` not needed).
- **Errors:** logged, and the cart is set to `[]`. Nothing is shown to the user.

#### 6.2.2 `POST /api/cart/add`
- **Trigger:** "Add to Cart" on Home and Shop product cards.
- **Client pre-checks** (no request is sent): user not logged in → "Please login before adding products to cart."; `product.stock <= 0` → "This product is out of stock."
- **Headers:** `Content-Type: application/json`.
- **Body:** `{ "productId": "prod1", "quantity": 2 }`. `quantity` is a number from 1 to `stock`.
- **Expected semantics:** **add** `quantity` to the existing line (the button label changes to "Add More"), or create the line if missing. New lines should be `selected: true`. The server should reject a total quantity above stock with a `message`.
- **Response:** the common cart shape. `message` is shown in a toast and banner on Shop (fallback "Product added to cart").

#### 6.2.3 `PUT /api/cart/update`
- **Trigger:** Cart page − / + buttons.
- **Headers:** `Content-Type: application/json`.
- **Body:** `{ "productId": "prod1", "quantity": 3 }`. This **sets** the absolute quantity (always ≥ 1; the client calls remove instead of sending ≤ 0).
- **Response:** the common cart shape.
- **Errors:** not caught by the UI (an unhandled rejection). Nothing is shown.

#### 6.2.4 `DELETE /api/cart/remove/:productId`
- **Trigger:** Cart "Remove" button; `updateQuantity(…, ≤0)` (not reachable from the UI); after an order is confirmed (once per ordered product, errors swallowed).
- **Path param:** product `_id`.
- **Response:** the common cart shape. Should not fail hard if the item is already gone: either `success:true` with the current cart, or an error that the confirm flow will swallow.

#### 6.2.5 `PUT /api/cart/toggle` — *defined, not used by any screen*
- **Body:** `{ "productId": "prod1", "selected": false }`. **Response:** the common cart shape.

#### 6.2.6 `PUT /api/cart/select-all` — *defined, not used by any screen*
- **Body:** `{ "selected": true }`. **Response:** the common cart shape.

#### 6.2.7 `DELETE /api/cart/clear` — *defined, not used by any screen*
- **Response:** body only checked for errors. The local cart is set to `[]`.

---

### 6.3 Categories

#### 6.3.1 `GET /api/category/get-category` (public)
- **Triggers:** Home mount and Retry; Shop mount and Retry; Admin Dashboard; Admin Categories (mount, Refresh, after save); Admin Products (mount).
- **Must work for anonymous users** (Home and Shop call it while logged out).
- **Response:**
  ```json
  {
    "success": true,
    "data": [
      { "_id": "cat1", "name": "Scented Candles", "description": "Aromatic soy candles", "image": "/uploads/categories/scented.jpg" }
    ]
  }
  ```
  `data` must be an array (if it isn't, the UI treats the list as empty). Fields read: `_id`, `name`, `description`, `image`. Display order is the API order.

#### 6.3.2 `POST /api/category/create-category` (admin)
- **Trigger:** Admin Categories form submit (create).
- **Body:** `multipart/form-data`:

  | Field | Type | Notes |
  |---|---|---|
  | `name` | text | trimmed, non-empty |
  | `description` | text | trimmed, may be `""` |
  | `image` | file | JPEG/PNG/WebP, ≤ 5 MB (client-checked) |

- **Response:** `{ "success": true, "data": { "_id": "...", "name": "...", "description": "...", "image": "..." } }`. `data._id` is optional but, if present, the row is added straight away. The list is refetched afterwards in any case.

#### 6.3.3 `PUT /api/category/update-category/:id` (admin)
- **Body:** multipart `name`, `description`, and `image` **only when the admin picked a new file**. If there's no `image`, keep the existing image.
- **Response:** as for create. If `data._id` matches a row, that row is replaced.

#### 6.3.4 `DELETE /api/category/delete-category/:id` (admin)
- **Response:** `{ "success": true, "message": "..." }` (only checked for errors).

---

### 6.4 Products

#### 6.4.1 `GET /api/product/get-product` (public)
- **Triggers:** Home mount and Retry; Shop mount and Retry; Admin Dashboard; Admin Products (mount, Refresh, after save).
- **Must work for anonymous users.**
- **Response:**
  ```json
  {
    "success": true,
    "data": [
      {
        "_id": "prod1",
        "name": "Rose Jar Candle",
        "description": "Hand-poured soy wax",
        "price": 499,
        "oldPrice": 699,
        "stock": 12,
        "image": "/uploads/products/rose.jpg",
        "category": { "_id": "cat1", "name": "Scented Candles" },
        "createdAt": "2026-09-30T10:00:00.000Z"
      }
    ]
  }
  ```
  - `category` can be a **populated object `{ _id, name }`** (preferred) **or a plain id string**. Both are handled: when it's a string, the name is looked up in the category list.
  - `createdAt` is required for "Featured"/newest sorting and the Home "latest 8".
  - `oldPrice` is optional. A discount only shows when `oldPrice > price`.
  - `stock` ≤ 0 means out of stock (add-to-cart disabled).
  - All products are returned in one response. **There's no pagination**, and filtering and sorting happen on the client.

#### 6.4.2 `POST /api/product/create-product` (admin)
- **Body:** `multipart/form-data`. **All values arrive as strings:**

  | Field | Example | Notes |
  |---|---|---|
  | `name` | `"Rose Jar Candle"` | trimmed, non-empty |
  | `category` | `"cat1"` | category `_id` |
  | `price` | `"499"` | ≥ 1, as typed |
  | `oldPrice` | `"699"` or **`""`** | empty string when left blank. The backend must treat `""` as "no old price" |
  | `stock` | `"12"` | integer ≥ 0 |
  | `description` | `"..."` or `""` | trimmed |
  | `image` | file | JPEG/PNG/WebP, ≤ 5 MB. Required on create |

- **Response:** `{ "success": true, ... }`. The body isn't read beyond the error check, and the list is refetched.

#### 6.4.3 `PUT /api/product/update-product/:id` (admin)
- **Body:** same fields. `image` is sent only if a new file was chosen (keep the old one otherwise). `oldPrice: ""` should **clear** the old price.
- **Response:** `{ "success": true }`.

#### 6.4.4 `DELETE /api/product/delete-product/:id` (admin)
- **Response:** `{ "success": true }`.

---

### 6.5 Banners and Promo Cards

#### 6.5.1 `GET /api/banner/get-banner` (public, storefront)
- **Trigger:** Home mount (paired with promo cards in `Promise.all`).
- **Must work for anonymous users.** Returned **in display order** (the client doesn't sort). If the backend supports active/inactive, only active banners should come back here.
- **Response:**
  ```json
  {
    "success": true,
    "data": [
      { "_id": "ban1", "image": "/uploads/banners/b1.jpg", "title": "Luxury Scented Candles", "subtitle": "Beautiful handmade candles", "buttonText": "Shop Now", "buttonLink": "/shop", "order": 0 }
    ]
  }
  ```
  Fields read: `_id` (or `id`), `image`, `title`, `subtitle`, `buttonText`, `buttonLink`. `banners[0]` is reused for the mid-page promo banner.

#### 6.5.2 `GET /api/banner/get-all-banner` (admin)
- **Trigger:** Admin Banners mount, after create, after delete.
- **Response:** `{ "success": true, "data": [ { "_id", "image", "title", "subtitle", "buttonText", "order" } ] }`.

#### 6.5.3 `POST /api/banner/create-banner` (admin)
- **Body:** `multipart/form-data`:

  | Field | Type | Example |
  |---|---|---|
  | `title` | text | `"Luxury Scented Candles"` (non-empty) |
  | `subtitle` | text | may be `""` |
  | `buttonText` | text | default `"Shop Now"`, may be `""` |
  | `buttonLink` | text | default `"/shop"`. Internal paths start with `/`; anything else is treated as an external URL |
  | `order` | text (numeric) | `"0"` |
  | `image` | file | any `image/*` (no client size or type limit) |

- **Response:** `{ "success": true }`.

#### 6.5.4 `DELETE /api/banner/delete-banner/:id` (admin)
- **Response:** `{ "success": true }`.

#### 6.5.5 `GET /api/promo-card/get-promo-card` (public, storefront)
- **Trigger:** Home mount.
- **Must work for anonymous users**, and return cards in display order.
- **Response:**
  ```json
  {
    "success": true,
    "data": [
      { "_id": "pc1", "image": "/uploads/promo/p1.jpg", "title": "Gift Sets", "subtitle": "Bring fragrance into your home", "buttonText": "Shop Now", "buttonLink": "/shop?category=cat1", "background": "#08aaa6", "order": 0 }
    ]
  }
  ```
  Fields read: `_id` (or `id`), `image`, `title`, `subtitle`, `buttonText`, `buttonLink`, `background` (a CSS colour).

#### 6.5.6 `GET /api/promo-card/get-all-promo-card` (admin)
- **Response:** `{ "success": true, "data": [ { "_id", "image", "title", "subtitle", "buttonText", "background" } ] }`.

#### 6.5.7 `POST /api/promo-card/create-promo-card` (admin)
- **Body:** `multipart/form-data`: `title`, `subtitle`, `buttonText`, `buttonLink`, `background` (e.g. `"#08aaa6"`), `order` (numeric string), `image` (file).
- **Response:** `{ "success": true }`.

#### 6.5.8 `DELETE /api/promo-card/delete-promo-card/:id` (admin)
- **Response:** `{ "success": true }`.

---

### 6.6 Orders

**Canonical order object** (the union of every field any screen reads):

```json
{
  "_id": "ord1",
  "orderId": "AKRF-20261002-4821",
  "user": { "_id": "u1", "name": "Asha Kumar", "phone": "9876543210" },
  "customer": {
    "name": "Asha Kumar",
    "mobile": "9876543210",
    "address": "12 MG Road",
    "city": "Delhi",
    "pincode": "110001",
    "message": "Please gift wrap"
  },
  "items": [
    { "_id": "li1", "productId": "prod1", "name": "Rose Jar Candle", "image": "/uploads/products/rose.jpg", "price": 499, "quantity": 2, "total": 998 }
  ],
  "itemsTotal": 998,
  "shipping": 0,
  "shippingStatus": "PAYABLE_SEPARATELY",
  "grandTotal": 998,
  "paymentMethod": "WhatsApp Order",
  "status": "Pending",
  "statusDates": {
    "Pending": "2026-10-02T09:15:00.000Z",
    "Confirmed": null,
    "Processing": null,
    "Shipped": null,
    "Delivered": null,
    "Cancelled": null
  },
  "expectedDelivery": "2026-10-09T00:00:00.000Z",
  "createdAt": "2026-10-02T09:15:00.000Z"
}
```

Notes for the backend:
- **`orderId`** is a human-readable id **generated by the backend**. The frontend shows it but never sends it. The format is free (it's shown as a string).
- **`status`** starts as `"Pending"`. **`statusDates[<status>]`** should hold the timestamp when the order entered each status. The admin UI and customer tracking show these. On creation, set `statusDates.Pending` (the UI falls back to `createdAt`).
- **`expectedDelivery`** is computed by the backend (the frontend never sends it). It's shown on My Orders, Order Details and Admin Orders when present. The rule isn't defined anywhere in the frontend (see §10).
- **`user`** is optional. It's only a fallback in the Dashboard "Recent Orders" table.

#### 6.6.1 `POST /api/order/create`
- **Trigger:** `/whatsapp-confirm` → "I Have Sent WhatsApp Order".
- **Headers:** `Content-Type: application/json`.
- **Body** (built from `localStorage.pendingWhatsAppOrder`):
  ```json
  {
    "customer": {
      "name": "Asha Kumar",
      "mobile": "9876543210",
      "address": "12 MG Road",
      "city": "Delhi",
      "pincode": "110001",
      "message": ""
    },
    "items": [
      { "productId": "prod1", "name": "Rose Jar Candle", "image": "/uploads/products/rose.jpg", "price": 499, "quantity": 2, "total": 998 }
    ],
    "itemsTotal": 998,
    "shipping": 0,
    "shippingStatus": "PAYABLE_SEPARATELY",
    "grandTotal": 998,
    "paymentMethod": "WhatsApp Order"
  }
  ```
  - Types: all `customer.*` values are trimmed strings (`message` may be `""`). `items[].price`, `quantity` and `total` are numbers. `itemsTotal`, `shipping` and `grandTotal` are numbers. `shippingStatus` is `"FREE"` or `"PAYABLE_SEPARATELY"`. `paymentMethod` is always `"WhatsApp Order"`.
  - `items[].image` is the image string exactly as received from the cart (relative path or URL).
  - **All prices and totals are computed on the client.** The backend should re-validate them against stored product prices and stock (see §10).
  - Expected server behaviour (not enforced by the client): attach the order to the session user; generate `orderId`; set `status: "Pending"` and `statusDates.Pending`; optionally set `expectedDelivery`; optionally reduce stock; **remove the ordered products from the user's cart** (the code comment says "Backend should already remove the ordered products from cart"; the client also removes them).
- **Success response:** `{ "success": true, "message": "Order placed", "order": { ... } }`. **Only `success` is read.** The order object is optional.
- **Error:** toast `data.message || "Failed to create order."`. The pending order stays, so the user can retry.

#### 6.6.2 `GET /api/order/my-orders`
- **Trigger:** `/my-orders` mount once the user has loaded.
- **Response (key `orders`, not `data`):**
  ```json
  { "success": true, "orders": [ { "...canonical order fields..." } ] }
  ```
  Must contain **only the current user's orders**, ideally newest first (the client doesn't sort). Fields read: `_id`, `orderId`, `status`, `createdAt`, `expectedDelivery`, `statusDates`, `items[].name/image/quantity/price/total`, `grandTotal`.
- **Error:** toast `data.message || "Failed to load orders"`.

#### 6.6.3 `GET /api/order/my-orders/:id`
- **Trigger:** `/my-orders/:id` mount. `:id` is the order **`_id`**.
- **Response (key `order`):**
  ```json
  { "success": true, "order": { "...canonical order fields..." } }
  ```
  Fields read: `orderId`, `status`, `statusDates.*`, `createdAt`, `expectedDelivery`, `items[]._id/name/image/quantity/price/total`, `customer.name/mobile/address/city/pincode`, `itemsTotal`, `shipping`, `shippingStatus`, `grandTotal`.
- Must return an error (with `message`) when the order doesn't exist **or belongs to another user**.
- **Error:** toast `data.message || "Unable to get order"`, then redirect to `/my-orders`.

#### 6.6.4 `GET /api/order/all` (admin)
- **Triggers:** Admin Orders (mount, Refresh, after a status update); Admin Dashboard.
- **Response:** Admin Orders reads `result.orders || result.data`, and Dashboard accepts either. Recommended:
  ```json
  { "success": true, "orders": [ { "...canonical order fields..." } ] }
  ```
  Return all orders from all users, ideally newest first (the Orders table doesn't sort; the Dashboard does). Fields read: everything in the canonical object, including `paymentMethod`, `customer.message`, and `user.name`/`user.phone` (Dashboard fallback).

#### 6.6.5 `PUT /api/order/status/:id` (admin)
- **Trigger:** changing a status `<select>` in the Admin Orders table or modal. `:id` is the order **`_id`**.
- **Headers:** `Content-Type: application/json`.
- **Body:** `{ "status": "Shipped" }`, one of the 6 status strings.
- **Expected server behaviour:** set `status`, and stamp `statusDates[status] = now`. Keep earlier dates so the timeline can show them. Optionally update `expectedDelivery`. The client allows **any** transition, including going backwards.
- **Response:**
  ```json
  { "success": true, "message": "Order status updated", "order": { "...full canonical order..." } }
  ```
  `message` is shown in a toast. `order` (or `data.order`) replaces the open modal's content, so it **must be the full order object** (the same shape as in `/api/order/all`). If it's missing, the modal keeps showing stale data until it's reopened.
- **Error:** toast `err.message || "Unable to update order status"`.

---

### 6.7 Consolidated endpoint summary

| # | Method | Path | Auth expected | Request body | Success keys read | Triggered from | Used? |
|---|---|---|---|---|---|---|---|
| 1 | GET | `/api/auth/me` | Session cookie (optional) | — | `success`, `user` | AuthProvider mount | Yes |
| 2 | POST | `/api/auth/register` | Public; **sets cookie** | JSON `{name,email,phone,password}` | `success`, `user`, `message` | Register | Yes |
| 3 | POST | `/api/auth/login` | Public; **sets cookie** | JSON `{email,password}` | `success`, `user`, `message` | Login | Yes |
| 4 | POST | `/api/auth/logout` | Session; **clears cookie** | — | (none) | Header logout | Yes |
| 5 | GET | `/api/cart` | User | — | `data.items` / `cart.items` | CartProvider, WhatsAppConfirm | Yes |
| 6 | POST | `/api/cart/add` | User | JSON `{productId,quantity}` | `data.items`, `message` | Home, Shop | Yes |
| 7 | PUT | `/api/cart/update` | User | JSON `{productId,quantity}` | `data.items` | Cart −/+ | Yes |
| 8 | DELETE | `/api/cart/remove/:productId` | User | — | `data.items` | Cart Remove, WhatsAppConfirm | Yes |
| 9 | PUT | `/api/cart/toggle` | User | JSON `{productId,selected}` | `data.items` | (CartContext only) | **No UI** |
| 10 | PUT | `/api/cart/select-all` | User | JSON `{selected}` | `data.items` | (CartContext only) | **No UI** |
| 11 | DELETE | `/api/cart/clear` | User | — | — | (CartContext only) | **No UI** |
| 12 | GET | `/api/category/get-category` | **Public** | — | `data[]` | Home, Shop, Admin Dashboard/Categories/Products | Yes |
| 13 | POST | `/api/category/create-category` | Admin | multipart `name,description,image` | `data` (optional) | Admin Categories | Yes |
| 14 | PUT | `/api/category/update-category/:id` | Admin | multipart `name,description[,image]` | `data` (optional) | Admin Categories | Yes |
| 15 | DELETE | `/api/category/delete-category/:id` | Admin | — | — | Admin Categories | Yes |
| 16 | GET | `/api/product/get-product` | **Public** | — | `data[]` | Home, Shop, Admin Dashboard/Products | Yes |
| 17 | POST | `/api/product/create-product` | Admin | multipart `name,category,price,oldPrice,stock,description,image` | — | Admin Products | Yes |
| 18 | PUT | `/api/product/update-product/:id` | Admin | multipart (same, image optional) | — | Admin Products | Yes |
| 19 | DELETE | `/api/product/delete-product/:id` | Admin | — | — | Admin Products | Yes |
| 20 | GET | `/api/banner/get-banner` | **Public** | — | `data[]` | Home | Yes |
| 21 | GET | `/api/banner/get-all-banner` | Admin | — | `data[]` | Admin Banners | Yes |
| 22 | POST | `/api/banner/create-banner` | Admin | multipart `title,subtitle,buttonText,buttonLink,order,image` | — | Admin Banners | Yes |
| 23 | DELETE | `/api/banner/delete-banner/:id` | Admin | — | — | Admin Banners | Yes |
| 24 | GET | `/api/promo-card/get-promo-card` | **Public** | — | `data[]` | Home | Yes |
| 25 | GET | `/api/promo-card/get-all-promo-card` | Admin | — | `data[]` | Admin Promo Cards | Yes |
| 26 | POST | `/api/promo-card/create-promo-card` | Admin | multipart `title,subtitle,buttonText,buttonLink,background,order,image` | — | Admin Promo Cards | Yes |
| 27 | DELETE | `/api/promo-card/delete-promo-card/:id` | Admin | — | — | Admin Promo Cards | Yes |
| 28 | POST | `/api/order/create` | User | JSON order payload (§6.6.1) | `success`, `message` | WhatsAppConfirm | Yes |
| 29 | GET | `/api/order/my-orders` | User | — | `orders[]` | My Orders | Yes |
| 30 | GET | `/api/order/my-orders/:id` | User (owner) | — | `order` | Order Details | Yes |
| 31 | GET | `/api/order/all` | Admin | — | `orders[]` (or `data[]`) | Admin Orders, Dashboard | Yes |
| 32 | PUT | `/api/order/status/:id` | Admin | JSON `{status}` | `message`, `order` (or `data.order`) | Admin Orders | Yes |

**Static file serving:** the backend must also serve uploaded images at `BASE_URL + <relative image path>` (§2.3). This isn't an API call, but the UI depends on it.

---

## 7. State Management

There's no Redux, Zustand or React Query. Global state lives in two React contexts. Everything else is component-local `useState`.

| Store | File | Holds | Exposed API | Persistence |
|---|---|---|---|---|
| **AuthContext** | `src/context/AuthContext.jsx` | `user` (object or null), `loading` (true until `/me` returns) | `user`, `loading`, `register(formData)`, `login(email, password)`, `logout()`, `getCurrentUser()`, `isLoggedIn` (= `Boolean(user)`) | **Not persisted in JS.** Rebuilt from `GET /api/auth/me` on every page load, using the session cookie. |
| **CartContext** | `src/context/CartContext.jsx` | `cart` (normalised items `{_id,name,image,price,oldPrice,stock,description,category,quantity,selected}`), `loading` | `cart`, `loading`, `cartCount` (Σ qty, all items), `selectedItems`, `selectedQuantity` (Σ qty, selected), `subtotal` (Σ price×qty, selected), `fetchCart`, `addToCart`, `updateQuantity`, `removeFromCart`, `toggleSelected`, `selectAll`, `clearCart` | **Server-side.** Re-fetched from `GET /api/cart` whenever `user` changes. Emptied locally on logout. |
| **localStorage `pendingWhatsAppOrder`** | written by `Cart.jsx`, read and cleared by `WhatsAppConfirm.jsx` | JSON snapshot of the order being placed (customer, items, totals, shippingStatus) | — | **Persists across reloads and sessions** until the order is confirmed, or the data is found invalid. It isn't tied to a user. |

Provider nesting: `BrowserRouter > ScrollToTop + Toaster + AuthProvider > CartProvider > Routes`.

Other notable local state: the Shop wishlist (in memory, lost on unmount), Shop search, sort and mobile-drawer state, per-card quantity steppers, admin form state, and admin modal state. The URL query (`?category`, `?search`, `?redirect`) also acts as state.

---

## 8. Third-Party Integrations in the UI

| Integration | What it does | Data exchanged with the backend |
|---|---|---|
| **WhatsApp (click-to-chat deep links)** | Order placement (`wa.me`), resending an order (`api.whatsapp.com/send`), contact form (`wa.me`), footer chat link. A pre-filled text is passed in the `text` query parameter. | **None.** Messages go straight from the user's WhatsApp to the business number `919288245292`. The backend only gets the order later, through `POST /api/order/create`, when the user confirms. |
| **YouTube embed** | Autoplaying, muted, looping candle video on Home (video id `dJJCayBThvY`, first 60 s). | None. |
| **Instagram / Facebook** | Plain outbound links (footer and contact page). | None. |
| **mailto: / tel:** | Email and phone links in the footer and contact page. The footer newsletter `mailto:` handler exists, but its form is commented out. | None. |
| **Google Maps** | **Not integrated.** The Contact page shows the placeholder text "Add your business Google Maps embed here". No key. | None. |
| **Payments** | **None.** No payment gateway; orders are WhatsApp-based and delivery is "paid separately". | — |
| **Analytics / tracking** | **None.** | — |
| **react-hot-toast** | In-app toast notifications (top-center, 3 s). | None. |
| **lucide-react / react-icons** | Icon libraries. | None. |

---

## 9. Functional Requirements List

### 9.1 Global layout and navigation

- **FR-UI-001** The system shall render the Header and Footer on every non-admin route (`/`, `/shop`, `/about`, `/contact`, `/cart`, `/login`, `/register`, `/my-orders`, `/my-orders/:id`, `/whatsapp-confirm`), and render neither on `/admin/*` routes.
- **FR-UI-002** The system shall scroll the window to the top whenever the route pathname changes.
- **FR-UI-003** The system shall show toast notifications at the top-centre of the screen for 3 seconds.
- **FR-UI-004** The system shall highlight the active navigation link (HOME matches `/` exactly).
- **FR-UI-005** The system shall show, in the header cart badge, the sum of quantities of all cart items, hide the badge when the sum is 0, and display "99+" when it exceeds 99.
- **FR-UI-006** The system shall, when the header search is submitted with a non-empty term, navigate to `/shop?search=<url-encoded trimmed term>`, and navigate to `/shop` when the term is empty.
- **FR-UI-007** The system shall show a "Login" link when no user is logged in, and "My Orders", the user's name and a logout control when a user is logged in.
- **FR-UI-008** The system shall show the admin dashboard link(s) in the header only when `user.role === "admin"`.
- **FR-UI-009** The system shall provide a mobile menu (below the `md` breakpoint) containing the nav links and the same auth-dependent actions as the desktop header.

### 9.2 Authentication

- **FR-UI-010** The system shall call `GET /api/auth/me` with credentials once on app load and treat the user as logged in only if the response is 2xx and `success` is truthy.
- **FR-UI-011** The system shall send every API request with `credentials: "include"` and shall not send an `Authorization` header.
- **FR-UI-012** The system shall reject a login submission with an empty (trimmed) email or empty password and show "Please enter email and password" inline and as a toast.
- **FR-UI-013** The system shall send `POST /api/auth/login` with JSON `{email, password}` (email trimmed).
- **FR-UI-014** The system shall, on login failure, display the response `message` (fallback "Login failed") in a "Login Failed" alert and a toast.
- **FR-UI-015** The system shall, on login success, show "Login successful!" and navigate to `/admin` if `user.role === "admin"`, otherwise to the `redirect` query parameter if present, otherwise to `/`.
- **FR-UI-016** The system shall clear the login error message when the user edits the email or password.
- **FR-UI-017** The system shall show "Password must be at least 6 characters" while a registration password of 1–5 characters is typed, and "Passwords do not match" while the confirmation differs from the password.
- **FR-UI-018** The system shall block registration and show "Please fill all required fields" when name, email, password or confirm password is empty.
- **FR-UI-019** The system shall send `POST /api/auth/register` with JSON `{name, email, phone, password}` (name, email and phone trimmed) and shall not send `confirmPassword`.
- **FR-UI-020** The system shall, on registration success, treat the returned `user` as logged in, show "Account created successfully!" and navigate to `/`.
- **FR-UI-021** The system shall, on registration failure, show the response `message` (fallback "Registration failed") as a toast.
- **FR-UI-022** The system shall, on logout, call `POST /api/auth/logout`, clear the local user regardless of the response, show "Logout successful" and navigate to `/`.
- **FR-UI-023** The system shall disable the login, register and logout buttons while their requests are in flight and show "Logging in...", "Creating account..." and "Logging out..." (mobile) respectively.

### 9.3 Route protection

- **FR-UI-024** The system shall show "Checking admin access..." on `/admin/*` while the session check is pending.
- **FR-UI-025** The system shall redirect an unauthenticated visitor of `/admin/*` to `/login`.
- **FR-UI-026** The system shall redirect an authenticated non-admin visitor of `/admin/*` to `/`.
- **FR-UI-027** The system shall redirect an unauthenticated visitor of `/my-orders` to `/login?redirect=%2Fmy-orders` after the session check completes.
- **FR-UI-028** The system shall redirect an unauthenticated visitor of `/whatsapp-confirm` to `/login?redirect=%2Fwhatsapp-confirm`.
- **FR-UI-029** The system shall show a "Please Login" panel (with Login and Create Account actions) on `/cart` when no user is logged in, where Login navigates to `/login?redirect=%2Fcart`.

### 9.4 Home

- **FR-UI-030** The system shall load categories, products, storefront banners and storefront promo cards from their public endpoints when the Home page mounts.
- **FR-UI-031** The system shall display banners as a slider in API order, auto-advancing every 4 seconds when there is more than one banner, with previous/next arrows and one dot per banner.
- **FR-UI-032** The system shall show "No banners available" when the banner list is empty.
- **FR-UI-033** The system shall show a banner's CTA button only when the banner has a title, labelled `buttonText` or "Shop Now".
- **FR-UI-034** The system shall, when a banner or promo-card CTA is activated, navigate in-app if `buttonLink` starts with "/", load the URL in the window if `buttonLink` is another non-empty value, and navigate to `/shop` otherwise.
- **FR-UI-035** The system shall render each promo card with its `background` colour (default `#08aaa6`), image, title, subtitle and button text (default "Shop Now").
- **FR-UI-036** The system shall show category tiles and navigate to `/shop?category=<_id>` when a tile is clicked.
- **FR-UI-037** The system shall show the 8 most recently created products (by `createdAt` descending) on Home.
- **FR-UI-038** The system shall show loading skeletons, an error message with a Retry button, or an empty message ("No categories available yet." / "No products available yet.") for the Home category and product sections.
- **FR-UI-039** The system shall show the first banner's image as a clickable mid-page promo banner when at least one banner exists.
- **FR-UI-040** The system shall show a toast and navigate to `/login` after 1 second when a guest clicks Add to Cart on Home.

### 9.5 Product display (Home and Shop cards)

- **FR-UI-041** The system shall format prices as "₹" followed by the `en-IN` formatted amount with at most 2 decimals.
- **FR-UI-042** The system shall show a discount badge with `round((oldPrice − price) / oldPrice × 100)` percent only when `oldPrice > price`, and show `oldPrice` struck through in that case.
- **FR-UI-043** The system shall show "{stock} In Stock" when stock > 0, and "Out of Stock" with a Sold Out indicator and a disabled Add to Cart button when stock ≤ 0.
- **FR-UI-044** The system shall let the user choose a quantity between 1 and the product's stock before adding to cart.

### 9.6 Shop

- **FR-UI-045** The system shall load all categories and all products on Shop mount and filter and sort them on the client.
- **FR-UI-046** The system shall filter products by the `category` query parameter (matching `product.category._id` or `product.category`), showing all products when it is absent.
- **FR-UI-047** The system shall set or remove the `category` query parameter when a category or "All Products" is selected in the sidebar, and close the mobile drawer.
- **FR-UI-048** The system shall show, per category, the number of loaded products in that category, and the total for "All Products".
- **FR-UI-049** The system shall initialise and synchronise the search box from the `search` query parameter.
- **FR-UI-050** The system shall filter products case-insensitively whose name, category name or description contains the search text.
- **FR-UI-051** The system shall sort products by newest `createdAt` ("Featured"), ascending price, descending price, or name A–Z according to the sort selection.
- **FR-UI-052** The system shall display the selected category's name as the heading (or "All Candles") and "{n} products found".
- **FR-UI-053** The system shall show "No Candles Found" with a "View All Candles" action that clears the search, sort, category and search query parameters when no product matches.
- **FR-UI-054** The system shall show "Please login first to add products to cart." (status banner and toast) when a guest clicks Add to Cart on Shop.
- **FR-UI-055** The system shall show the server's `message` (fallback "Product added to cart") on successful add-to-cart on Shop and reset that card's quantity to 1.
- **FR-UI-056** The system shall let the user toggle a wishlist heart per product, kept only in memory for the current page visit.

### 9.7 Cart

- **FR-UI-057** The system shall fetch the cart from `GET /api/cart` whenever the logged-in user changes and empty the local cart when no user is logged in.
- **FR-UI-058** The system shall drop cart lines whose `product` is missing and use the product's `_id` as the line id.
- **FR-UI-059** The system shall refuse to add an out-of-stock product with "This product is out of stock." without calling the API.
- **FR-UI-060** The system shall send `POST /api/cart/add` with `{productId, quantity}` and replace the local cart with the returned items.
- **FR-UI-061** The system shall show "Your Cart Is Empty" with a link to `/shop` when the logged-in user's cart has no items.
- **FR-UI-062** The system shall list every cart item with image, name, unit price and item total (price × quantity).
- **FR-UI-063** The system shall call `PUT /api/cart/update` with the new absolute quantity when − or + is pressed, disabling − at quantity 1 and + when quantity ≥ stock (if stock > 0).
- **FR-UI-064** The system shall call `DELETE /api/cart/remove/:productId` when Remove is pressed.
- **FR-UI-065** The system shall compute Items Total as the sum of price × quantity over items whose `selected` is not `false`.
- **FR-UI-066** The system shall show delivery as "FREE" when Items Total ≥ ₹1099, and as "Pay Separately" with the amount still needed for free delivery otherwise.
- **FR-UI-067** The system shall set Grand Total equal to Items Total (shipping charge 0).
- **FR-UI-068** The system shall pre-fill delivery name, mobile, address, city and pincode from the user's `name`, `phone`, `address`, `city` and `pincode` without overwriting values already typed.
- **FR-UI-069** The system shall restrict the mobile input to at most 10 digits and the pincode input to at most 6 digits by stripping non-digit characters.
- **FR-UI-070** The system shall validate the delivery form on order placement with the exact messages listed in §5.5, highlight invalid fields, and scroll to the form when invalid.
- **FR-UI-071** The system shall accept only mobile numbers matching `^[6-9]\d{9}$` and pincodes matching `^\d{6}$`.
- **FR-UI-072** The system shall show "Please select at least one product." and not proceed when no cart item is selected.

### 9.8 WhatsApp checkout

- **FR-UI-073** The system shall, on a valid "Place Order on WhatsApp", store the pending order (customer, items, itemsTotal, shipping, shippingStatus, grandTotal) in `localStorage` under `pendingWhatsAppOrder` without calling the backend.
- **FR-UI-074** The system shall set `shippingStatus` to "FREE" when Items Total ≥ 1099, otherwise to "PAYABLE_SEPARATELY".
- **FR-UI-075** The system shall open `https://wa.me/919288245292` in a new tab with a pre-filled message containing an `AKRF-YYYYMMDD-NNNN` reference, customer details, item lines, the payment summary, the delivery-charge note and the optional customer note.
- **FR-UI-076** The system shall navigate from `/cart` to `/whatsapp-confirm` when the page becomes visible again while a pending order exists.
- **FR-UI-077** The system shall redirect from `/whatsapp-confirm` to `/cart` with an explanatory toast when the pending order is missing, unparsable or has no items, and remove invalid data.
- **FR-UI-078** The system shall display the pending order's customer details, items and totals on `/whatsapp-confirm`.
- **FR-UI-079** The system shall reopen WhatsApp with the order message when "Send WhatsApp Again" is pressed.
- **FR-UI-080** The system shall send `POST /api/order/create` with the payload in §6.6.1 (including `paymentMethod: "WhatsApp Order"` and `items[].productId/name/image/price/quantity/total`) when "I Have Sent WhatsApp Order" is pressed.
- **FR-UI-081** The system shall, after successful order creation, remove each ordered product from the cart (ignoring removal errors), re-fetch the cart, delete the pending order from localStorage, show "Order placed successfully!" and navigate to `/my-orders` (replace).
- **FR-UI-082** The system shall, on order-creation failure, show the server `message` (fallback "Failed to create order.") and keep the pending order.
- **FR-UI-083** The system shall disable all confirmation-page buttons and show "Placing Order..." while the order is being created.

### 9.9 My Orders and Order Details

- **FR-UI-084** The system shall load the user's orders from `GET /api/order/my-orders` and read them from the `orders` key.
- **FR-UI-085** The system shall show "No Orders Yet" with a "Start Shopping" link when the user has no orders.
- **FR-UI-086** The system shall show for each order its `orderId`, a colour-coded status, order date, expected delivery (unless Cancelled), the current-status date, up to 3 items with "+N more product(s)", and the grand total.
- **FR-UI-087** The system shall label the current-status date "Order Placed" for Pending and "{status} On" otherwise, using `statusDates[status]` (or `createdAt` for Pending), or "Not available".
- **FR-UI-088** The system shall link each order card to `/my-orders/{_id}`.
- **FR-UI-089** The system shall load one order from `GET /api/order/my-orders/:id` and read it from the `order` key, redirecting to `/my-orders` with an error toast on failure.
- **FR-UI-090** The system shall show a 5-step tracking timeline (Order Placed, Confirmed, Processing, Shipped, Delivered) marking steps before the current status as completed and the current step as active, with each step's `statusDates` timestamp or "Pending".
- **FR-UI-091** The system shall show a 3-step timeline (Order Placed, Confirmed, Cancelled) and an "Order Cancelled" notice when the status is Cancelled.
- **FR-UI-092** The system shall show the order's delivery details (name, mobile, address, city, pincode), item list and summary, with shipping shown as "FREE", "PAYABLE SEPARATELY" or the numeric shipping amount.
- **FR-UI-093** The system shall format dates as `en-IN` "DD Mon YYYY" (date) or "DD Mon YYYY, hh:mm" (date-time), and show "-" for missing or invalid dates.

### 9.10 Contact and static pages

- **FR-UI-094** The system shall require Full Name, Email, Subject and Message in the contact form (HTML validation) and open WhatsApp `wa.me/919288245292` with a formatted contact message on submit, then clear the form.
- **FR-UI-095** The system shall show the static business details (phone, email, address, working hours) and social links on the Contact page.
- **FR-UI-096** The system shall show the About page's static story, mission and four feature cards, with links to `/shop`.

### 9.11 Admin layout and dashboard

- **FR-UI-097** The system shall show an admin sidebar with Dashboard, Categories, Products, Orders, Banners, Promotional Cards and "Back to Website", collapsible on mobile.
- **FR-UI-098** The system shall load products, categories and all orders in parallel on the dashboard and show an error message (clearing all figures) if any request fails.
- **FR-UI-099** The system shall display counts of products, categories and orders, and Delivered Revenue as the sum of `grandTotal` over orders with status "Delivered".
- **FR-UI-100** The system shall display the number of orders in each of the six statuses.
- **FR-UI-101** The system shall list the 5 most recent orders by `createdAt` with order id, customer name and mobile, total item quantity, amount, status and date.
- **FR-UI-102** The system shall re-load dashboard data when Refresh is pressed, showing "Refreshing..." meanwhile.

### 9.12 Admin categories

- **FR-UI-103** The system shall list categories with image, name and description, and support client-side search on name and description.
- **FR-UI-104** The system shall accept only JPEG, PNG or WebP category images of at most 5 MB, showing "Only JPG, PNG and WebP images are allowed" or "Image must be under 5 MB" otherwise.
- **FR-UI-105** The system shall require a category name ("Category name is required") and, on create, an image ("Please upload a category image").
- **FR-UI-106** The system shall send category create (POST) and update (PUT) as multipart with `name`, `description` and, when chosen, `image`.
- **FR-UI-107** The system shall show "Category created successfully" / "Category updated successfully" and refresh the list after saving.
- **FR-UI-108** The system shall ask for confirmation before deleting a category, call the delete endpoint, remove the row and show "Category deleted successfully".

### 9.13 Admin products

- **FR-UI-109** The system shall list products with image, name, category name, price (with old price), and stock ("Out of stock" when ≤ 0), searchable by name and category.
- **FR-UI-110** The system shall validate the product form in this order: name required, category required, image required on create, price ≥ 1, stock an integer ≥ 0, old price (if given) ≥ price, using the messages in §5.12.
- **FR-UI-111** The system shall send product create/update as multipart with `name`, `category`, `price`, `oldPrice`, `stock`, `description` and, when chosen, `image`.
- **FR-UI-112** The system shall pre-fill the edit form from the product, using `category._id` when category is populated.
- **FR-UI-113** The system shall ask for confirmation before deleting a product and show "Product deleted successfully" after deletion.

### 9.14 Admin banners and promo cards

- **FR-UI-114** The system shall require a banner title ("Please enter banner title") and image ("Please select banner image") and send `title`, `subtitle`, `buttonText`, `buttonLink`, `order` and `image` as multipart to the create-banner endpoint.
- **FR-UI-115** The system shall default the banner and promo-card forms to button text "Shop Now", button link "/shop" and order 0, and reset to these defaults after a successful upload.
- **FR-UI-116** The system shall list all banners (admin endpoint) with image, title, subtitle, button text and order, each with a confirmed Delete action.
- **FR-UI-117** The system shall require a promo-card title ("Please enter title") and image ("Please select image") and send `title`, `subtitle`, `buttonText`, `buttonLink`, `background`, `order` and `image` as multipart.
- **FR-UI-118** The system shall offer a colour picker for the promo-card background (default `#08aaa6`) and render each listed card on its background colour.
- **FR-UI-119** The system shall show "Banner uploaded successfully", "Banner deleted successfully", "Promotional card uploaded" and "Promotional card deleted" toasts after the respective successful actions.

### 9.15 Admin orders

- **FR-UI-120** The system shall load all orders from `GET /api/order/all`, reading `orders` or `data`.
- **FR-UI-121** The system shall show totals for all, Pending, Processing, Delivered and Cancelled orders.
- **FR-UI-122** The system shall filter orders client-side by text matching customer name, customer mobile or `orderId`, and by an exact status.
- **FR-UI-123** The system shall send `PUT /api/order/status/:_id` with `{status}` immediately when an admin changes an order's status select, disable all status selects during the request, toast the server `message` (fallback "Order status updated"), and refresh the list.
- **FR-UI-124** The system shall replace the open order modal's data with the `order` returned by the status update when present.
- **FR-UI-125** The system shall show, in the order modal, the order and expected-delivery dates, customer details, a status selector, a 6-entry timeline with `statusDates` timestamps (or "Not available" / "Not {status} yet"), the product lines, totals and the customer note.

### 9.16 Error handling (cross-cutting)

- **FR-UI-126** The system shall display the `message` field of any failed API response to the user, falling back to a screen-specific default message when absent.
- **FR-UI-127** The system shall treat a response as failed when the HTTP status is not 2xx or when `success` is `false` (and, for auth and order-customer endpoints, when `success` is not truthy).
- **FR-UI-128** The system shall resolve relative image paths by prefixing the API base URL and use absolute (`http…`) or `data:` URLs unchanged.

---

## 10. Known Issues / Ambiguities

### 10.1 Broken or incorrect flows

| ID | Issue | Location | Impact |
|---|---|---|---|
| K-01 | **API base URL hard-coded in 7 files and inconsistent.** `adminApi.js` has an uncommitted change to `http://localhost:5000` (the committed value is `https://devakroyalflames.in`). All other files hard-code `localhost:5000`. There's no env-variable support. | §2.2 | A production build would send auth, cart and orders to `localhost`. With `vite --host 0.0.0.0`, opening the site from another device on the LAN sends API calls to *that device's* localhost. |
| K-02 | **Home "Add to Cart" ignores the async result.** `handleAddToCart` calls `addToCart(...)` without `await` and reads `result.success` from a Promise. | `Home.jsx:668-685` | The request succeeds, but the user always sees the error toast "Unable to add product to cart". The card shows an empty or undefined message, and server errors become unhandled rejections. |
| K-03 | `AddToCartButton` has the same synchronous bug, but it's never imported. | `components/AddToCartButton.jsx:18-23` | Dead code. |
| K-04 | Cart quantity and remove actions have no `try/catch`, loading state or disabling. | `Cart.jsx:897-950` | Server errors (e.g. "exceeds stock") are silently lost as unhandled rejections, and rapid clicks can send overlapping requests. |
| K-05 | **There's no UI to select or deselect cart items**, yet totals and the order only include `selected !== false` items. `toggle`, `select-all` and `clear` are never called. | `Cart.jsx`, `CartContext.jsx:210-284` | If the backend ever returns `selected:false`, the item shows in the cart but is silently left out of the order with no way to include it. **The backend should default `selected` to `true`.** |
| K-06 | `placingOrder` in the Cart is never set to `true`. | `Cart.jsx:96-97` | "Processing..." never shows. Double-clicking opens WhatsApp twice. |
| K-07 | **"I Haven't Sent It" keeps `pendingWhatsAppOrder`.** Back on `/cart`, any time the tab becomes visible again (e.g. after switching tabs) the user is redirected to `/whatsapp-confirm`. | `WhatsAppConfirm.jsx:460-462`, `Cart.jsx:513-544` | The user is stuck in a redirect loop until they confirm or clear storage. |
| K-08 | `pendingWhatsAppOrder` isn't scoped to a user and survives logout. | `Cart.jsx:377-380` | Another user logging in on the same browser can see and submit someone else's pending order. |
| K-09 | **Order reference mismatch.** The `AKRF-YYYYMMDD-NNNN` reference in the WhatsApp message is generated on the client and never sent. The backend creates its own `orderId`. "Send WhatsApp Again" sends no reference at all. | `Cart.jsx:283-300, 382`; `WhatsAppConfirm.jsx:126-182` | The business can't match WhatsApp messages to backend orders by reference. |
| K-10 | Return-from-WhatsApp detection only works while `/cart` is mounted and relies on `visibilitychange`. If WhatsApp opens in the same tab or app (common on mobile), the flow depends on the user coming back to the browser tab. | `Cart.jsx:513-544` | The user may never reach the confirm page and must navigate manually. |
| K-11 | Ordered items are removed from the cart **by the client** after creation. The code comment says the backend should do this too. | `WhatsAppConfirm.jsx:373-405` | If both remove them, the client's DELETEs may fail. Those errors are swallowed, so it's harmless as long as the response is JSON. |
| K-12 | `Login` ignores `location.state.from` set by `AdminProtectedRoute`, and admins ignore `?redirect`. | `AdminProtectedRoute.jsx:26`, `Login.jsx:57-65` | Deep links to admin sub-pages always land on `/admin` after login. |
| K-13 | `/my-orders/:id` has no client-side auth guard. | `OrderDetails.jsx:147-185` | It relies on the backend returning an error for anonymous or non-owner access. The backend must enforce ownership. |
| K-14 | When the My Orders fetch fails, only a toast is shown, and the page then shows "No Orders Yet". | `MyOrders.jsx:245-258, 342` | Misleading empty state. |
| K-15 | **Home loads banners and promo cards with one `Promise.all`.** If either fails, both sections are cleared. | `Home.jsx:540-572` | Partial outage hides all marketing content. |
| K-16 | **The Dashboard loads 3 lists with `Promise.all`.** One failure zeroes every stat. | `Dashboard.jsx:152-212` | Misleading zeros. |
| K-17 | Admin order status can be changed to any value, including backwards (e.g. Delivered → Pending), with no confirmation. A single `updatingStatus` flag disables every row's select. | `Orders.jsx:225-355, 789-819` | Accidental changes. **The backend should define how `statusDates` behave on backward moves.** |
| K-18 | `Product.jsx` sends `oldPrice: ""` and `description: ""` when blank, because `toFormData` only skips `null`/`undefined`. | `Product.jsx:237-248`, `adminApi.js:46-63` | **The backend must accept `""` for `oldPrice`** (as "none" / "clear") and must not fail number parsing. |
| K-19 | The admin product table shows a struck-through old price whenever `oldPrice != null`, so `0` or `""` renders as "₹0" or "₹". | `Product.jsx:377-381` | Cosmetic. **The backend should return `null` or omit `oldPrice` when it isn't set.** |
| K-20 | Banners and promo cards **can't be edited**, only created and deleted. There's no client-side image type or size check (`accept="image/*"` only). | `Banner.jsx`, `PromoCard.jsx` | The backend must validate uploads. |
| K-21 | The Banner and PromoCard admin pages call `document.getElementById(...).value = ""` after upload. | `Banner.jsx:141-143`, `PromoCard.jsx:145-147` | Works, but is fragile. |
| K-22 | The Shop search box doesn't update the URL, so the `?search=` value from the header stays in the URL while the box shows something else. | `Shop.jsx:943-945, 1443-1454` | Cosmetic and confusing. |
| K-23 | The Shop wishlist is in memory only and has no API. | `Shop.jsx:787-790, 1212-1230` | Lost on navigation. |
| K-24 | There's no 404 route. | `App.jsx` | Unknown URLs render a blank page (no header, footer or "not found" message). |
| K-25 | About page CTAs use `<a href="/shop">` rather than `<Link>`. | `About.jsx:102-108, 203-209` | Full page reload, which re-runs `/api/auth/me`. |
| K-26 | The footer has placeholder business data (`your-email@example.com`, `Your Store Address, India`) that conflicts with the Contact page (`akroyalflames@gmail.com`, `Delhi, India`). The Contact Instagram link is generic. The footer newsletter form is commented out (`handleSubscribe` is unused). | `Footer.jsx:28-31, 436-468`; `Contact.jsx:27-37, 433` | Content inconsistency. |
| K-27 | The Contact map is a placeholder. | `Contact.jsx:688-693` | Missing feature. |
| K-28 | `BASE_URL` in `Cart.jsx` is declared but unused. | `Cart.jsx:33` | Dead code. |
| K-29 | `MyOrders` and `OrderDetails` build image URLs themselves (not with `imageUrl`), so `data:` URLs or paths without a leading `/` break. | `MyOrders.jsx:617-624`, `OrderDetails.jsx:848-854` | **The backend should store order item images as `/…` paths or absolute URLs.** |
| K-30 | Registration accepts any phone format, but checkout requires `^[6-9]\d{9}$`. | `Register.jsx:258-264` | The autofilled mobile may fail checkout validation. |
| K-31 | My Orders and Admin Orders show orders in API order (no client sort). The Dashboard sorts its own list. | `MyOrders.jsx:394`, `Orders.jsx:707` | **The backend should return orders newest first.** |
| K-32 | The session is only checked once, at load. There's no global 401 handling or auto-logout when the session expires. | `AuthContext.jsx:40-42` | The UI keeps showing a logged-in state until reload. |
| K-33 | Several pages log full payloads and responses to the console (`FINAL ORDER PAYLOAD`, `ORDER API RESPONSE`, `Register response`, `Dashboard Orders`, `Opening WhatsApp`). | various | Personal data leaks into the browser console. |

### 10.2 Inconsistent field names and shapes the backend must follow

| Topic | What the frontend does |
|---|---|
| List key | Catalogue, banner and promo-card lists use **`data`**. Customer orders use **`orders`**. A single order uses **`order`**. Admin orders accept `orders` **or** `data`. The cart uses **`data.items`** or `cart.items`. |
| Phone naming | Register sends **`phone`**. The user object is read as **`user.phone`**. Order `customer` uses **`mobile`** (the Dashboard also tries `customer.phone`). |
| Product id in cart vs order | Cart calls send **`productId`**. Order items send **`productId`**. Cart lines are keyed by the populated **`product._id`**. Pending-order items in localStorage use **`_id`**. |
| `category` on product | Either a populated `{_id,name}` or a raw id string. Both are supported. |
| Banner/promo id | `_id` preferred. Home also accepts `id` (only for React keys). Delete calls use `_id`. |
| Shipping | `shipping` is always `0` from the client. `shippingStatus` is `"FREE"` or `"PAYABLE_SEPARATELY"` (with underscore). The UI displays "PAYABLE SEPARATELY" or "Pay Separately". |
| `success` strictness | Auth and order-customer endpoints need `success` to be **truthy**. `adminApi` and cart endpoints only fail on **`success === false`**. |

### 10.3 Ambiguities (behaviour the frontend doesn't define)

- **`expectedDelivery` rule:** the frontend shows it but never sends it. How it's computed (e.g. createdAt + N days, or set by an admin) is undefined.
- **`orderId` format:** it's displayed only. The client-side `AKRF-YYYYMMDD-NNNN` pattern suggests a convention, but the frontend doesn't require it.
- **Stock handling on order:** whether stock is reserved or decremented at order creation, at confirmation or at delivery isn't specified. The cart only checks `stock` for UI limits.
- **Cart add semantics:** the "Add More" label implies `quantity` is **added** to the existing line. This should be confirmed.
- **Category deletion with products:** what happens to products referencing a deleted category isn't handled. The UI shows "—" or "Candles" for unknown categories.
- **Banner/promo `order` field:** it's sent as a numeric string and displayed, but the storefront doesn't sort. The backend is expected to return storefront lists sorted by `order`.
- **Public vs admin banner/promo lists:** two endpoints each (`get-banner` vs `get-all-banner`). The difference (e.g. an active filter) isn't defined by the frontend.
- **`/api/auth/me` when logged out:** either a 401 with JSON or a 200 `{success:false}` works.

### 10.4 Security concerns for the new backend

1. **Admin authorization must be enforced on the server** for every admin endpoint (#13–15, 17–19, 21–23, 25–27, 31, 32). The client-side `role` check is cosmetic only.
2. **Never trust client prices or totals** in `POST /api/order/create`. Recompute `price`, `total`, `itemsTotal`, `grandTotal` and `shippingStatus` from stored products. Validate stock and that `productId`s exist.
3. **Order ownership:** `/api/order/my-orders` and `/api/order/my-orders/:id` must only return the session user's orders.
4. **Cookie-based auth with cross-origin credentials** requires strict CORS (an explicit origin allow-list, `Allow-Credentials: true`) and CSRF protection on state-changing endpoints (e.g. a SameSite cookie policy and/or origin checking). The frontend sends no CSRF token, so the protection must not rely on the client sending one.
5. **File uploads:** validate type and size on the server (banner and promo uploads have no client checks). Serve uploads from a path that can't run scripts.
6. **`buttonLink` values** are used in `window.location.href`. The backend should reject `javascript:` and other dangerous schemes, since admin-entered values reach every visitor.
7. **Registration input:** the server must validate email format, password length (≥ 6 is only enforced on the client), uniqueness, and must hash passwords.
8. **Error messages** are shown verbatim. Don't leak internal details (stack traces, query errors) in `message`.

---

## 11. Coverage Checklist

### 11.1 Source files read (all of them)

| # | File | Lines | Notes |
|---|---|---|---|
| 1 | `index.html` | 13 | Title "AK Royal Flames", favicon, root mount |
| 2 | `package.json` | 30 | Dependencies & scripts |
| 3 | `vite.config.js` | 9 | host `0.0.0.0`, port 5173 |
| 4 | `tailwind.config.js` | 10 | Default theme |
| 5 | `postcss.config.js` | 6 | tailwind + autoprefixer |
| 6 | `.oxlintrc.json` | 8 | Lint rules |
| 7 | `.gitignore` | 24 | — |
| 8 | `README.md` | 16 | Vite template boilerplate |
| 9 | `src/main.jsx` | 10 | StrictMode root |
| 10 | `src/index.css` | 2 | Tailwind directives |
| 11 | `src/App.jsx` | 216 | Routes & providers |
| 12 | `src/utils/adminApi.js` | 62 | `adminApi`, `imageUrl`, `toFormData`, BASE_URL (uncommitted change) |
| 13 | `src/context/AuthContext.jsx` | 132 | Auth API |
| 14 | `src/context/CartContext.jsx` | 343 | Cart API |
| 15 | `src/components/Header.jsx` | 465 | — |
| 16 | `src/components/Footer.jsx` | 533 | — |
| 17 | `src/components/ScrollToTop.jsx` | 17 | — |
| 18 | `src/components/DataTable.jsx` | 187 | — |
| 19 | `src/components/AddToCartButton.jsx` | 59 | Unused |
| 20 | `src/pages/Home.jsx` | 1223 | — |
| 21 | `src/pages/Shop.jsx` | 1754 | — |
| 22 | `src/pages/About.jsx` | 217 | — |
| 23 | `src/pages/Contact.jsx` | 700 | — |
| 24 | `src/pages/Cart.jsx` | 1544 | — |
| 25 | `src/pages/Login.jsx` | 230 | — |
| 26 | `src/pages/Register.jsx` | 447 | — |
| 27 | `src/pages/MyOrders.jsx` | 744 | — |
| 28 | `src/pages/OrderDetails.jsx` | 1192 | — |
| 29 | `src/pages/WhatsAppConfirm.jsx` | 909 | — |
| 30 | `src/admin/AdminProtectedRoute.jsx` | 39 | — |
| 31 | `src/admin/AdminLayout.jsx` | 286 | — |
| 32 | `src/admin/Dashboard.jsx` | 783 | — |
| 33 | `src/admin/Category.jsx` | 565 | — |
| 34 | `src/admin/Product.jsx` | 676 | — |
| 35 | `src/admin/Banner.jsx` | 445 | — |
| 36 | `src/admin/PromoCard.jsx` | 473 | — |
| 37 | `src/admin/Orders.jsx` | 1603 | — |

**Static assets checked (binary, no logic):**
- Referenced: `public/favicon.svg`, `public/images/logo.png`, `candle1.jpg`, `candle2.jpg`.
- Present but **unreferenced**: `public/icons.svg`, `public/images/{banner1.jpg, banner2.png, banner3.png, candle3.jpg, logo1.svg, logo3.jpeg, video1.mp4, video2.mp4}`, `src/assets/{hero.png, react.svg, vite.svg}`.

**Excluded:** `node_modules/`, `dist/` (build output), `package-lock.json` (lockfile, no app logic). **There are no `.env*` files.**

### 11.2 Counts

| Item | Count |
|---|---|
| Source/config files read | 37 |
| Route paths | **16** (10 website + 6 admin), plus 0 catch-all |
| Distinct API endpoints | **32** (29 called from UI flows, 3 defined in CartContext but unused: `/api/cart/toggle`, `/api/cart/select-all`, `/api/cart/clear`) |
| Endpoints by area | Auth 4 · Cart 7 · Category 4 · Product 4 · Banner 4 · Promo card 4 · Order 5 |
| Public (no-auth) endpoints the storefront needs | 4 GET (`get-category`, `get-product`, `get-banner`, `get-promo-card`) + register + login (+ `me`, which may fail) |
| Multipart upload endpoints | 6 (category create/update, product create/update, banner create, promo-card create). The file field is always **`image`** |
| localStorage keys | 1 (`pendingWhatsAppOrder`) |
| Cookies set or read by JS | 0 (the browser handles the session cookie) |
| Environment variables | 0 |
| Functional requirements | **128** (FR-UI-001 … FR-UI-128) |
| Known issues listed | 33 (K-01 … K-33), plus §10.2–10.4 |

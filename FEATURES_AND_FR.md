# Candle Shop Backend: Features and Functional Requirements Specification

> Purpose: a complete, implementation-ready description of the existing backend's behavior, so it can be rebuilt in any technology stack without changing the existing React frontend or the existing MongoDB data.
>
> Convention used throughout: **"actually does"** describes current behavior, including quirks. Quirks and suspected defects are also listed in [§13 Known Issues](#13-known-issues--ambiguities). A rebuild that must stay compatible should reproduce the behavior in §1–§12 exactly, unless a deliberate fix is agreed on.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Actors and Roles](#2-actors-and-roles)
3. [Configuration / Environment Variables](#3-configuration--environment-variables)
4. [Data Models](#4-data-models)
5. [Authentication and Authorization](#5-authentication-and-authorization)
6. [API Endpoints](#6-api-endpoints)
7. [File Uploads and Static Files](#7-file-uploads-and-static-files)
8. [Third-Party Integrations](#8-third-party-integrations)
9. [Business Rules](#9-business-rules)
10. [Background Jobs / Scheduled Tasks / Startup Behaviour](#10-background-jobs--scheduled-tasks--startup-behaviour)
11. [Error Handling Conventions](#11-error-handling-conventions)
12. [Functional Requirements List](#12-functional-requirements-list)
13. [Known Issues / Ambiguities](#13-known-issues--ambiguities)
14. [Coverage Checklist](#14-coverage-checklist)

---

## 1. Overview

### 1.1 What the application does

This backend is the REST API for a small online **candle shop** (order IDs carry the brand prefix `AKRF-`). It provides:

- **Customer accounts:** registration, login, logout, and "who am I", using a JWT stored in an HTTP-only cookie.
- **Catalogue:** product categories and products, each with one uploaded image.
- **Home-page merchandising:** hero **banners** and **promotional cards**, each with one uploaded image, a display order, and an active flag.
- **Shopping cart:** one persistent cart per user. Each line can be selected or deselected for checkout.
- **Orders:** checkout creates an order with customer delivery details. The payment method defaults to `"WhatsApp Order"`, which means payment and confirmation happen outside the system, for example over WhatsApp. Customers can see their own orders. Admins can see all orders and change an order's status.
- **Static file hosting** for uploaded images under `/uploads/...`.

There is no online payment gateway, no email or SMS, no coupon system, and no stock deduction.

### 1.2 Users

| User | Description |
|---|---|
| Anonymous visitor | Browses categories, products, active banners and promo cards. Can register or log in. (Today, an anonymous visitor can also call every catalogue and merchandising write endpoint, because those endpoints are unprotected. See §13.) |
| Customer (`role: "user"`) | Manages their cart, places orders, views their own orders. |
| Administrator (`role: "admin"`) | Everything a customer can do, plus view all orders and update order status. The frontend's admin pages also use the catalogue, banner and promo-card write endpoints, which the server does not restrict. |

### 1.3 Main business flows

1. **Browse:** `GET /api/category/get-category`, `GET /api/product/get-product`, `GET /api/banner/get-banner`, `GET /api/promo-card/get-promo-card`. Images load from `/uploads/<file>`.
2. **Register / login:** `POST /api/auth/register` or `POST /api/auth/login` sets the `accessToken` cookie. `GET /api/auth/me` restores the session on page load.
3. **Cart:** `GET /api/cart` (auto-creates an empty cart), `POST /api/cart/add`, `PUT /api/cart/update`, `PUT /api/cart/toggle`, `DELETE /api/cart/remove/:productId`, `DELETE /api/cart/clear`.
4. **Checkout:** `POST /api/order/create` with customer details, items and totals that the client calculates. The ordered products are removed from the cart. The order starts at `Pending`, and expected delivery is set to order time plus 3 days.
5. **Order tracking:** `GET /api/order/my-orders` and `GET /api/order/my-orders/:id`.
6. **Admin order management:** `GET /api/order/all` and `PUT /api/order/status/:id`. Any status can be set at any time. Each status records its own timestamp.
7. **Admin catalogue and merchandising:** create, update and delete categories and products; create and delete banners and promo cards (multipart uploads).

---

## 2. Actors and Roles

### 2.1 Role storage

- A user's role is stored in the `role` field of the user document in the `users` collection.
- Allowed values: `"user"` and `"admin"`. Default: `"user"`.
- The role is **not** stored in the JWT. On every authenticated request, the server reads it from the database by loading the user identified by `userId` in the token.
- Registration always creates `role: "user"`. **No API endpoint creates an admin or changes a role.** Admins must be promoted directly in the database by setting `role` to `"admin"`.

### 2.2 Permissions matrix

Legend: ✅ allowed, ❌ denied, — not applicable.

| Capability | Anonymous | user | admin |
|---|---|---|---|
| Health check `GET /` | ✅ | ✅ | ✅ |
| Register, login, logout | ✅ | ✅ | ✅ |
| `GET /api/auth/me` | ❌ 401 | ✅ | ✅ |
| Read categories, products, active banners, active promo cards | ✅ | ✅ | ✅ |
| Read **all** banners and promo cards ("admin" lists) | ✅ (unprotected) | ✅ | ✅ |
| Create, update, delete categories and products | ✅ (unprotected) | ✅ | ✅ |
| Create and delete banners and promo cards | ✅ (unprotected) | ✅ | ✅ |
| Cart operations (own cart only) | ❌ 401 | ✅ | ✅ |
| Create order, list or view own orders | ❌ 401 | ✅ | ✅ |
| List all orders | ❌ 401 | ❌ 403 | ✅ |
| Update order status | ❌ 401 | ❌ 403 | ✅ |
| Fetch uploaded files `/uploads/*` | ✅ | ✅ | ✅ |

Customers can only read their own orders: order lookups are filtered by the authenticated user's id. Admins have no special read path for a single order other than `GET /api/order/all`.

---

## 3. Configuration / Environment Variables

The server loads variables from a `.env` file in the working directory at startup. Variables already present in the real process environment take precedence over `.env` values.

### 3.1 Variables read by the code

| Name | Purpose | Required | Default in code |
|---|---|---|---|
| `PORT` | HTTP listen port | No | `9000` |
| `MONGO_URI` | MongoDB connection string | **Yes.** If missing or unreachable, the process logs an error and exits with code 1. | none |
| `FRONTEND_URL` | The single CORS origin that is allowed, e.g. `http://localhost:5173` | Effectively yes. If unset, CORS falls back to `Access-Control-Allow-Origin: *`, which browsers reject for credentialed requests. | none |
| `JWT_SECRET` | HMAC secret for signing and verifying JWTs | Effectively yes | **Signing:** if `JWT_SECRET` is not in the real process environment when the module loads, a hard-coded fallback literal from the source code is used. **Verification:** reads `JWT_SECRET` at request time, so it uses the `.env` value, with no fallback. See §5.3 and §13 (KI-02). |

### 3.2 Variables present in `.env` but never read by the code

| Name | Notes |
|---|---|
| `GOOGLE_MAPS_API_KEY` | Declared but unused. No maps integration exists. |
| (commented-out second `FRONTEND_URL`) | Ignored. |

*Secret values are intentionally not reproduced in this document.*

### 3.3 HTTP server settings

| Setting | Value |
|---|---|
| Listen port | `PORT`, or `9000` if unset |
| Startup log line | `server started on port <port>` |
| Global API prefix | none; each module mounts under `/api/<module>` (see §6) |
| Route matching | Case-insensitive, and a trailing slash is optional: `/api/Cart/` matches `/api/cart` |
| Query parameters | **None are read by any endpoint** |

### 3.4 Request body parsing

Requests are processed in this order: cookie parsing, then JSON and URL-encoded body parsing, then CORS, then static files, then routes.

| Content type | Handling | Size limit |
|---|---|---|
| `application/json` | Parsed into the request body | **10 MB.** Exceeding it returns HTTP 413 (default HTML error page, see §11). |
| `application/x-www-form-urlencoded` | Parsed with nested-object support, e.g. `customer[name]=X` becomes `{customer:{name:"X"}}` | **10 MB** |
| `multipart/form-data` | Parsed only on upload endpoints (see §7). The text fields become body fields, all strings. | 100 MB per file |
| Other or none | The body is an empty object `{}` | — |

Malformed JSON returns HTTP 400 with the default HTML error page.

### 3.5 Cookies

Incoming cookies are parsed so that `accessToken` can be read. Signed cookies are not used.

### 3.6 CORS

| Aspect | Value |
|---|---|
| Allowed origin | Exactly the string in `FRONTEND_URL`. The response header `Access-Control-Allow-Origin` is always set to this value, whatever the request's Origin, together with `Vary: Origin`. |
| Credentials | `Access-Control-Allow-Credentials: true` |
| Allowed methods (preflight) | `GET,HEAD,PUT,PATCH,POST,DELETE` |
| Allowed headers (preflight) | Echoes the request's `Access-Control-Request-Headers` |
| Exposed headers / max-age | none |
| Preflight response | HTTP `204`, empty body |
| Scope | All routes, including `/uploads/*` and `/` |

### 3.7 Static file serving

| URL prefix | Served from |
|---|---|
| `/uploads/<filename>` | The `uploads` folder relative to the process working directory. Standard static-file behavior: ETag and Last-Modified headers, `Cache-Control: public, max-age=0`, dotfiles ignored. A missing file returns the generic 404 (§11). |

---

## 4. Data Models

### 4.0 Conventions common to every collection

- Every document has `_id` (ObjectId). In JSON responses it is a 24-character lowercase hex string.
- Every collection has **automatic timestamps** `createdAt` and `updatedAt` (BSON Date). Both are set on insert, and `updatedAt` is refreshed on every save. In JSON they are ISO-8601 UTC strings with milliseconds, e.g. `"2026-10-02T09:15:27.481Z"`.
- Every document has a version key **`__v`** (integer, starting at `0`). It is returned in responses. It increases when an array field is replaced, pushed to or pulled from, for example cart item changes. Existing data contains it, so a rebuild should keep the field in stored and returned documents.
- Fields not defined in a schema are dropped on write (strict schemas).
- "trim" means leading and trailing whitespace is removed before storing. "lowercase" means the value is lower-cased before storing.
- No soft-delete flags exist. All deletes are hard deletes.
- There are no pre-save or post-save hooks, virtual fields or model methods. All logic, including password hashing, lives in the endpoint handlers.
- Indexes marked unique are created automatically at startup if they don't exist.
- JSON responses do **not** include a virtual `id` field. The one exception is the auth endpoints, which build `user.id` by hand.

### 4.1 `users`

| Field | Type | Required | Default | Constraints / notes |
|---|---|---|---|---|
| `_id` | ObjectId | auto | — | — |
| `name` | String | **yes** | — | trim |
| `email` | String | **yes** | — | **unique index**, lowercase, trim. Format is not validated. |
| `phone` | String | no | `""` | — |
| `password` | String | **yes** | — | **bcrypt hash**, cost 10, prefix `$2a$10$`, 60 characters. Never returned by any endpoint. |
| `address` | String | no | `""` | Not writable through any endpoint |
| `city` | String | no | `""` | Not writable through any endpoint |
| `pincode` | String | no | `""` | Not writable through any endpoint |
| `role` | String | no | `"user"` | enum: `"user"`, `"admin"` |
| `createdAt`, `updatedAt` | Date | auto | — | — |
| `__v` | Number | auto | `0` | — |

References: referenced by `carts.user` and `orders.user`. When an order's `user` is populated, every field except `password` is included.

Serialized example (as embedded in populated orders):

```json
{
  "_id": "66fa1c2b9d3e4a0012ab34cd",
  "name": "Asha Verma",
  "email": "asha@example.com",
  "phone": "9876543210",
  "address": "",
  "city": "",
  "pincode": "",
  "role": "user",
  "createdAt": "2026-09-30T10:00:00.000Z",
  "updatedAt": "2026-09-30T10:00:00.000Z",
  "__v": 0
}
```

### 4.2 `categories`

| Field | Type | Required | Default | Constraints / notes |
|---|---|---|---|---|
| `_id` | ObjectId | auto | — | — |
| `name` | String | **yes** | — | trim, **unique index** (case-sensitive) |
| `description` | String | no | `""` | — |
| `image` | String | **yes** | — | Relative URL path such as `/uploads/1790670860904-253178900.png` |
| `createdAt`, `updatedAt`, `__v` | — | auto | — | — |

References: referenced by `products.category`. The category is **never populated** in product responses.

```json
{
  "_id": "66fa1d009d3e4a0012ab3500",
  "name": "Jar Candles",
  "description": "Soy wax candles in glass jars",
  "image": "/uploads/1790670860904-253178900.png",
  "createdAt": "2026-09-30T10:05:00.000Z",
  "updatedAt": "2026-09-30T10:05:00.000Z",
  "__v": 0
}
```

### 4.3 `products`

| Field | Type | Required | Default | Constraints / notes |
|---|---|---|---|---|
| `_id` | ObjectId | auto | — | — |
| `name` | String | **yes** | — | trim. Not unique at database level. The handler rejects a duplicate name within the same category. |
| `category` | ObjectId → `categories` | **yes** | — | Returned as a plain id string, never populated |
| `price` | Number | **yes** | — | min `1`. Decimals allowed. |
| `oldPrice` | Number | no | *(absent)* | min `1`. The field is omitted entirely when not set. |
| `stock` | Number | **yes** | — | min `0`. Handlers require an integer. |
| `description` | String | no | `""` | — |
| `image` | String | **yes** | — | `/uploads/<file>` |
| `createdAt`, `updatedAt`, `__v` | — | auto | — | — |

References: referenced by `carts.items[].product` and `orders.items[].product`. In cart and order responses those references are populated with the full product document. They become `null` if the product has since been deleted.

```json
{
  "_id": "66fa1e119d3e4a0012ab3601",
  "name": "Lavender Jar Candle",
  "category": "66fa1d009d3e4a0012ab3500",
  "price": 499,
  "oldPrice": 699,
  "stock": 25,
  "description": "Hand-poured lavender soy candle",
  "image": "/uploads/1790698202524-11481566.png",
  "createdAt": "2026-09-30T10:10:00.000Z",
  "updatedAt": "2026-09-30T10:10:00.000Z",
  "__v": 0
}
```

### 4.4 `carts`

| Field | Type | Required | Default | Constraints / notes |
|---|---|---|---|---|
| `_id` | ObjectId | auto | — | — |
| `user` | ObjectId → `users` | **yes** | — | **unique index**: one cart per user. Never populated. |
| `items` | Array of CartItem | no | `[]` | — |
| `createdAt`, `updatedAt`, `__v` | — | auto | — | — |

**CartItem** (embedded, **no `_id`**):

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `product` | ObjectId → `products` | **yes** | — | Populated with the full product (or `null`) in every cart response, except the clear-cart response |
| `quantity` | Number | no | `1` | min `1`. Integers are not enforced. |
| `selected` | Boolean | no | `true` | Marks whether the line is selected for checkout |

```json
{
  "_id": "66fa20009d3e4a0012ab3700",
  "user": "66fa1c2b9d3e4a0012ab34cd",
  "items": [
    {
      "product": { "...full product object (§4.3)...": "" },
      "quantity": 2,
      "selected": true
    }
  ],
  "createdAt": "2026-09-30T11:00:00.000Z",
  "updatedAt": "2026-09-30T11:05:00.000Z",
  "__v": 1
}
```

### 4.5 `orders`

| Field | Type | Required | Default | Constraints / notes |
|---|---|---|---|---|
| `_id` | ObjectId | auto | — | — |
| `orderId` | String | **yes** | — | **unique index**. Format `AKRF-<epochMillis>-<4-digit random 1000–9999>`, e.g. `AKRF-1790700056594-4821` |
| `user` | ObjectId → `users` | **yes** | — | Indexed. Populated (without `password`) in the create, admin list and status-update responses. Not populated in the customer list or detail responses. |
| `customer` | Object | — | — | Nested (not a sub-document, no `_id`): |
| `customer.name` | String | **yes** | — | — |
| `customer.mobile` | String | **yes** | — | — |
| `customer.address` | String | **yes** | — | — |
| `customer.city` | String | **yes** | — | — |
| `customer.pincode` | String | **yes** | — | — |
| `customer.message` | String | no | `""` | Note from the customer |
| `items` | Array of OrderItem | **yes** | — | — |
| `itemsTotal` | Number | **yes** | — | Supplied by the client, not recalculated |
| `shipping` | Number | no | `0` | — |
| `shippingStatus` | String | no | `"FREE"` | enum: `"FREE"`, `"PAYABLE_SEPARATELY"`. `null` is also accepted. |
| `grandTotal` | Number | **yes** | — | Supplied by the client, not recalculated |
| `paymentMethod` | String | no | `"WhatsApp Order"` | Free text |
| `status` | String | no | `"Pending"` | enum: `"Pending"`, `"Confirmed"`, `"Processing"`, `"Shipped"`, `"Delivered"`, `"Cancelled"` |
| `statusDates` | Object | — | — | Nested object. One Date-or-null per status: |
| `statusDates.Pending` | Date | no | `null` | — |
| `statusDates.Confirmed` | Date | no | `null` | — |
| `statusDates.Processing` | Date | no | `null` | — |
| `statusDates.Shipped` | Date | no | `null` | — |
| `statusDates.Delivered` | Date | no | `null` | — |
| `statusDates.Cancelled` | Date | no | `null` | — |
| `expectedDelivery` | Date | no | `null` | Order time + 3 days. Set to `null` when cancelled. |
| `createdAt`, `updatedAt`, `__v` | — | auto | — | — |

**OrderItem** (embedded, **no `_id`**):

| Field | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `product` | ObjectId → `products` | **yes** | — | Populated with the full product (or `null`) in every order response |
| `name` | String | **yes** | — | Product-name snapshot from the client |
| `image` | String | no | `""` | Image snapshot from the client |
| `price` | Number | **yes** | — | Unit-price snapshot from the client |
| `quantity` | Number | **yes** | — | min `1` |
| `total` | Number | **yes** | — | Calculated by the server as `price × quantity` |

```json
{
  "_id": "66fa30009d3e4a0012ab3800",
  "orderId": "AKRF-1790700056594-4821",
  "user": "66fa1c2b9d3e4a0012ab34cd",
  "customer": {
    "name": "Asha Verma",
    "mobile": "9876543210",
    "address": "12 MG Road",
    "city": "Jaipur",
    "pincode": "302001",
    "message": "Please gift wrap"
  },
  "items": [
    {
      "product": { "...full product object (§4.3) or null...": "" },
      "name": "Lavender Jar Candle",
      "image": "/uploads/1790698202524-11481566.png",
      "price": 499,
      "quantity": 2,
      "total": 998
    }
  ],
  "itemsTotal": 998,
  "shipping": 0,
  "shippingStatus": "FREE",
  "grandTotal": 998,
  "paymentMethod": "WhatsApp Order",
  "status": "Pending",
  "statusDates": {
    "Pending": "2026-10-02T09:15:27.481Z",
    "Confirmed": null,
    "Processing": null,
    "Shipped": null,
    "Delivered": null,
    "Cancelled": null
  },
  "expectedDelivery": "2026-10-05T09:15:27.481Z",
  "createdAt": "2026-10-02T09:15:27.490Z",
  "updatedAt": "2026-10-02T09:15:27.490Z",
  "__v": 0
}
```

### 4.6 `banners`

| Field | Type | Required | Default | Constraints / notes |
|---|---|---|---|---|
| `_id` | ObjectId | auto | — | — |
| `title` | String | **yes** | — | trim |
| `subtitle` | String | no | `""` | trim |
| `image` | String | **yes** | — | `/uploads/<file>` |
| `buttonText` | String | no | `"Shop Now"` | — |
| `buttonLink` | String | no | `"/shop"` | — |
| `order` | Number | no | `0` | Display order, ascending |
| `status` | Boolean | no | `true` | Active flag. Only `true` banners are public. |
| `createdAt`, `updatedAt`, `__v` | — | auto | — | — |

```json
{
  "_id": "66fa40009d3e4a0012ab3900",
  "title": "Festive Collection",
  "subtitle": "Up to 30% off",
  "image": "/uploads/1790700080917-344934455.jpeg",
  "buttonText": "Shop Now",
  "buttonLink": "/shop",
  "order": 0,
  "status": true,
  "createdAt": "2026-10-01T08:00:00.000Z",
  "updatedAt": "2026-10-01T08:00:00.000Z",
  "__v": 0
}
```

### 4.7 `promocards`

Same as `banners`, plus a `background` field.

| Field | Type | Required | Default | Constraints / notes |
|---|---|---|---|---|
| `_id` | ObjectId | auto | — | — |
| `title` | String | **yes** | — | trim |
| `subtitle` | String | no | `""` | trim |
| `image` | String | **yes** | — | `/uploads/<file>` |
| `buttonText` | String | no | `"Shop Now"` | — |
| `buttonLink` | String | no | `"/shop"` | — |
| `background` | String | no | `"#08aaa6"` | CSS colour, not validated |
| `order` | Number | no | `0` | — |
| `status` | Boolean | no | `true` | Active flag |
| `createdAt`, `updatedAt`, `__v` | — | auto | — | — |

```json
{
  "_id": "66fa41009d3e4a0012ab3a00",
  "title": "Gift Sets",
  "subtitle": "Perfect for Diwali",
  "image": "/uploads/1790700101917-149332359.jpeg",
  "buttonText": "Shop Now",
  "buttonLink": "/shop",
  "background": "#08aaa6",
  "order": 1,
  "status": true,
  "createdAt": "2026-10-01T08:10:00.000Z",
  "updatedAt": "2026-10-01T08:10:00.000Z",
  "__v": 0
}
```

### 4.8 Index summary

| Collection | Index | Unique |
|---|---|---|
| users | `email` | yes |
| categories | `name` | yes |
| carts | `user` | yes |
| orders | `orderId` | yes |
| orders | `user` | no |
| (all) | `_id` | yes (default) |

---

## 5. Authentication and Authorization

### 5.1 Overview

- Authentication is stateless and uses a **JWT carried in an HTTP-only cookie named `accessToken`**.
- The `Authorization` header is **not** read. A token sent only as `Bearer` is ignored, and the request gets 401 `"Please login first"`.
- There is **no** OTP, password reset, email verification, refresh token, token revocation or profile update.

### 5.2 Password hashing

| Aspect | Value |
|---|---|
| Algorithm | **bcrypt** |
| Cost factor | **10** |
| Stored format | Standard modular-crypt string, version prefix `$2a$`, e.g. `$2a$10$<53 chars>` (60 chars total). A rebuild must verify existing `$2a$` hashes. |
| Comparison | Standard bcrypt compare of the plaintext against the stored hash |

### 5.3 Token

| Aspect | Value |
|---|---|
| Format | JWT (JWS compact) |
| Algorithm | **HS256** (HMAC-SHA256) |
| Signing secret | The value of `JWT_SECRET` **as it was in the process environment when the auth module loaded**, before `.env` is applied, otherwise a hard-coded fallback literal (KI-02). In the current deployment, the `.env` value equals that fallback, so signing and verification agree. A rebuild should simply use `JWT_SECRET` for both. |
| Verification secret | `JWT_SECRET` read at request time. HS256, HS384 and HS512 are accepted. |
| Payload | `{ "userId": "<24-hex user _id>", "iat": <epoch seconds>, "exp": <iat + 604800> }` |
| Expiry | **7 days** (`604800` seconds) |

### 5.4 Cookie

Set on successful register and login:

| Attribute | Value |
|---|---|
| Name | `accessToken` |
| Value | the JWT |
| `HttpOnly` | yes |
| `Secure` | **no** |
| `SameSite` | `Lax` |
| `Max-Age` | `604800` seconds (7 days), plus the matching `Expires` |
| `Path` | `/` |
| `Domain` | not set (host-only) |

Example header:
`Set-Cookie: accessToken=<jwt>; Max-Age=604800; Path=/; Expires=Fri, 09 Oct 2026 09:15:27 GMT; HttpOnly; SameSite=Lax`

Cleared on logout:
`Set-Cookie: accessToken=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; HttpOnly; SameSite=Lax`

### 5.5 Authentication guard ("auth required")

Runs before a protected handler:

1. Read cookie `accessToken`. If it is missing or empty, respond **401** `{"success":false,"message":"Please login first"}`.
2. Verify the JWT signature and expiry with `JWT_SECRET`. On any failure (bad signature, malformed, expired, secret not configured), log `Auth middleware error: <reason>` and respond **401** `{"success":false,"message":"Invalid or expired session"}`.
3. Load the user by `_id = payload.userId`, excluding `password`. If no user is found, including when `userId` is absent, respond **401** `{"success":false,"message":"User not found"}`.
4. If a database error occurs at this step, respond **401** `"Invalid or expired session"`, the same as step 2.
5. Attach the user (without password) to the request as the "current user" and continue.

### 5.6 Admin guard

Runs **after** the authentication guard:

1. If there is no current user, respond **401** `{"success":false,"message":"Please login first"}`. This cannot happen in practice.
2. If `currentUser.role !== "admin"`, respond **403** `{"success":false,"message":"Admin access required"}`.
3. On an unexpected exception, log `Admin middleware error: <msg>` and respond **403** `{"success":false,"message":"Access denied"}`.
4. Otherwise continue.

### 5.7 Endpoint protection map

| Guard | Endpoints |
|---|---|
| None (public) | `GET /`, `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, **all** `/api/category/*`, **all** `/api/product/*`, **all** `/api/banner/*`, **all** `/api/promo-card/*`, `GET /uploads/*` |
| Auth | `GET /api/auth/me`, all six `/api/cart/*` endpoints, `POST /api/order/create`, `GET /api/order/my-orders`, `GET /api/order/my-orders/:id` |
| Auth + Admin | `GET /api/order/all`, `PUT /api/order/status/:id` |

### 5.8 Flows

**Signup:** `POST /api/auth/register` (§6.2.1). Validate, normalize email, reject duplicates, hash the password, create a `user`, issue the cookie, return the user summary. The user is logged in immediately.

**Login:** `POST /api/auth/login` (§6.2.2). Normalize the email, look up the user, compare with bcrypt, issue the cookie, return the user profile. Both failure cases return the same generic message.

**Session check:** `GET /api/auth/me` (§6.2.3).

**Logout:** `POST /api/auth/logout` (§6.2.4). Clears the cookie only. The JWT itself stays valid until it expires.

---

## 6. API Endpoints

### 6.0 Conventions

- All JSON responses use `Content-Type: application/json; charset=utf-8`.
- Responses use one of three envelope styles, depending on the module. Reproduce them exactly:
  - **Style A** (auth, cart, order, banner, promo-card): `{ "success": bool, "message"?: string, <payload key> }`
  - **Style B** (category and product write endpoints): `{ "message": string, "success": bool, "error": bool, "data"?: ... }`
  - **Style C** (category and product list endpoints): `{ "message": string, "data": [...] }`, with **no** `success` or `error` key.
- "Valid ObjectId" in explicit checks means a 24-character hexadecimal string. A non-numeric string of any other length is invalid.
- Where an endpoint passes an id to the database **without** an explicit check, an invalid id causes a database cast error. That surfaces as that endpoint's **500** response (noted per endpoint).
- "Truthy" and "falsy" follow loose-typing semantics: `undefined`, `null`, `""`, `0`, `false` and `NaN` are falsy.
- "Number(x)" means numeric conversion of strings: surrounding whitespace is ignored; `""` → 0; `"abc"` → NaN; `"1e3"` → 1000; `"0x10"` → 16; `true` → 1; `null` → 0; `undefined` → NaN.
- No endpoint reads query parameters. No list endpoint paginates.

### 6.1 Endpoint summary

| # | Method | Path | Guard | Purpose |
|---|---|---|---|---|
| 1 | GET | `/` | — | Health check |
| 2 | POST | `/api/auth/register` | — | Sign up |
| 3 | POST | `/api/auth/login` | — | Log in |
| 4 | GET | `/api/auth/me` | Auth | Current user |
| 5 | POST | `/api/auth/logout` | — | Log out |
| 6 | POST | `/api/category/create-category` | — (should be admin) | Create category (multipart) |
| 7 | GET | `/api/category/get-category` | — | List categories |
| 8 | PUT | `/api/category/update-category/:_id` | — (should be admin) | Update category (multipart) |
| 9 | DELETE | `/api/category/delete-category/:_id` | — (should be admin) | Delete category |
| 10 | POST | `/api/product/create-product` | — (should be admin) | Create product (multipart) |
| 11 | GET | `/api/product/get-product` | — | List products |
| 12 | PUT | `/api/product/update-product/:_id` | — (should be admin) | Update product (multipart) |
| 13 | DELETE | `/api/product/delete-product/:_id` | — (should be admin) | Delete product |
| 14 | GET | `/api/cart` | Auth | Get or create own cart |
| 15 | POST | `/api/cart/add` | Auth | Add product or increase quantity |
| 16 | PUT | `/api/cart/update` | Auth | Set line quantity |
| 17 | DELETE | `/api/cart/remove/:productId` | Auth | Remove line |
| 18 | PUT | `/api/cart/toggle` | Auth | Select or deselect line |
| 19 | DELETE | `/api/cart/clear` | Auth | Empty cart |
| 20 | POST | `/api/order/create` | Auth | Place order |
| 21 | GET | `/api/order/my-orders` | Auth | List own orders |
| 22 | GET | `/api/order/my-orders/:id` | Auth | Own order detail |
| 23 | GET | `/api/order/all` | Auth + Admin | List all orders |
| 24 | PUT | `/api/order/status/:id` | Auth + Admin | Change order status |
| 25 | POST | `/api/banner/create-banner` | — (should be admin) | Create banner (multipart) |
| 26 | GET | `/api/banner/get-banner` | — | Active banners |
| 27 | GET | `/api/banner/get-all-banner` | — (should be admin) | All banners |
| 28 | DELETE | `/api/banner/delete-banner/:id` | — (should be admin) | Delete banner |
| 29 | POST | `/api/promo-card/create-promo-card` | — (should be admin) | Create promo card (multipart) |
| 30 | GET | `/api/promo-card/get-promo-card` | — | Active promo cards |
| 31 | GET | `/api/promo-card/get-all-promo-card` | — (should be admin) | All promo cards |
| 32 | DELETE | `/api/promo-card/delete-promo-card/:id` | — (should be admin) | Delete promo card |
| 33 | GET | `/uploads/<filename>` | — | Static uploaded file |

"Should be admin" records what the comments in the code and the frontend's usage intend. The server does **not** enforce it (KI-01).

---

### 6.1.1 `GET /` (health check)

- **Auth:** none.
- **Logic:** none.
- **Response 200:**

```json
{ "msg": "api is working" }
```

---

### 6.2 Auth module (`/api/auth`)

#### 6.2.1 `POST /api/auth/register`

- **Auth:** none.
- **Content type:** `application/json` (URL-encoded also works).

| Body field | Type | Required | Rules |
|---|---|---|---|
| `name` | string | yes | Must be truthy. Trimmed before storing. |
| `email` | string | yes | Must be truthy. Trimmed and lower-cased. Format not validated. |
| `password` | string | yes | Must be truthy and `length >= 6` |
| `phone` | string | no | Trimmed. Stored as `""` if absent or empty. |
| any other field (e.g. `role`) | — | — | Ignored. The role is always `"user"`. |

**Logic:**

1. If `name`, `email` or `password` is falsy, respond 400.
2. If `password.length < 6`, respond 400. If `password` is not a string (e.g. a JSON number), `length` is undefined and this check passes; hashing then fails and the request gets the 500 response.
3. Set `normalizedEmail = email.trim().toLowerCase()`. If `email` is not a string, the request gets the 500 response.
4. Find a user where `email == normalizedEmail`. If one exists, respond 409.
5. Hash the password with bcrypt, cost 10.
6. Insert into `users`: `{name: name.trim(), email: normalizedEmail, phone: phone?.trim() || "", password: <hash>, role: "user"}`. Defaults fill `address`, `city` and `pincode` with `""`. A whitespace-only `name` becomes `""` and fails the schema "required" rule, which returns the 500 response.
7. Create a JWT for the new `_id` and set the `accessToken` cookie (§5.4).
8. Respond 201.

**Success 201** (no `address`, `city` or `pincode` in this response):

```json
{
  "success": true,
  "message": "Account created successfully",
  "user": {
    "id": "66fa1c2b9d3e4a0012ab34cd",
    "name": "Asha Verma",
    "email": "asha@example.com",
    "phone": "9876543210",
    "role": "user"
  }
}
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| name, email or password missing or falsy | 400 | `{"success":false,"message":"Name, email and password are required"}` |
| password shorter than 6 characters | 400 | `{"success":false,"message":"Password must be at least 6 characters"}` |
| email already registered | 409 | `{"success":false,"message":"Email already registered"}` |
| any exception: non-string inputs, validation failure, duplicate-key race, database error | 500 | `{"success":false,"message":"Registration failed"}`. The server logs `Register Error:` plus the error. |

#### 6.2.2 `POST /api/auth/login`

- **Auth:** none.

| Body field | Type | Required |
|---|---|---|
| `email` | string | yes (truthy) |
| `password` | string | yes (truthy) |

**Logic:**

1. If either field is falsy, respond 400.
2. Normalize the email (trim, lowercase) and find the user by email. If none is found, respond 401.
3. Compare the password with the stored hash using bcrypt. On mismatch, respond 401.
4. Issue the JWT and set the cookie (§5.3, §5.4).
5. Respond 200.

**Success 200:**

```json
{
  "success": true,
  "message": "Login successful",
  "user": {
    "id": "66fa1c2b9d3e4a0012ab34cd",
    "name": "Asha Verma",
    "email": "asha@example.com",
    "phone": "9876543210",
    "address": "",
    "city": "",
    "pincode": "",
    "role": "user"
  }
}
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| email or password falsy | 400 | `{"success":false,"message":"Email and password are required"}` |
| no user with that email | 401 | `{"success":false,"message":"Invalid email or password"}` |
| wrong password | 401 | `{"success":false,"message":"Invalid email or password"}` |
| exception (e.g. non-string email or password, database error) | 500 | `{"success":false,"message":"Login failed"}`. The server logs `Login Error:`. |

#### 6.2.3 `GET /api/auth/me`

- **Auth:** authentication guard (§5.5). The guard's 401 responses apply.
- **Logic:** return the current user loaded by the guard.

**Success 200:** same `user` shape as login, without `message`:

```json
{
  "success": true,
  "user": {
    "id": "66fa1c2b9d3e4a0012ab34cd",
    "name": "Asha Verma",
    "email": "asha@example.com",
    "phone": "9876543210",
    "address": "",
    "city": "",
    "pincode": "",
    "role": "admin"
  }
}
```

**Errors:** the guard's 401s. On an exception: 500 `{"success":false,"message":"Unable to get user"}`.

#### 6.2.4 `POST /api/auth/logout`

- **Auth:** none. Works with or without a cookie.
- **Body:** none.
- **Logic:** send a cookie-clearing header for `accessToken` with `HttpOnly`, `Secure=false`, `SameSite=Lax` and `Path=/`. There is no server-side token invalidation.

**Success 200:**

```json
{ "success": true, "message": "Logout successful" }
```

**Errors:** on an exception, 500 `{"success":false,"message":"Logout failed"}`. This is practically unreachable.

---

### 6.3 Category module (`/api/category`)

All write endpoints are **unauthenticated** (KI-01). Uploads follow §7: form field `image`, a single file.

#### 6.3.1 `POST /api/category/create-category`

- **Content type:** `multipart/form-data`

| Field | Type | Required | Rules |
|---|---|---|---|
| `name` | text | yes | Must be non-empty after trimming |
| `description` | text | no | Trimmed. Stored as `""` if absent. |
| `image` | file | yes | One file, see §7 for allowed types and size |

**Logic:**

1. The upload step stores the file in `uploads/` first (§7). Upload-stage errors return the generic 500 HTML response (§11).
2. If `name` is missing or blank after trimming, respond 400.
3. If no file was uploaded, respond 400.
4. Find a category with `name == name.trim()` (exact, case-sensitive). If one exists, respond 409.
5. Insert `{name: trimmed, description: description?.trim() || "", image: "/uploads/<storedFilename>"}`.
6. Respond 201.
7. On 400 or 409 after a file was uploaded, the uploaded file is **not** deleted (KI-08).

**Success 201:**

```json
{
  "message": "Category created successfully",
  "success": true,
  "error": false,
  "data": {
    "_id": "66fa1d009d3e4a0012ab3500",
    "name": "Jar Candles",
    "description": "Soy wax candles in glass jars",
    "image": "/uploads/1790670860904-253178900.png",
    "createdAt": "2026-09-30T10:05:00.000Z",
    "updatedAt": "2026-09-30T10:05:00.000Z",
    "__v": 0
  }
}
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| name missing or blank | 400 | `{"message":"Category name is required","success":false,"error":true}` |
| no image file | 400 | `{"message":"Please upload an image","success":false,"error":true}` |
| name already exists | 409 | `{"message":"Category already exists","success":false,"error":true}` |
| any exception (including a duplicate-key race) | 500 | `{"message":"<raw error message>","success":false,"error":true}`. The server logs `Create category error:`. |
| upload rejected (type, size, wrong field name) | 500 | default HTML error page (§11) |

#### 6.3.2 `GET /api/category/get-category`

- **Auth:** none. **Body:** none.
- **Logic:**
  1. Read **all** documents from `categories`, with no filter and no explicit sort, so natural or insertion order. Each `_id` is converted to its string form, which serializes the same as before.
  2. Respond 200. Note the envelope: no `success` key.

**Success 200:**

```json
{
  "message": "categories fetched successfully",
  "data": [
    {
      "_id": "66fa1d009d3e4a0012ab3500",
      "name": "Jar Candles",
      "description": "Soy wax candles in glass jars",
      "image": "/uploads/1790670860904-253178900.png",
      "createdAt": "2026-09-30T10:05:00.000Z",
      "updatedAt": "2026-09-30T10:05:00.000Z",
      "__v": 0
    }
  ]
}
```

An empty collection returns `"data": []` with status 200.

**Errors:**

| Condition | Status | Body |
|---|---|---|
| (unreachable) result not an array | 404 | `{"message":"category not found","success":false}` |
| database error | 500 | `{"message":"<error message>","error":true,"success":false}` |

#### 6.3.3 `PUT /api/category/update-category/:_id`

- **Path param:** `_id`, the category id.
- **Content type:** `multipart/form-data` (JSON is also accepted when no image is sent).

| Field | Type | Required | Rules |
|---|---|---|---|
| `name` | text | no | If present, it must be a string that is non-blank after trimming, and unique among other categories |
| `description` | text | no | If present: trimmed if it is a string, otherwise stored as `""` |
| `image` | file | no | Replaces the current image |

**Logic.** In every early-return failure listed in steps 1–4 and in the exception handler, a newly uploaded file is deleted:

1. If `_id` is not a valid ObjectId, respond 400.
2. Find the category by `_id`. If it is not found, respond 404.
3. If `name` is present (`!== undefined`):
   - If it is not a string or is blank after trimming, respond 400.
   - Look for another category (`_id ≠ :_id`) with exactly `name.trim()`. If one exists, respond 409.
   - Set `name = trimmed`.
4. If `description` is present, set it to `description.trim()` if it is a string, otherwise `""`.
5. Remember `oldImage`. If a file was uploaded, set `image = "/uploads/<newFile>"`.
6. Save. This refreshes `updatedAt`.
7. If a new image was uploaded and it differs from `oldImage`, delete the old file (§7.4 rules: only if it starts with `/uploads/`; a missing file is ignored).
8. Respond 200.

**Success 200:**

```json
{
  "message": "Category updated successfully",
  "success": true,
  "error": false,
  "data": { "_id": "66fa1d009d3e4a0012ab3500", "name": "Jar Candles", "description": "...", "image": "/uploads/1790916574293-4883898.jpg", "createdAt": "...", "updatedAt": "...", "__v": 0 }
}
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| invalid `_id` | 400 | `{"message":"Invalid category ID","success":false,"error":true}` |
| not found | 404 | `{"message":"Category not found","success":false,"error":true}` |
| `name` present but not a string or blank | 400 | `{"message":"Category name is required","success":false,"error":true}` |
| name duplicates another category | 409 | `{"message":"Category already exists","success":false,"error":true}` |
| database duplicate-key error (code 11000) on save | 409 | `{"message":"Category already exists","success":false,"error":true}` |
| schema validation error on save | 400 | `{"message":"<validation message>","success":false,"error":true}` |
| other exception | 500 | `{"message":"Internal server error","success":false,"error":true}`. The server logs `Update category error:`. |
| upload rejected | 500 | default HTML error page (§11) |

#### 6.3.4 `DELETE /api/category/delete-category/:_id`

- **Path param:** `_id`.

**Logic:**

1. If `_id` is not a valid ObjectId, respond 400.
2. Find the category. If it is not found, respond 404.
3. If **any** product has `category == _id`, respond 409. This blocks deletion.
4. Delete the category document.
5. Delete its image file (§7.4).
6. Respond 200 with the deleted document.

**Success 200:**

```json
{
  "message": "Category deleted successfully",
  "success": true,
  "error": false,
  "data": { "_id": "66fa1d009d3e4a0012ab3500", "name": "Jar Candles", "description": "...", "image": "/uploads/...", "createdAt": "...", "updatedAt": "...", "__v": 0 }
}
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| invalid `_id` | 400 | `{"message":"Invalid category ID","success":false,"error":true}` |
| not found | 404 | `{"message":"Category not found","success":false,"error":true}` |
| category has products | 409 | `{"message":"This category contains products. Delete or reassign those products first.","success":false,"error":true}` |
| exception | 500 | `{"message":"Internal server error","success":false,"error":true}`. The server logs `Delete category error:`. |

---

### 6.4 Product module (`/api/product`)

All write endpoints are **unauthenticated** (KI-01).

#### 6.4.1 `POST /api/product/create-product`

- **Content type:** `multipart/form-data`

| Field | Type | Required | Rules |
|---|---|---|---|
| `name` | text | yes | Non-blank after trimming |
| `category` | text | yes | Valid ObjectId of an existing category |
| `price` | text/number | yes | Not `""`. `Number(price)` must be finite and `>= 1`. Decimals allowed. |
| `oldPrice` | text/number | no | If present and not `""`, `Number(oldPrice)` must be finite and `>= 1`. **Not compared with price on create.** |
| `stock` | text/number | yes | Not `""`. `Number(stock)` must be an integer `>= 0`. |
| `description` | text | no | Trimmed. Stored as `""` if absent. |
| `image` | file | yes | §7 |

**Logic.** Checks run in this order:

1. If `name` is missing or blank, `category` is falsy, `price` is undefined or `""`, or `stock` is undefined or `""`, respond 400 "Name, category, price and stock are required".
2. If no file was uploaded, respond 400 "Please upload an image".
3. If `category` is not a valid ObjectId, respond 400 "Invalid category ID".
4. If the category doesn't exist, respond 404 "Category not found".
5. Validate the numbers. If any rule in the table fails, respond 400 "Invalid price, old price or stock".
6. If a product exists with exactly `name.trim()` **and** the same `category`, respond 409.
7. Insert `{name: trimmed, category, price: Number(price), oldPrice: Number(oldPrice) (only if supplied and not ""), stock: Number(stock), description: description?.trim() || "", image: "/uploads/<file>"}`.
8. Respond 201.
9. On any failure after the upload, the uploaded file is **not** deleted (KI-08).

**Success 201:**

```json
{
  "message": "Product created successfully",
  "success": true,
  "error": false,
  "data": {
    "_id": "66fa1e119d3e4a0012ab3601",
    "name": "Lavender Jar Candle",
    "category": "66fa1d009d3e4a0012ab3500",
    "price": 499,
    "oldPrice": 699,
    "stock": 25,
    "description": "Hand-poured lavender soy candle",
    "image": "/uploads/1790698202524-11481566.png",
    "createdAt": "2026-09-30T10:10:00.000Z",
    "updatedAt": "2026-09-30T10:10:00.000Z",
    "__v": 0
  }
}
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| required field missing | 400 | `{"message":"Name, category, price and stock are required","success":false,"error":true}` |
| no image | 400 | `{"message":"Please upload an image","success":false,"error":true}` |
| invalid category id | 400 | `{"message":"Invalid category ID","success":false,"error":true}` |
| category not found | 404 | `{"message":"Category not found","success":false,"error":true}` |
| bad price, oldPrice or stock | 400 | `{"message":"Invalid price, old price or stock","success":false,"error":true}` |
| duplicate (same name and category) | 409 | `{"message":"Product already exists","success":false,"error":true}` |
| schema validation exception | 400 | `{"message":"<validation message>","success":false,"error":true}` |
| other exception (e.g. non-string `name` in a JSON body) | 500 | `{"message":"Internal server error","success":false,"error":true}`. The server logs `Create Product error:`. |
| upload rejected | 500 | default HTML error page (§11) |

#### 6.4.2 `GET /api/product/get-product`

- **Logic:** return **all** products, with no filter, sort, pagination or category population. `category` is a plain id string. `_id` is converted to a string.

**Success 200:**

```json
{
  "message": "products fetched successfully",
  "data": [
    {
      "_id": "66fa1e119d3e4a0012ab3601",
      "name": "Lavender Jar Candle",
      "category": "66fa1d009d3e4a0012ab3500",
      "price": 499,
      "oldPrice": 699,
      "stock": 25,
      "description": "Hand-poured lavender soy candle",
      "image": "/uploads/1790698202524-11481566.png",
      "createdAt": "2026-09-30T10:10:00.000Z",
      "updatedAt": "2026-09-30T10:10:00.000Z",
      "__v": 0
    }
  ]
}
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| (unreachable) | 404 | `{"message":"products not found","success":false}` |
| database error | 500 | `{"message":"<error message>","error":true,"success":false}` |

#### 6.4.3 `PUT /api/product/update-product/:_id`

- **Path param:** `_id`.
- **Content type:** `multipart/form-data` (JSON accepted when no image is sent). Every field is optional. A field is "present" when it is not `undefined`.

| Field | Rule when present |
|---|---|
| `name` | Must be non-blank after trimming. It is stored trimmed. **The duplicate check from create is not applied.** |
| `category` | Must be a valid ObjectId and an existing category |
| `price` | Not `""`. Finite and `>= 1`. |
| `oldPrice` | `""` **removes** the field. Otherwise it must be finite and `>= 1`. |
| `stock` | Not `""`. An integer `>= 0`. |
| `description` | Stored trimmed. A non-string value returns the 500 response. |
| `image` | Replaces the image |

**Logic.** Checks run in this order, and each failure returns immediately:

1. If `_id` is not a valid ObjectId, respond 400 "Invalid product ID".
2. Find the product. If it is not found, respond 404 "Product not found".
3. `name`: if present and blank, respond 400 "Product name is required". Otherwise set it.
4. `category`: if invalid, respond 400 "Invalid category ID". If it doesn't exist, respond 404 "Category not found". Otherwise set it.
5. `price`: if invalid, respond 400 "Invalid price". Otherwise set it.
6. `oldPrice`: `""` unsets it. If invalid, respond 400 "Invalid old price". Otherwise set it.
7. **Cross-field check** on the resulting values: if `oldPrice` is set and `oldPrice < price`, respond 400 "Old price cannot be less than price". This applies even if the request didn't touch these fields. Equal values are allowed.
8. `stock`: if invalid, respond 400 "Invalid stock". Otherwise set it.
9. `description`: set to the trimmed value.
10. If a file was uploaded, set `image = "/uploads/<newFile>"`.
11. Save.
12. If a new file was uploaded and the image changed, delete the old image file (§7.4).
13. Respond 200.
14. **On the 400 and 404 early returns in steps 1–8, a newly uploaded file is not deleted (KI-08).** In the exception handler it **is** deleted.

**Success 200:**

```json
{
  "message": "Product updated successfully",
  "success": true,
  "error": false,
  "data": { "_id": "66fa1e119d3e4a0012ab3601", "name": "Lavender Jar Candle", "category": "66fa1d009d3e4a0012ab3500", "price": 549, "oldPrice": 699, "stock": 20, "description": "...", "image": "/uploads/...", "createdAt": "...", "updatedAt": "...", "__v": 0 }
}
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| invalid `_id` | 400 | `{"message":"Invalid product ID","success":false,"error":true}` |
| product not found | 404 | `{"message":"Product not found","success":false,"error":true}` |
| blank name | 400 | `{"message":"Product name is required","success":false,"error":true}` |
| invalid category id | 400 | `{"message":"Invalid category ID","success":false,"error":true}` |
| category not found | 404 | `{"message":"Category not found","success":false,"error":true}` |
| invalid price | 400 | `{"message":"Invalid price","success":false,"error":true}` |
| invalid oldPrice | 400 | `{"message":"Invalid old price","success":false,"error":true}` |
| oldPrice < price | 400 | `{"message":"Old price cannot be less than price","success":false,"error":true}` |
| invalid stock | 400 | `{"message":"Invalid stock","success":false,"error":true}` |
| any exception, including schema validation (e.g. non-string `name` gives `"name.trim is not a function"`) | 500 | `{"message":"<raw error message>","success":false,"error":true}` |
| upload rejected | 500 | default HTML error page (§11) |

#### 6.4.4 `DELETE /api/product/delete-product/:_id`

**Logic:**

1. If `_id` is not a valid ObjectId, respond 400.
2. Find and delete the product in one operation. If it is not found, respond 404.
3. Delete its image file (§7.4).
4. Respond 200. Carts and orders that reference the product are **not** touched; their populated `product` becomes `null`.

**Success 200** (no `data`):

```json
{ "message": "Product deleted successfully", "success": true, "error": false }
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| invalid id | 400 | `{"message":"Invalid product ID","success":false,"error":true}` |
| not found | 404 | `{"message":"Product not found","success":false,"error":true}` |
| exception | 500 | `{"message":"<error message>","success":false,"error":true}` |

---

### 6.5 Cart module (`/api/cart`)

All cart endpoints require **authentication** (§5.5) and operate only on the current user's cart. In every cart response, "populated cart" means the full cart document with `items[].product` replaced by the full product document, or `null` if the product no longer exists. `user` stays an id string.

Item matching rule: a cart line matches when the string form of its `product` id is **exactly equal** to the supplied `productId` string.

#### 6.5.1 `GET /api/cart`

**Logic:**

1. Find the cart for the current user and populate it.
2. If none exists, insert `{user, items: []}` and read it back populated.
3. Respond 200.

**Success 200:**

```json
{
  "success": true,
  "cart": {
    "_id": "66fa20009d3e4a0012ab3700",
    "user": "66fa1c2b9d3e4a0012ab34cd",
    "items": [
      {
        "product": {
          "_id": "66fa1e119d3e4a0012ab3601",
          "name": "Lavender Jar Candle",
          "category": "66fa1d009d3e4a0012ab3500",
          "price": 499,
          "oldPrice": 699,
          "stock": 25,
          "description": "Hand-poured lavender soy candle",
          "image": "/uploads/1790698202524-11481566.png",
          "createdAt": "2026-09-30T10:10:00.000Z",
          "updatedAt": "2026-09-30T10:10:00.000Z",
          "__v": 0
        },
        "quantity": 2,
        "selected": true
      }
    ],
    "createdAt": "2026-09-30T11:00:00.000Z",
    "updatedAt": "2026-09-30T11:05:00.000Z",
    "__v": 1
  }
}
```

**Errors:** the guard's 401s. On an exception: 500 `{"success":false,"message":"Unable to get cart"}`.

#### 6.5.2 `POST /api/cart/add`

| Body field | Type | Required | Default | Rules |
|---|---|---|---|---|
| `productId` | string | yes | — | An existing product id |
| `quantity` | number/string | no | `1` | `Number(quantity) >= 1`. Non-integers are accepted. |

**Logic:**

1. If `productId` is falsy, respond 400.
2. Find the product by id. If it is not found, respond 404. An invalid id format causes a cast error, which returns the 500 response.
3. Set `qty = Number(quantity)`. If `qty < 1`, respond 400. A `NaN` value passes this check, then fails at save with the 500 response.
4. If `qty > product.stock`, respond 400 `Only <stock> items available`.
5. Load the user's cart, creating an empty one if needed.
6. If a line for this product exists:
   - Set `newQuantity = line.quantity + qty`. If `newQuantity > product.stock`, respond 400 `Only <stock> items available`.
   - Otherwise set `line.quantity = newQuantity` and `line.selected = true`.
7. Otherwise append `{product: productId, quantity: qty, selected: true}`.
8. Save, re-read the cart populated, and respond 200.

Stock is only **checked**, never reserved or decremented.

**Success 200:**

```json
{ "success": true, "message": "Product added to cart", "cart": { "...populated cart...": "" } }
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| no productId | 400 | `{"success":false,"message":"Product ID is required"}` |
| product not found | 404 | `{"success":false,"message":"Product not found"}` |
| qty < 1 | 400 | `{"success":false,"message":"Quantity must be at least 1"}` |
| qty, or existing + qty, exceeds stock | 400 | `{"success":false,"message":"Only 5 items available"}` (the number is the current `stock`) |
| exception (invalid id format, NaN quantity, database error) | 500 | `{"success":false,"message":"Unable to add product"}` |

#### 6.5.3 `PUT /api/cart/update`

| Body field | Type | Required | Rules |
|---|---|---|---|
| `productId` | string | yes | Must already be in the cart |
| `quantity` | number/string | yes | `Number(quantity) >= 1`. This **sets** the quantity; it does not add to it. |

**Logic:**

1. Set `qty = Number(quantity)`. If `productId` is falsy or `qty < 1`, respond 400. A missing or non-numeric `quantity` gives `NaN`, which passes this check and then fails at save with the 500 response.
2. Find the user's cart. If it doesn't exist, respond 404. **The cart is not auto-created here.**
3. Find the line. If it is not found, respond 404.
4. Load the product. If it exists and `qty > product.stock`, respond 400. If the product was deleted, the stock check is skipped.
5. Set `line.quantity = qty`. The `selected` flag is unchanged.
6. Save, re-read populated, and respond 200.

**Success 200:**

```json
{ "success": true, "message": "Cart updated", "cart": { "...populated cart...": "" } }
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| missing productId or qty < 1 | 400 | `{"success":false,"message":"Invalid cart data"}` |
| no cart | 404 | `{"success":false,"message":"Cart not found"}` |
| product not in cart | 404 | `{"success":false,"message":"Product not found in cart"}` |
| exceeds stock | 400 | `{"success":false,"message":"Only <stock> items available"}` |
| exception | 500 | `{"success":false,"message":"Unable to update cart"}` |

#### 6.5.4 `DELETE /api/cart/remove/:productId`

- **Path param:** `productId`.

**Logic:**

1. Find the user's cart. If it doesn't exist, respond 404.
2. Remove every line whose product id equals `productId`. If no line matches, nothing changes and the request still succeeds.
3. Save, re-read populated, and respond 200.

**Success 200:**

```json
{ "success": true, "message": "Product removed", "cart": { "...populated cart...": "" } }
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| no cart | 404 | `{"success":false,"message":"Cart not found"}` |
| exception | 500 | `{"success":false,"message":"Unable to remove product"}` |

#### 6.5.5 `PUT /api/cart/toggle`

| Body field | Type | Required | Rules |
|---|---|---|---|
| `productId` | string | yes (implicitly) | Must be in the cart |
| `selected` | boolean | no | **Only the JSON boolean `false` deselects.** Every other value, including missing, `"false"` or `0`, selects. |

**Logic:**

1. Find the user's cart. If it doesn't exist, respond 404.
2. Find the line. If it is not found (including when `productId` is missing), respond 404.
3. Set `line.selected = (selected !== false)`.
4. Save, re-read populated, and respond 200.

**Success 200:**

```json
{ "success": true, "message": "Selection updated", "cart": { "...populated cart...": "" } }
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| no cart | 404 | `{"success":false,"message":"Cart not found"}` |
| line not found | 404 | `{"success":false,"message":"Product not found in cart"}` |
| exception | 500 | `{"success":false,"message":"Unable to update selection"}` |

#### 6.5.6 `DELETE /api/cart/clear`

**Logic:**

1. Find the user's cart. If it doesn't exist, respond 200 "Cart already empty" **without a `cart` key**.
2. Otherwise set `items = []`, save, and respond 200 with the saved cart. It is **not** re-read populated, and `items` is `[]`.

**Success 200 (cart existed):**

```json
{
  "success": true,
  "message": "Cart cleared",
  "cart": {
    "_id": "66fa20009d3e4a0012ab3700",
    "user": "66fa1c2b9d3e4a0012ab34cd",
    "items": [],
    "createdAt": "2026-09-30T11:00:00.000Z",
    "updatedAt": "2026-10-02T09:20:00.000Z",
    "__v": 2
  }
}
```

**Success 200 (no cart):**

```json
{ "success": true, "message": "Cart already empty" }
```

**Errors:** on an exception, 500 `{"success":false,"message":"Unable to clear cart"}`.

---

### 6.6 Order module (`/api/order`)

#### 6.6.1 `POST /api/order/create`

- **Auth:** authentication guard.
- **Content type:** `application/json`.

| Body field | Type | Required | Default | Rules |
|---|---|---|---|---|
| `customer` | object | yes | — | — |
| `customer.name` | string | yes | — | Truthy. Trimmed. |
| `customer.mobile` | string | yes | — | Truthy. Trimmed. **Must be a string**: a JSON number gives the 500 response. |
| `customer.address` | string | yes | — | Truthy. Trimmed. |
| `customer.city` | string | yes | — | Truthy. Trimmed. |
| `customer.pincode` | string | yes | — | Truthy. Trimmed. Must be a string. |
| `customer.message` | string | no | `""` | Trimmed |
| `items` | array | yes | — | Non-empty |
| `items[].product` or `items[].productId` | string | yes | — | `product` takes precedence. Must be a castable ObjectId. Existence is **not** checked. |
| `items[].name` | string | yes | — | Truthy |
| `items[].image` | string | no | `""` | — |
| `items[].price` | number | no | `0` | `Number(price \|\| 0)` |
| `items[].quantity` | number | no | `1` | `Number(quantity \|\| 1)`. Must be > 0. |
| `itemsTotal` | number | effectively | `0` | `Number(itemsTotal \|\| 0)`. **Trusted from the client.** |
| `shipping` | number | no | `0` | `Number(shipping \|\| 0)` |
| `shippingStatus` | string | no | `"FREE"` | `"FREE"` or `"PAYABLE_SEPARATELY"`. Any other string gives the 500 response. |
| `grandTotal` | number | effectively | `0` | `Number(grandTotal \|\| 0)`. **Trusted from the client.** |
| `paymentMethod` | string | no | `"WhatsApp Order"` | Free text |

Example request:

```json
{
  "customer": {
    "name": "Asha Verma",
    "mobile": "9876543210",
    "address": "12 MG Road",
    "city": "Jaipur",
    "pincode": "302001",
    "message": "Please gift wrap"
  },
  "items": [
    {
      "product": "66fa1e119d3e4a0012ab3601",
      "name": "Lavender Jar Candle",
      "image": "/uploads/1790698202524-11481566.png",
      "price": 499,
      "quantity": 2
    }
  ],
  "itemsTotal": 998,
  "shipping": 0,
  "shippingStatus": "FREE",
  "grandTotal": 998,
  "paymentMethod": "WhatsApp Order"
}
```

**Logic:**

1. If `customer` is missing, or any of `name`, `mobile`, `address`, `city` or `pincode` is falsy, respond 400.
2. If `items` is not an array or is empty, respond 400.
3. Normalize each item to `{product: item.product || item.productId, name: item.name, image: item.image || "", price: Number(item.price || 0), quantity: Number(item.quantity || 1), total: price * quantity}`. A client-sent `total` is ignored.
4. If any normalized item has a falsy `product`, a falsy `name`, or `quantity <= 0`, respond 400. A `NaN` quantity passes this check and fails at save with the 500 response.
5. Generate `orderId = "AKRF-" + <current epoch ms> + "-" + <random integer 1000–9999>`.
6. Set `orderDate = now`, and `expectedDelivery = orderDate + 3 calendar days` (server local time, same wall-clock time).
7. Insert the order with: `orderId`, `user = currentUser._id`, the trimmed `customer` fields (`message` trimmed or `""`), the normalized items, `itemsTotal`, `shipping`, `shippingStatus`, `grandTotal`, `paymentMethod`, `status: "Pending"`, `statusDates: {Pending: orderDate, others: null}` and `expectedDelivery`.
8. **Cart cleanup:** if the user has a cart, remove every cart line whose product id appears in the order items, **whether or not the line is selected**, then save.
9. Re-read the order, populating `items.product` (full product or `null`) and `user` (all fields except `password`).
10. Respond 201.

**No** price verification against products, **no** totals recalculation, **no** stock check or decrement, **no** notification.

**Success 201:**

```json
{
  "success": true,
  "message": "Order created successfully",
  "order": {
    "_id": "66fa30009d3e4a0012ab3800",
    "orderId": "AKRF-1790700056594-4821",
    "user": {
      "_id": "66fa1c2b9d3e4a0012ab34cd",
      "name": "Asha Verma",
      "email": "asha@example.com",
      "phone": "9876543210",
      "address": "",
      "city": "",
      "pincode": "",
      "role": "user",
      "createdAt": "2026-09-30T10:00:00.000Z",
      "updatedAt": "2026-09-30T10:00:00.000Z",
      "__v": 0
    },
    "customer": { "name": "Asha Verma", "mobile": "9876543210", "address": "12 MG Road", "city": "Jaipur", "pincode": "302001", "message": "Please gift wrap" },
    "items": [
      {
        "product": { "...full product object or null...": "" },
        "name": "Lavender Jar Candle",
        "image": "/uploads/1790698202524-11481566.png",
        "price": 499,
        "quantity": 2,
        "total": 998
      }
    ],
    "itemsTotal": 998,
    "shipping": 0,
    "shippingStatus": "FREE",
    "grandTotal": 998,
    "paymentMethod": "WhatsApp Order",
    "status": "Pending",
    "statusDates": { "Pending": "2026-10-02T09:15:27.481Z", "Confirmed": null, "Processing": null, "Shipped": null, "Delivered": null, "Cancelled": null },
    "expectedDelivery": "2026-10-05T09:15:27.481Z",
    "createdAt": "2026-10-02T09:15:27.490Z",
    "updatedAt": "2026-10-02T09:15:27.490Z",
    "__v": 0
  }
}
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| customer details incomplete | 400 | `{"success":false,"message":"Please provide complete customer details"}` |
| items missing, not an array, or empty | 400 | `{"success":false,"message":"At least one product is required"}` |
| an item lacks product or name, or has quantity <= 0 | 400 | `{"success":false,"message":"Invalid order product data"}` |
| any exception (non-string customer fields, invalid enum, uncastable product id, NaN numbers, database error) | 500 | `{"success":false,"message":"Unable to create order","error":"<raw error message>"}` |

#### 6.6.2 `GET /api/order/my-orders`

- **Auth:** authentication guard.
- **Logic:** find all orders where `user == currentUser._id`, populate `items.product`, sort `createdAt` descending. `user` is **not** populated.

**Success 200:**

```json
{
  "success": true,
  "orders": [
    { "_id": "66fa30009d3e4a0012ab3800", "orderId": "AKRF-1790700056594-4821", "user": "66fa1c2b9d3e4a0012ab34cd", "customer": { "...": "" }, "items": [ { "product": { "...": "" }, "name": "...", "image": "...", "price": 499, "quantity": 2, "total": 998 } ], "itemsTotal": 998, "shipping": 0, "shippingStatus": "FREE", "grandTotal": 998, "paymentMethod": "WhatsApp Order", "status": "Pending", "statusDates": { "...": "" }, "expectedDelivery": "...", "createdAt": "...", "updatedAt": "...", "__v": 0 }
  ]
}
```

**Errors:** the guard's 401s. On an exception: 500 `{"success":false,"message":"Unable to get orders"}`.

#### 6.6.3 `GET /api/order/my-orders/:id`

- **Auth:** authentication guard.
- **Path param:** `id`, the order's **`_id`**, not `orderId`.
- **Logic:** find one order with `_id == id` **and** `user == currentUser._id`, then populate `items.product`. `user` is not populated.

**Success 200:**

```json
{ "success": true, "order": { "...order object, user as id string...": "" } }
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| not found, or belongs to another user | 404 | `{"success":false,"message":"Order not found"}` |
| invalid id format, or other exception | 500 | `{"success":false,"message":"Unable to get order details"}` |

#### 6.6.4 `GET /api/order/all`

- **Auth:** authentication guard plus admin guard.
- **Logic:** find all orders, populate `user` (without `password`) and `items.product`, sort `createdAt` descending. No pagination or filters.

**Success 200:**

```json
{ "success": true, "orders": [ { "...order object with user populated...": "" } ] }
```

**Errors:** guard 401 and 403 responses. On an exception: 500 `{"success":false,"message":"Unable to get orders"}`.

#### 6.6.5 `PUT /api/order/status/:id`

- **Auth:** authentication guard plus admin guard.
- **Path param:** `id`, the order `_id`.

| Body field | Type | Required | Rules |
|---|---|---|---|
| `status` | string | yes | One of `Pending`, `Confirmed`, `Processing`, `Shipped`, `Delivered`, `Cancelled` (case-sensitive) |

**Logic:**

1. If `status` is not in the allowed list, respond 400.
2. Find the order by id. If it is not found, respond 404. An invalid id format gives the 500 response.
3. Set `now = current time`.
4. Set `order.status = status`. **Any transition is allowed**, including backwards moves, re-opening a cancelled order, or setting the same status again.
5. Set `order.statusDates[status] = now`. This overwrites any earlier date for that status. Dates for other statuses are kept unchanged.
6. If `status == "Cancelled"`, set `expectedDelivery = null`.
7. If `status != "Cancelled"` and `expectedDelivery` is null, set `expectedDelivery = now + 3 calendar days`. If it is already set, it is kept.
8. Save, re-read with `items.product` and `user` (without `password`) populated, and respond 200.

There are no stock changes and no notifications.

**Success 200:**

```json
{
  "success": true,
  "message": "Order status changed to Shipped",
  "order": { "...order object with user populated...": "" }
}
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| status missing or not allowed | 400 | `{"success":false,"message":"Invalid order status"}` |
| order not found | 404 | `{"success":false,"message":"Order not found"}` |
| exception (invalid id format, etc.) | 500 | `{"success":false,"message":"Unable to update order status","error":"<raw error message>"}` |

---

### 6.7 Banner module (`/api/banner`)

All endpoints are **unauthenticated** (KI-01).

#### 6.7.1 `POST /api/banner/create-banner`

- **Content type:** `multipart/form-data`

| Field | Type | Required | Default | Rules |
|---|---|---|---|---|
| `title` | text | yes | — | Truthy. Trimmed by the schema. Whitespace-only text passes the handler check but fails schema "required", giving the 500 response. |
| `subtitle` | text | no | `""` | Trimmed |
| `buttonText` | text | no | `"Shop Now"` | Falsy values use the default |
| `buttonLink` | text | no | `"/shop"` | Falsy values use the default |
| `order` | text/number | no | `0` | `Number(order) \|\| 0`, so NaN becomes 0 |
| `status` | text/bool | no | `true` | Undefined gives `true`. `"true"` or `true` gives `true`. **Anything else gives `false`.** |
| `image` | file | yes | — | §7 |

**Logic:**

1. If `title` is falsy, respond 400.
2. If there is no file, respond 400.
3. Insert the banner with the values above and `image = "/uploads/<file>"`.
4. Respond 201.
5. On a 400 after upload, the file is not deleted.

**Success 201:**

```json
{
  "success": true,
  "message": "Banner created successfully",
  "data": {
    "_id": "66fa40009d3e4a0012ab3900",
    "title": "Festive Collection",
    "subtitle": "Up to 30% off",
    "image": "/uploads/1790700080917-344934455.jpeg",
    "buttonText": "Shop Now",
    "buttonLink": "/shop",
    "order": 0,
    "status": true,
    "createdAt": "2026-10-01T08:00:00.000Z",
    "updatedAt": "2026-10-01T08:00:00.000Z",
    "__v": 0
  }
}
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| title falsy | 400 | `{"success":false,"message":"Banner title is required"}` |
| no image | 400 | `{"success":false,"message":"Banner image is required"}` |
| exception | 500 | `{"success":false,"message":"<raw error message>"}`, e.g. ``"Banner validation failed: title: Path `title` is required."``. The server logs `CREATE BANNER ERROR:`. |
| upload rejected | 500 | default HTML error page |

#### 6.7.2 `GET /api/banner/get-banner`

- **Logic:** find banners where `status == true`, sorted by `order` ascending, then `createdAt` descending.

**Success 200:**

```json
{ "success": true, "data": [ { "...banner object (§4.6)...": "" } ] }
```

**Errors:** 500 `{"success":false,"message":"<error message>"}`. The server logs `GET BANNER ERROR:`.

#### 6.7.3 `GET /api/banner/get-all-banner`

- **Logic:** find all banners, with the same sort as §6.7.2.
- **Success 200:** same shape as §6.7.2.
- **Errors:** 500 `{"success":false,"message":"<error message>"}`. The server logs `GET ALL BANNER ERROR:`.

#### 6.7.4 `DELETE /api/banner/delete-banner/:id`

**Logic:**

1. Find the banner by `id`. If it is not found, respond 404. An invalid id format gives the 500 response with a cast-error message.
2. If `image` is set, build the file path as `<cwd>/<image with its first "/" removed>`, i.e. `uploads/<file>`. If the file exists, delete it **synchronously**. If deletion throws, the request fails with 500 and the document is **not** deleted.
3. Delete the banner document.
4. Respond 200.

**Success 200:**

```json
{ "success": true, "message": "Banner deleted successfully" }
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| not found | 404 | `{"success":false,"message":"Banner not found"}` |
| exception (e.g. invalid id) | 500 | `{"success":false,"message":"<raw error message>"}`, e.g. ``"Cast to ObjectId failed for value \"abc\" (type string) at path \"_id\" for model \"Banner\""``. The server logs `DELETE BANNER ERROR:`. |

There is **no update endpoint and no status-toggle endpoint** for banners.

---

### 6.8 Promo card module (`/api/promo-card`)

All endpoints are **unauthenticated** (KI-01). Behavior mirrors banners, with an extra `background` field.

#### 6.8.1 `POST /api/promo-card/create-promo-card`

- **Content type:** `multipart/form-data`

| Field | Type | Required | Default | Rules |
|---|---|---|---|---|
| `title` | text | yes | — | Truthy. Trimmed by the schema. Same whitespace-only caveat as banners. |
| `subtitle` | text | no | `""` | Trimmed |
| `buttonText` | text | no | `"Shop Now"` | — |
| `buttonLink` | text | no | `"/shop"` | — |
| `background` | text | no | `"#08aaa6"` | Not validated |
| `order` | text/number | no | `0` | `Number(order) \|\| 0` |
| `status` | text/bool | no | `true` | Same rule as banners |
| `image` | file | yes | — | §7 |

**Logic:**

1. If `title` is falsy, respond 400.
2. If there is no file, respond 400.
3. Insert the promo card.
4. Respond 201.

**Success 201:**

```json
{
  "success": true,
  "message": "Promotional card created successfully",
  "data": {
    "_id": "66fa41009d3e4a0012ab3a00",
    "title": "Gift Sets",
    "subtitle": "Perfect for Diwali",
    "image": "/uploads/1790700101917-149332359.jpeg",
    "buttonText": "Shop Now",
    "buttonLink": "/shop",
    "background": "#08aaa6",
    "order": 1,
    "status": true,
    "createdAt": "2026-10-01T08:10:00.000Z",
    "updatedAt": "2026-10-01T08:10:00.000Z",
    "__v": 0
  }
}
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| title falsy | 400 | `{"success":false,"message":"Promo card title is required"}` |
| no image | 400 | `{"success":false,"message":"Promo card image is required"}` |
| exception | 500 | `{"success":false,"message":"<raw error message>"}`. The server logs `CREATE PROMO ERROR:`. |
| upload rejected | 500 | default HTML error page |

#### 6.8.2 `GET /api/promo-card/get-promo-card`

- **Logic:** find promo cards where `status == true`, sorted by `order` ascending, then `createdAt` descending.
- **Success 200:** `{"success":true,"data":[ ...promo card objects (§4.7)... ]}`
- **Errors:** 500 `{"success":false,"message":"<error message>"}`. The server logs `GET PROMO ERROR:`.

#### 6.8.3 `GET /api/promo-card/get-all-promo-card`

- **Logic:** find all promo cards, with the same sort.
- **Success 200:** `{"success":true,"data":[ ... ]}`
- **Errors:** 500 `{"success":false,"message":"<error message>"}`. The server logs `GET ALL PROMO ERROR:`.

#### 6.8.4 `DELETE /api/promo-card/delete-promo-card/:id`

- **Logic:** identical to §6.7.4: find, delete the file synchronously if it exists, delete the document.

**Success 200:**

```json
{ "success": true, "message": "Promotional card deleted successfully" }
```

**Errors:**

| Condition | Status | Body |
|---|---|---|
| not found | 404 | `{"success":false,"message":"Promo card not found"}` |
| exception (e.g. invalid id) | 500 | `{"success":false,"message":"<raw error message>"}`. The server logs `DELETE PROMO ERROR:`. |

There is **no update endpoint and no status-toggle endpoint** for promo cards.

---

### 6.9 Static uploads

#### 6.9.1 `GET /uploads/<filename>`

- **Auth:** none.
- Serves the file `uploads/<filename>` from the working directory, with a content type based on the file extension.
- If the file is missing, the generic 404 is returned (§11).
- See §7.

---

## 7. File Uploads and Static Files

### 7.1 Which endpoints accept uploads

| Endpoint | Form field | Max files | Required |
|---|---|---|---|
| `POST /api/category/create-category` | `image` | 1 | yes (checked by handler) |
| `PUT /api/category/update-category/:_id` | `image` | 1 | no |
| `POST /api/product/create-product` | `image` | 1 | yes |
| `PUT /api/product/update-product/:_id` | `image` | 1 | no |
| `POST /api/banner/create-banner` | `image` | 1 | yes |
| `POST /api/promo-card/create-promo-card` | `image` | 1 | yes |

### 7.2 Upload rules

| Rule | Value |
|---|---|
| Accepted MIME types, as declared by the client | `image/jpeg`, `image/png`, `image/jpg`, `video/mp4`, `video/mkv`, `video/webm`, `video/avi` |
| Max size per file | **100 MB** (104,857,600 bytes) |
| Other field or part limits | none beyond the defaults |
| Disallowed MIME type | The request is rejected with HTTP **500** and the default HTML error page containing `Only JPEG, PNG, JPG images and MP4, MKV, WEBM, AVI videos are allowed` |
| File too large | HTTP **500**, HTML page, message `File too large` |
| A file under a different field name, or more than one `image` file | HTTP **500**, HTML page, message `Unexpected field` |
| Upload-stage errors | Occur before the handler runs, so the JSON handler logic is skipped |

### 7.3 Storage and naming

- Files are stored on the local disk in the **`uploads/`** folder, relative to the process working directory. The folder is **not created automatically**: if it is missing, uploads fail with 500. It is excluded from version control.
- The file is written to disk **before** the handler's validation runs.
- Stored filename: `<epochMillis>-<random integer 0–1000000000>` + `<original file extension, case preserved, including the dot>`. Examples: `1790670860904-253178900.png`, `1790700056594-868888729.jpeg`. A file with no extension is stored with no extension.
- The value saved in the database is the **relative URL** `/uploads/<storedFilename>`. Responses return this relative path. The frontend prefixes it with the API base URL. No absolute URL is ever built.

### 7.4 Deletion

| Context | Behavior |
|---|---|
| Category and product update (new image uploaded, save succeeded) | Delete the old file if the stored value starts with `/uploads/`. The path is built as `uploads/<basename of value>`. A missing file is silently ignored; other errors are logged as `Image delete error:` and ignored. |
| Category update failure paths (invalid id, not found, bad name, duplicate, exception) | The newly uploaded file is deleted using the same rule |
| Product update exception path | The newly uploaded file is deleted. **On 400 and 404 validation paths it is not.** |
| Category and product delete | Delete the record's image file using the same rule, after the document is deleted |
| Banner and promo-card delete | Path is `<cwd>/` plus the stored value with its first `/` removed. Checked for existence, then deleted synchronously, **before** the document is deleted. |
| Create endpoints (all four) on a validation failure | The uploaded file is **not** deleted (orphaned) |
| Product delete | Carts and orders keep their `image` snapshot strings (orders) or references (carts), even though the file is gone |

### 7.5 Serving

- `GET /uploads/<filename>` serves the stored files publicly with standard static-file semantics (§3.7). There is no authentication, no resizing, and no long-lived cache headers.

---

## 8. Third-Party Integrations

| Service | Status | Details |
|---|---|---|
| **MongoDB** | Active | The only external dependency. Connection string in `MONGO_URI`. Uses collections `users`, `categories`, `products`, `carts`, `orders`, `banners`, `promocards`. |
| Maps service (Google Maps) | **Not used** | `GOOGLE_MAPS_API_KEY` exists in `.env` but is never read |
| Payment gateway | **None** | `paymentMethod` defaults to the free-text `"WhatsApp Order"`. No payment processing. |
| Email | **None** | An email-sending client library is declared as a dependency but never used |
| SMS / WhatsApp API | **None** | The WhatsApp ordering flow happens on the frontend or manually. The backend sends nothing. |
| Cloud storage | **None** | Files are stored on local disk only |
| Relational database | **None** | A relational database client is declared as a dependency but never used |

---

## 9. Business Rules

### 9.1 Accounts

- **BR-01** Emails are stored trimmed and lower-cased. Lookups for login and duplicate checks use the normalized form, so emails are effectively case-insensitive.
- **BR-02** One account per email (409 on duplicate, plus a unique database index).
- **BR-03** Passwords must be at least 6 characters. There are no other complexity rules.
- **BR-04** Self-registration always creates role `user`. Admins exist only through direct database edits.
- **BR-05** Sessions last 7 days. There is no sliding renewal. Logout clears only the cookie.

### 9.2 Catalogue

- **BR-06** Category names are unique (exact, case-sensitive, after trimming).
- **BR-07** A category cannot be deleted while any product references it (409).
- **BR-08** On create, product name plus category must be unique (exact match after trimming). The update endpoint does **not** re-check this.
- **BR-09** `price` must be a finite number ≥ 1. Decimals are allowed.
- **BR-10** `oldPrice`, if given, must be a finite number ≥ 1. On **update only**, the resulting `oldPrice` must be ≥ `price`, otherwise 400. On create, no relation is enforced.
- **BR-11** `stock` must be an integer ≥ 0.
- **BR-12** Every category and product must have an image.
- **BR-13** A product must reference an existing category, checked on create and on category change.

### 9.3 Cart

- **BR-14** Each user has exactly one cart, created lazily by `GET /api/cart` or `POST /api/cart/add`.
- **BR-15** A product appears at most once per cart. Adding it again increases the quantity and re-selects the line.
- **BR-16** Quantity must be ≥ 1. A cart line's quantity can never exceed the product's **current** `stock` at the time of add or update. Stock is not reserved.
- **BR-17** Lines have a `selected` flag (default `true`). Only the boolean `false` deselects.
- **BR-18** Deleted products remain in carts as lines whose `product` is `null` in responses.

### 9.4 Orders

- **BR-19** Order creation requires customer `name`, `mobile`, `address`, `city` and `pincode`, plus at least one item with a product id, a name and a positive quantity.
- **BR-20** Item `total = price × quantity` is calculated by the server. `itemsTotal`, `shipping` and `grandTotal` are taken **as sent** by the client, with no recalculation or cross-check.
- **BR-21** `shippingStatus` ∈ {`FREE`, `PAYABLE_SEPARATELY`} (default `FREE`). `shipping` defaults to 0.
- **BR-22** The payment method defaults to `"WhatsApp Order"`. No payment is captured.
- **BR-23** Order number format: `AKRF-<epoch ms>-<1000..9999>`, unique.
- **BR-24** New orders start at `Pending` with `statusDates.Pending = creation time` and all other status dates `null`.
- **BR-25** `expectedDelivery` = creation time + 3 calendar days.
- **BR-26** After an order is placed, every cart line for an ordered product is removed, whether or not it was selected.
- **BR-27** Placing an order does **not** check or reduce stock, and does not check that the products exist.
- **BR-28** **Status lifecycle:** the statuses are `Pending → Confirmed → Processing → Shipped → Delivered`, plus `Cancelled`. The server enforces **no** transition rules: an admin can set any status from any status, including the current one.
- **BR-29** Setting a status records `statusDates[<status>] = now`, overwriting any earlier value for that status. Other dates are kept.
- **BR-30** Cancelling sets `expectedDelivery = null`. Setting any non-cancelled status when `expectedDelivery` is null sets it to now + 3 days. Otherwise it is unchanged.
- **BR-31** Customers can see only their own orders. Only admins can list all orders or change a status. Customers cannot cancel their own orders.

### 9.5 Merchandising

- **BR-32** Banners and promo cards are public only when `status == true`. Lists are sorted by `order` ascending, then newest first.
- **BR-33** Defaults: `buttonText "Shop Now"`, `buttonLink "/shop"`, `order 0`, `status true`. Promo cards also default `background "#08aaa6"`.
- **BR-34** On create, `status` becomes false for any supplied value other than `true` or `"true"`.
- **BR-35** Banners and promo cards cannot be edited after creation, only deleted.

### 9.6 Limits

- **BR-36** JSON and URL-encoded bodies are limited to 10 MB. Uploaded files are limited to 100 MB each, one file per request.
- **BR-37** Coupons, discounts, taxes and pagination do not exist.

---

## 10. Background Jobs / Scheduled Tasks / Startup Behaviour

| Item | Behavior |
|---|---|
| Scheduled jobs / cron / timers | **None** |
| Seeding / admin auto-creation | **None** |
| Startup sequence | 1. Load the `.env` file into the environment (existing process variables are not overwritten). 2. Register cookie parsing. 3. **Start** the MongoDB connection using `MONGO_URI`. It is not awaited before listening. 4. Register body parsers (10 MB), CORS, static `/uploads`, `GET /` and the module routes. 5. Listen on `PORT` (default 9000) and log `server started on port <port>`. |
| DB connect success | Log `MongoDB connected successfully` |
| DB connect failure | Log `MongoDB connection failed: <error message>` and **exit the process with code 1** |
| Requests before the DB is connected | Database operations are queued until the connection is ready. If the connection fails, the process exits. |
| Index creation | On startup, unique indexes are ensured: `users.email`, `categories.name`, `carts.user`, `orders.orderId`, plus the non-unique `orders.user` |
| Upload folder | Must already exist. It is not created at startup. |
| Run command | The declared start command runs the server under a file-watching auto-restart development tool (KI-28). There is no build step and no test suite. |

---

## 11. Error Handling Conventions

### 11.1 Handler-level errors

Every handler catches its own exceptions and returns a JSON body with HTTP 500. The body differs by module:

| Module | 500 body |
|---|---|
| Auth | `{"success":false,"message":"<fixed text>"}`, e.g. `"Registration failed"`, `"Login failed"`, `"Unable to get user"`, `"Logout failed"` |
| Cart | `{"success":false,"message":"<fixed text>"}`, e.g. `"Unable to get cart"` |
| Order create and status | `{"success":false,"message":"<fixed text>","error":"<raw exception message>"}` |
| Order lists and detail | `{"success":false,"message":"<fixed text>"}` |
| Category create, product update and delete | `{"message":"<raw exception message>","success":false,"error":true}` |
| Category update and delete, product create | `{"message":"Internal server error","success":false,"error":true}` (with special cases listed per endpoint) |
| Category and product GET | `{"message":"<raw message>","error":true,"success":false}` |
| Banner, promo card | `{"success":false,"message":"<raw exception message>"}` |

### 11.2 Errors outside handlers (default framework handler)

These return **HTML**, not JSON:

| Situation | Status | Body |
|---|---|---|
| Unknown route or method, or a missing static file | 404 | HTML page: `<pre>Cannot <METHOD> <path></pre>`, e.g. `Cannot GET /api/unknown` |
| Malformed JSON body | 400 | HTML page with the parse error |
| Body over 10 MB | 413 | HTML page, "request entity too large" |
| Upload rejected (type, size, field name), or upload folder missing | 500 | HTML page with the error message |

The HTML page is a minimal document: title `Error`, and the message in `<pre>`. Unless the server runs in production mode (a standard environment flag, not set in the current `.env`), the page includes the stack trace. In production it shows only the HTTP status text. These responses have the headers `Content-Security-Policy: default-src 'none'` and `X-Content-Type-Options: nosniff`.

### 11.3 Logging

- Plain console output only. There is no request or access logging and no log files.
- Logged events: startup (`server started on port …`), DB connect success and failure, the guard error messages (`Auth middleware error: …`, `Admin middleware error: …`), and per-handler error labels: `Register Error:`, `Login Error:`, `Me Error:`, `Logout Error:`, `Create category error:`, `Update category error:`, `Delete category error:`, `Image delete error:`, `Create Product error:`, `CREATE ORDER ERROR:`, `GET MY ORDERS ERROR:`, `GET ORDER ERROR:`, `GET ALL ORDERS ERROR:`, `UPDATE ORDER STATUS ERROR:`, `CREATE BANNER ERROR:`, `GET BANNER ERROR:`, `GET ALL BANNER ERROR:`, `DELETE BANNER ERROR:`, `CREATE PROMO ERROR:`, `GET PROMO ERROR:`, `GET ALL PROMO ERROR:`, `DELETE PROMO ERROR:`. Cart handlers log the raw error object.
- Category and product GET errors, product update and delete errors are **not** logged.

---

## 12. Functional Requirements List

### 12.1 Platform and configuration

- **FR-001** The system shall listen for HTTP requests on the port given by `PORT`, defaulting to `9000`.
- **FR-002** The system shall respond to `GET /` with HTTP 200 and `{"msg":"api is working"}`.
- **FR-003** The system shall send `Access-Control-Allow-Origin` equal to the value of `FRONTEND_URL` and `Access-Control-Allow-Credentials: true` on all responses.
- **FR-004** The system shall answer CORS preflight requests with HTTP 204, allowed methods `GET,HEAD,PUT,PATCH,POST,DELETE`, and the requested headers echoed back.
- **FR-005** The system shall parse JSON and URL-encoded (nested) request bodies up to 10 MB, and respond HTTP 413 above that limit.
- **FR-006** The system shall serve files in the `uploads` folder publicly at `/uploads/<filename>`.
- **FR-007** The system shall return HTTP 404 for unknown routes.
- **FR-008** The system shall connect to MongoDB using `MONGO_URI` at startup, log `MongoDB connected successfully` on success, and on failure log `MongoDB connection failed: <message>` and exit with code 1.
- **FR-009** The system shall ensure unique indexes on `users.email`, `categories.name`, `carts.user` and `orders.orderId`, and a non-unique index on `orders.user`.
- **FR-010** The system shall store `createdAt`, `updatedAt` and `__v` on every document in all seven collections, and return them in responses.
- **FR-011** The system shall serialize ObjectIds as 24-character hex strings and dates as ISO-8601 UTC strings with milliseconds.
- **FR-012** The system shall match routes case-insensitively and accept an optional trailing slash.

### 12.2 Authentication

- **FR-013** The system shall reject registration with 400 `"Name, email and password are required"` when name, email or password is missing or empty.
- **FR-014** The system shall reject registration with 400 `"Password must be at least 6 characters"` when the password string is shorter than 6 characters.
- **FR-015** The system shall normalize emails by trimming and lower-casing before lookup and storage.
- **FR-016** The system shall reject registration with 409 `"Email already registered"` when the normalized email exists.
- **FR-017** The system shall hash passwords with bcrypt at cost factor 10 before storing them.
- **FR-018** The system shall create every self-registered user with `role: "user"`, ignoring any role in the request.
- **FR-019** The system shall store the trimmed name and the trimmed phone (or `""`) on registration.
- **FR-020** On successful registration the system shall set the `accessToken` cookie and respond 201 with `success`, `message: "Account created successfully"` and `user {id,name,email,phone,role}`.
- **FR-021** The system shall respond 500 `"Registration failed"` on any unexpected registration error.
- **FR-022** The system shall reject login with 400 `"Email and password are required"` when either field is missing.
- **FR-023** The system shall reject login with 401 `"Invalid email or password"` when the email is unknown or the password does not match.
- **FR-024** On successful login the system shall set the `accessToken` cookie and respond 200 with `message: "Login successful"` and `user {id,name,email,phone,address,city,pincode,role}`.
- **FR-025** The system shall respond 500 `"Login failed"` on any unexpected login error.
- **FR-026** The system shall issue HS256 JWTs with payload `{userId}`, signed with `JWT_SECRET` and expiring after 7 days.
- **FR-027** The system shall set the auth cookie as `accessToken` with HttpOnly, SameSite=Lax, not Secure, Path=/, and Max-Age 604800 seconds.
- **FR-028** The system shall read the session token only from the `accessToken` cookie.
- **FR-029** The system shall respond 401 `"Please login first"` to protected endpoints when no token cookie is present.
- **FR-030** The system shall respond 401 `"Invalid or expired session"` when the token fails verification or has expired.
- **FR-031** The system shall respond 401 `"User not found"` when the token's `userId` does not match a user.
- **FR-032** The system shall load the current user, without the password, from the database on every authenticated request, and use the stored role for authorization.
- **FR-033** The system shall respond 403 `"Admin access required"` when a non-admin calls an admin-only endpoint.
- **FR-034** `GET /api/auth/me` shall return 200 with `success: true` and the user profile `{id,name,email,phone,address,city,pincode,role}`.
- **FR-035** `POST /api/auth/logout` shall clear the `accessToken` cookie and return 200 `"Logout successful"` without requiring authentication.
- **FR-036** The system shall never return the password hash in any response.

### 12.3 Categories

- **FR-037** The system shall create a category from multipart fields `name` and `description` and a required file `image`, storing `image` as `/uploads/<storedFilename>`.
- **FR-038** The system shall reject category creation with 400 `"Category name is required"` when the name is blank.
- **FR-039** The system shall reject category creation with 400 `"Please upload an image"` when no file is provided.
- **FR-040** The system shall reject category creation or rename with 409 `"Category already exists"` when another category has the exact trimmed name.
- **FR-041** The system shall respond 201 `"Category created successfully"` with `success:true,error:false,data:<category>` on creation.
- **FR-042** `GET /api/category/get-category` shall return 200 `{"message":"categories fetched successfully","data":[all categories]}` without a `success` field, unsorted and unpaginated.
- **FR-043** The system shall reject category update or delete with 400 `"Invalid category ID"` when the path id is not a valid ObjectId.
- **FR-044** The system shall respond 404 `"Category not found"` when updating or deleting a non-existent category.
- **FR-045** The system shall update only the category fields that are present (`name`, `description`, `image`), trimming text, and respond 200 `"Category updated successfully"` with the updated document.
- **FR-046** When a category update replaces the image, the system shall delete the previous image file from `uploads` after a successful save.
- **FR-047** When a category update fails, the system shall delete any newly uploaded file.
- **FR-048** The system shall reject category deletion with 409 `"This category contains products. Delete or reassign those products first."` when any product references it.
- **FR-049** On successful category deletion, the system shall remove the document and its image file, and respond 200 `"Category deleted successfully"` with the deleted document in `data`.

### 12.4 Products

- **FR-050** The system shall create a product from multipart fields `name`, `category`, `price`, `oldPrice`, `stock` and `description`, and a required file `image`.
- **FR-051** The system shall reject product creation with 400 `"Name, category, price and stock are required"` when any of those is missing or empty.
- **FR-052** The system shall reject product creation with 400 `"Please upload an image"` when no file is provided.
- **FR-053** The system shall reject a product's category with 400 `"Invalid category ID"` if it is not a valid ObjectId, and with 404 `"Category not found"` if it does not exist.
- **FR-054** The system shall reject product creation with 400 `"Invalid price, old price or stock"` unless price is finite and ≥ 1, stock is an integer ≥ 0, and oldPrice (if supplied) is finite and ≥ 1.
- **FR-055** The system shall reject product creation with 409 `"Product already exists"` when a product with the same trimmed name exists in the same category.
- **FR-056** The system shall respond 201 `"Product created successfully"` with the created product in `data`.
- **FR-057** `GET /api/product/get-product` shall return 200 `{"message":"products fetched successfully","data":[all products]}`, with `category` as an id string, no `success` field and no sorting.
- **FR-058** The system shall reject product update or delete with 400 `"Invalid product ID"` for an invalid id, and 404 `"Product not found"` for a missing product.
- **FR-059** The system shall update only the product fields that are present, using these messages: `"Product name is required"`, `"Invalid price"`, `"Invalid old price"` and `"Invalid stock"` (400 each).
- **FR-060** The system shall remove `oldPrice` from a product when the update supplies `oldPrice` as an empty string.
- **FR-061** The system shall reject a product update with 400 `"Old price cannot be less than price"` when the resulting oldPrice is set and is less than the resulting price.
- **FR-062** When a product update replaces the image, the system shall delete the previous file after a successful save. On an unexpected error it shall delete the new file and respond 500 with the raw error message.
- **FR-063** The system shall respond 200 `"Product updated successfully"` with the updated product in `data`.
- **FR-064** On product deletion, the system shall remove the document and its image file and respond 200 `{"message":"Product deleted successfully","success":true,"error":false}`.

### 12.5 Cart

- **FR-065** All cart endpoints shall require authentication and operate only on the current user's cart.
- **FR-066** `GET /api/cart` shall return the user's cart, creating an empty cart if none exists, with `items[].product` populated.
- **FR-067** Cart responses (except clear) shall populate each line's `product` with the full product document, or `null` if the product no longer exists.
- **FR-068** `POST /api/cart/add` shall respond 400 `"Product ID is required"` when `productId` is missing.
- **FR-069** `POST /api/cart/add` shall respond 404 `"Product not found"` when the product does not exist.
- **FR-070** `POST /api/cart/add` shall default `quantity` to 1 and respond 400 `"Quantity must be at least 1"` when the quantity is below 1.
- **FR-071** `POST /api/cart/add` shall respond 400 `"Only <stock> items available"` when the requested quantity, or the existing quantity plus the requested quantity, exceeds the product's stock.
- **FR-072** `POST /api/cart/add` shall increase the quantity and set `selected: true` for an existing line, or append a new line with `selected: true`, and respond 200 `"Product added to cart"` with the populated cart.
- **FR-073** `PUT /api/cart/update` shall respond 400 `"Invalid cart data"` when `productId` is missing or the quantity is below 1.
- **FR-074** `PUT /api/cart/update` shall respond 404 `"Cart not found"` when the user has no cart, and 404 `"Product not found in cart"` when the line does not exist.
- **FR-075** `PUT /api/cart/update` shall set the line quantity to the given value, after checking it does not exceed the stock of an existing product, and respond 200 `"Cart updated"`.
- **FR-076** `DELETE /api/cart/remove/:productId` shall remove the matching line, succeeding even if no line matches, and respond 200 `"Product removed"`. It shall respond 404 `"Cart not found"` when there is no cart.
- **FR-077** `PUT /api/cart/toggle` shall set `selected` to false only when the body's `selected` is the boolean `false`, and true otherwise, then respond 200 `"Selection updated"`.
- **FR-078** `PUT /api/cart/toggle` shall respond 404 `"Cart not found"` or `"Product not found in cart"` as appropriate.
- **FR-079** `DELETE /api/cart/clear` shall empty the cart and respond 200 `"Cart cleared"` with the cart (`items: []`). When no cart exists, it shall respond 200 `{"success":true,"message":"Cart already empty"}`.
- **FR-080** The system shall enforce at most one cart per user.

### 12.6 Orders

- **FR-081** `POST /api/order/create` shall require authentication.
- **FR-082** The system shall respond 400 `"Please provide complete customer details"` when `customer` or any of `customer.name`, `mobile`, `address`, `city`, `pincode` is missing or empty.
- **FR-083** The system shall respond 400 `"At least one product is required"` when `items` is not a non-empty array.
- **FR-084** The system shall take each item's product id from `product`, or from `productId` when `product` is absent.
- **FR-085** The system shall default an item's `price` to 0 and `quantity` to 1, and calculate `total = price × quantity`.
- **FR-086** The system shall respond 400 `"Invalid order product data"` when any item lacks a product id or name, or has a quantity ≤ 0.
- **FR-087** The system shall generate a unique `orderId` of the form `AKRF-<epoch ms>-<4-digit number 1000–9999>`.
- **FR-088** The system shall store the order with trimmed customer fields, `status: "Pending"`, `statusDates.Pending` = creation time, other status dates `null`, and `expectedDelivery` = creation time + 3 days.
- **FR-089** The system shall store `itemsTotal`, `shipping` (default 0), `shippingStatus` (default `"FREE"`), `grandTotal` and `paymentMethod` (default `"WhatsApp Order"`) as supplied by the client.
- **FR-090** The system shall reject `shippingStatus` values other than `FREE` or `PAYABLE_SEPARATELY` with 500 `"Unable to create order"`, carrying the validation message in `error`.
- **FR-091** After creating an order, the system shall remove from the user's cart every line whose product appears in the order.
- **FR-092** The system shall respond 201 `"Order created successfully"` with the order, with `items.product` and `user` (without password) populated.
- **FR-093** `GET /api/order/my-orders` shall return 200 `{success:true, orders:[...]}` containing only the current user's orders, newest first, with `items.product` populated.
- **FR-094** `GET /api/order/my-orders/:id` shall return 200 `{success:true, order}` only when the order `_id` belongs to the current user, and 404 `"Order not found"` otherwise.
- **FR-095** `GET /api/order/all` shall require the admin role and return every order, newest first, with `user` (without password) and `items.product` populated.
- **FR-096** `PUT /api/order/status/:id` shall require the admin role.
- **FR-097** `PUT /api/order/status/:id` shall respond 400 `"Invalid order status"` unless `status` is one of `Pending, Confirmed, Processing, Shipped, Delivered, Cancelled`.
- **FR-098** `PUT /api/order/status/:id` shall respond 404 `"Order not found"` for a non-existent order.
- **FR-099** On a status update, the system shall set `status`, set `statusDates[status]` to the current time, and keep the other status dates.
- **FR-100** On a status update to `Cancelled`, the system shall set `expectedDelivery` to `null`.
- **FR-101** On a status update to any other status while `expectedDelivery` is null, the system shall set `expectedDelivery` to the current time + 3 days.
- **FR-102** The system shall allow any status to be set from any current status.
- **FR-103** On a status update, the system shall respond 200 with `message: "Order status changed to <status>"` and the populated order.

### 12.7 Banners

- **FR-104** `POST /api/banner/create-banner` shall create a banner from multipart fields `title`, `subtitle`, `buttonText`, `buttonLink`, `order` and `status`, and a required file `image`.
- **FR-105** The system shall respond 400 `"Banner title is required"` when `title` is missing, and 400 `"Banner image is required"` when there is no file.
- **FR-106** The system shall apply banner defaults `subtitle ""`, `buttonText "Shop Now"`, `buttonLink "/shop"`, `order 0` (also when not numeric) and `status true` (when omitted). Any supplied status other than `true` or `"true"` shall be stored as `false`.
- **FR-107** The system shall respond 201 `"Banner created successfully"` with the banner in `data`.
- **FR-108** `GET /api/banner/get-banner` shall return only banners with `status: true`, sorted by `order` ascending, then `createdAt` descending, as `{success:true,data:[...]}`.
- **FR-109** `GET /api/banner/get-all-banner` shall return all banners with the same sort and envelope.
- **FR-110** `DELETE /api/banner/delete-banner/:id` shall respond 404 `"Banner not found"` for a missing banner. Otherwise it shall delete the image file, if present, and then the document, and respond 200 `"Banner deleted successfully"`.

### 12.8 Promo cards

- **FR-111** `POST /api/promo-card/create-promo-card` shall create a promo card from multipart fields `title`, `subtitle`, `buttonText`, `buttonLink`, `background`, `order` and `status`, and a required file `image`.
- **FR-112** The system shall respond 400 `"Promo card title is required"` when `title` is missing, and 400 `"Promo card image is required"` when there is no file.
- **FR-113** The system shall apply promo card defaults identical to banners, plus `background "#08aaa6"`.
- **FR-114** The system shall respond 201 `"Promotional card created successfully"` with the card in `data`.
- **FR-115** `GET /api/promo-card/get-promo-card` shall return only cards with `status: true`, sorted by `order` ascending, then `createdAt` descending, as `{success:true,data:[...]}`.
- **FR-116** `GET /api/promo-card/get-all-promo-card` shall return all cards with the same sort and envelope.
- **FR-117** `DELETE /api/promo-card/delete-promo-card/:id` shall respond 404 `"Promo card not found"` for a missing card. Otherwise it shall delete the image file, if present, and then the document, and respond 200 `"Promotional card deleted successfully"`.

### 12.9 Uploads

- **FR-118** The system shall accept at most one uploaded file, in the form field `image`, on the six upload endpoints.
- **FR-119** The system shall accept only files whose declared MIME type is `image/jpeg`, `image/png`, `image/jpg`, `video/mp4`, `video/mkv`, `video/webm` or `video/avi`, and reject others with HTTP 500 and the message `Only JPEG, PNG, JPG images and MP4, MKV, WEBM, AVI videos are allowed`.
- **FR-120** The system shall reject files larger than 100 MB.
- **FR-121** The system shall store uploads in `uploads/` as `<epoch ms>-<random 0–1e9><original extension>`, and record them in the database as `/uploads/<filename>`.
- **FR-122** The system shall return image paths as relative URLs (`/uploads/...`) in all responses.

---

## 13. Known Issues / Ambiguities

These are observations only. The current behavior is described in the sections above.

| ID | Area | Observation |
|---|---|---|
| **KI-01** | Security | **No authentication or authorization** on any category, product, banner or promo-card endpoint, including create, update, delete and the "admin" `get-all-*` lists. Anyone can modify the catalogue or upload files up to 100 MB. |
| **KI-02** | Security / config | The JWT signing secret is captured when the auth module loads, which happens **before** `.env` is applied. Signing therefore uses the real environment's `JWT_SECRET` or a **hard-coded fallback literal**, while verification uses the `.env` value at request time. It works today only because the `.env` value equals the fallback. Changing `JWT_SECRET` only in `.env` would make every login produce tokens that fail verification. A hard-coded secret in source is also a security risk. |
| **KI-03** | Security | `.env`, which contains real credentials, is tracked in version control. |
| **KI-04** | Security | The cookie is not `Secure`. With `SameSite=Lax`, a frontend on a different *site* (registrable domain) than the API will not send the cookie on fetch or XHR requests. It works today only for same-site setups such as localhost ports. |
| **KI-05** | Security | Logout does not invalidate the JWT. A copied token stays valid for up to 7 days. |
| **KI-06** | Business integrity | Order prices and totals (`price`, `itemsTotal`, `shipping`, `grandTotal`) are trusted from the client. Product existence is not checked, stock is not checked or decremented, and items can reference arbitrary product ids. |
| **KI-07** | Business integrity | Order status has no transition rules. For example `Delivered → Pending` and `Cancelled → Shipped` are allowed, and re-entering a status overwrites its earlier timestamp. A re-opened order gets a new `expectedDelivery` of now + 3 days. |
| **KI-08** | Files | Uploaded files are orphaned on disk when create endpoints (category, product, banner, promo card) fail validation, and on product-update 400/404 paths. Category update cleans up correctly. |
| **KI-09** | Files | Video MIME types are accepted although every field is called `image` and is displayed as an image. `video/mkv` and `video/avi` are non-standard MIME names; browsers usually send `video/x-matroska` and `video/x-msvideo`, so those uploads are rejected. `image/webp` and `image/gif` are rejected. MIME types are trusted from the client, not sniffed. |
| **KI-10** | Errors | Upload errors (bad type, too large, wrong field), malformed JSON, oversized bodies and unknown routes return **HTML** pages, not JSON. Upload errors use status 500 instead of 4xx. The HTML may include stack traces when not in production mode. |
| **KI-11** | Errors | Invalid ObjectId formats return 500 rather than 400 or 404 in: banner and promo-card delete, cart add, order detail and order status update. Some 500 responses expose raw internal error messages: category create, product update and delete, banner, promo card, order create and status. |
| **KI-12** | Validation | A `NaN` quantity in cart add or update, or in order items (e.g. `"abc"`), passes the `< 1` or `<= 0` checks and fails later with 500. A missing `quantity` in cart update leads to the same 500. Cart and order quantities are not required to be integers. |
| **KI-13** | Validation | Non-string JSON values (e.g. a numeric `password`, `email` or `customer.mobile`) cause 500 errors instead of 400. A numeric password skips the length check. |
| **KI-14** | Validation | Whitespace-only `name` on register, or `title` on banner or promo card, passes the handler check but fails the schema "required" rule, giving 500 ("Registration failed", or a raw validation message). |
| **KI-15** | Validation | Email, phone, mobile, pincode, button link and background colour formats are not validated. |
| **KI-16** | Inconsistency | `oldPrice ≥ price` is enforced on product **update** but not on create. On update the check runs against the stored values, so an update of an unrelated field can fail if legacy data violates the rule. The product-name duplicate check runs on create only. |
| **KI-17** | Inconsistency | Response envelopes differ by module: `success`, `success+error`, or neither (category and product GET). The `if (!result)` 404 branches in the GET handlers can never trigger. |
| **KI-18** | Inconsistency | The register response omits `address`, `city` and `pincode`; login and me include them. |
| **KI-19** | Inconsistency | The clear-cart response returns an unpopulated cart, or no `cart` key when the user has no cart. Other cart responses return a populated cart. `PUT /cart/update`, `/toggle` and `/remove` return 404 when no cart exists, while `GET` and `add` auto-create one. |
| **KI-20** | Semantics | `PUT /cart/toggle` deselects only for boolean `false`. Form-style `"false"` selects. |
| **KI-21** | Semantics | Order creation removes ordered products from the cart even if those lines were deselected, and regardless of the quantity ordered. |
| **KI-22** | Data integrity | Deleting a product leaves cart lines and order items referencing it, which populate as `null`. Order items keep their name, image and price snapshot, but the image file is deleted. |
| **KI-23** | Missing features | There is no endpoint to update a user profile (address, city and pincode are never written), change or reset a password, create admins, update banners or promo cards, toggle their `status`, view or cancel an order as a customer, or paginate or filter any list. |
| **KI-24** | Dead config / code | `GOOGLE_MAPS_API_KEY` is unused. Dependencies are declared for an email-service client, a relational database client, an HTTP request logger and a second bcrypt implementation; none is used. There is also a commented-out alternative static-serving line. |
| **KI-25** | Ambiguity | The GET category and product handlers wrap their single aggregation stage in an extra array (`[[stage]]`). The database layer flattens it, so it works, but it looks unintended. The stage only converts `_id` to a string, which does not change the JSON output. |
| **KI-26** | Ambiguity | Expected delivery uses server-local calendar arithmetic (+3 days at the same wall-clock time). Across a daylight-saving change this is not exactly 72 hours. |
| **KI-27** | Robustness | The database connection is not awaited before the server starts listening. Banner and promo-card image deletion is synchronous and runs before the document delete; if file deletion throws, the record remains. |
| **KI-28** | Ops | The start command uses a development file-watcher. The `uploads/` folder must be created manually. Local-disk storage does not survive container or host replacement. |
| **KI-29** | Concurrency | Concurrent first requests to `GET /api/cart` or `add` for the same user can race on the unique `carts.user` index, and the loser gets 500. Category and email duplicate checks are check-then-insert, so races surface as 500 (except on category update, which maps them to 409). |
| **KI-30** | CORS | If `FRONTEND_URL` is unset, the server sends `Access-Control-Allow-Origin: *` together with `Allow-Credentials: true`. Browsers reject this for credentialed requests. Only one origin can be configured. |
| **KI-31** | Data | Category and product name uniqueness is case-sensitive, so "Jar Candles" and "jar candles" can coexist. |

---

## 14. Coverage Checklist

### 14.1 Source files read

| File | Role |
|---|---|
| `server.js` | Entry point: environment loading, cookie and body parsing, CORS, static files, route mounting, listen |
| `config/db.js` | MongoDB connection and exit-on-failure |
| `middleware/auth.middleware.js` | Authentication guard (cookie JWT) |
| `middleware/admin.middleware.js` | Admin role guard |
| `middleware/multer.js` | Upload storage, naming, type filter, size limit |
| `models/user.model.js` | `users` schema |
| `models/Category.js` | `categories` schema |
| `models/Product.js` | `products` schema |
| `models/cart.model.js` | `carts` schema |
| `models/order.model.js` | `orders` schema |
| `models/banner.model.js` | `banners` schema |
| `models/promoCard.model.js` | `promocards` schema |
| `routes/auth.routes.js` | Auth routes |
| `routes/categoryRoutes.js` | Category routes |
| `routes/productRoutes.js` | Product routes |
| `routes/cart.routes.js` | Cart routes |
| `routes/order.routes.js` | Order routes |
| `routes/banner.routes.js` | Banner routes |
| `routes/promoCard.routes.js` | Promo-card routes |
| `controllers/auth.controller.js` | Register, login, me, logout |
| `controllers/category.controller.js` | Category CRUD and image cleanup |
| `controllers/product.controller.js` | Product CRUD and image cleanup |
| `controllers/cart.controller.js` | Cart operations |
| `controllers/order.controller.js` | Order create, list, detail, admin list, status |
| `controllers/banner.controller.js` | Banner create, list, delete |
| `controllers/promoCard.controller.js` | Promo-card create, list, delete |
| `package.json` | Start command and declared dependencies (to identify unused ones) |
| `.env` | Variable **names** only; values not reproduced |
| `.gitignore` | Confirms `uploads` and dependencies are ignored |
| `package-lock.json` | Not read line by line (dependency lock file); installed versions were checked to confirm hashing, aggregation, upload-error and CORS behavior |
| `uploads/` | Contents skipped as instructed (30 existing files, naming pattern confirmed) |

### 14.2 Summary counts

| Item | Count |
|---|---|
| MongoDB collections | **7**: `users`, `categories`, `products`, `carts`, `orders`, `banners`, `promocards` |
| API endpoints (under `/api`) | **31**: auth 4, category 4, product 4, cart 6, order 5, banner 4, promo-card 4 |
| Other routes | **2**: `GET /` health check, `GET /uploads/*` static files |
| Total routes documented | **33** |
| Functional requirements | **122** (FR-001 to FR-122) |
| Business rules | **37** (BR-01 to BR-37) |
| Known issues | **31** (KI-01 to KI-31) |

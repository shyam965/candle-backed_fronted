"""Home and Shop (FE §5.3–5.4) and the product-card add-to-cart action (FR-UI-040, 054, 055, 059, 060)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse, Response
from pymongo.errors import PyMongoError

from app.core.errors import AppError
from app.core.htmx import add_trigger, is_htmx, toast
from app.core.ids import parse_object_id
from app.core.templating import render
from app.security.deps import current_user
from app.services import cart_service, catalog, category_service, merch_service, product_service
from app.services.merch_service import BANNER, PROMO
from app.web.common import form_data, ui_router

log = logging.getLogger("akrf.storefront")
router = ui_router()


async def _names(request: Request) -> dict[Any, str]:
    return {c["_id"]: c["name"] for c in await category_service.list_all(request.app.state.db)}


def _cards(products: list[dict[str, Any]], names: dict[Any, str]) -> list[dict[str, Any]]:
    return [{**p, "category_name": product_service.category_name(p, names, "Candles")} for p in products]


async def _section(request: Request, template: str, loader, error_message: str, **extra: Any) -> Response:
    """Render one independently-loaded section; failures show an error box + Retry + toast (D-46)."""
    try:
        context = await loader()
    except PyMongoError:
        log.exception("Section failed: %s", template)
        response = await render(request, template, {"load_error": error_message, **extra}, full_page=False)
        return toast(response, error_message, "error")
    return await render(request, template, {**context, **extra}, full_page=False)


# ---------- Home ----------

@router.get("/")
async def home(request: Request) -> Response:
    return await render(request, "pages/home.html")


@router.get("/_p/home/banners")
async def home_banners(request: Request) -> Response:
    async def load() -> dict[str, Any]:
        return {"banners": await merch_service.list_active(request.app.state.db, BANNER)}
    return await _section(request, "partials/home/banners.html", load, "Unable to load banners")


@router.get("/_p/home/promo-cards")
async def home_promo_cards(request: Request) -> Response:
    async def load() -> dict[str, Any]:
        return {"cards": await merch_service.list_active(request.app.state.db, PROMO)}
    return await _section(request, "partials/home/promo_cards.html", load, "Unable to load promotional cards")


@router.get("/_p/home/categories")
async def home_categories(request: Request) -> Response:
    async def load() -> dict[str, Any]:
        return {"categories": await category_service.list_all(request.app.state.db)}
    return await _section(request, "partials/home/categories.html", load, "Unable to load categories")


@router.get("/_p/home/products")
async def home_products(request: Request) -> Response:
    async def load() -> dict[str, Any]:
        names = await _names(request)
        products = await product_service.list_all(request.app.state.db)
        return {"products": _cards(catalog.latest(products, 8), names)}
    return await _section(request, "partials/home/products.html", load, "Unable to load products")


# ---------- Shop ----------

def _shop_params(request: Request) -> dict[str, str]:
    q = request.query_params
    sort = q.get("sort", "default")
    return {
        "category": (q.get("category") or "").strip()[:24],
        "search": (q.get("search") or "").strip()[:100],
        "sort": sort if sort in catalog.SORTS else "default",
    }


def _shop_url(**params: str) -> str:
    clean = {k: v for k, v in params.items() if v and not (k == "sort" and v == "default")}
    return "/shop" + (f"?{urlencode(clean)}" if clean else "")


async def _shop_context(request: Request, params: dict[str, str]) -> dict[str, Any]:
    db = request.app.state.db
    context: dict[str, Any] = {"params": params, "sorts": catalog.SORTS, "shop_url": _shop_url}
    categories: list[dict[str, Any]] = []
    try:
        categories = await category_service.list_all(db)
        context["categories"] = categories
    except PyMongoError:
        log.exception("Shop categories failed")
        context["categories_error"] = "Unable to load categories"
    names = {c["_id"]: c["name"] for c in categories}
    try:
        products = await product_service.list_all(db)
        context["all_count"] = len(products)
        context["counts"] = catalog.category_counts(products)
        view = catalog.shop_view(products, names, category=params["category"] or None,
                                 search=params["search"], sort=params["sort"])
        context["products"] = _cards(view, names)
    except PyMongoError:
        log.exception("Shop products failed")
        context["products_error"] = "Unable to load products"
    selected = parse_object_id(params["category"]) if params["category"] else None
    context["heading"] = names.get(selected, "All Candles") if selected else "All Candles"
    return context


@router.get("/shop")
async def shop(request: Request) -> Response:
    raw = request.query_params
    if "search" in raw and not raw.get("search", "").strip():
        params = _shop_params(request)
        return RedirectResponse(_shop_url(category=params["category"], sort=params["sort"]), status_code=303)
    params = _shop_params(request)
    context = await _shop_context(request, params)
    restoring = request.headers.get("hx-history-restore-request") == "true"
    if is_htmx(request) and not restoring and request.headers.get("hx-target") == "shop-results":
        response = await render(request, "partials/shop/results.html", {**context, "oob": True}, full_page=False)
        response.headers["HX-Push-Url"] = _shop_url(**params)
        for key in ("categories_error", "products_error"):
            if context.get(key):
                toast(response, context[key], "error")
        return response
    return await render(request, "pages/shop.html", context)


# ---------- Add to cart from a product card ----------

@router.post("/cart/add")
async def add_to_cart(request: Request, user: dict | None = Depends(current_user)) -> Response:
    db = request.app.state.db
    data = await form_data(request)
    source = "shop" if data.get("source") == "shop" else "home"
    product = await product_service.get(db, data.get("product_id"))
    names = await _names(request)
    card = _cards([product], names)[0]
    context: dict[str, Any] = {"product": card, "source": source, "oob": True}

    async def respond(message: str, kind: str, *, card_message: str | None = None, added: bool = False,
                      quantity: str = "1") -> Response:
        context.update(card_message=card_message or (message if source == "home" else None), card_kind=kind,
                       added=added, quantity=quantity, status_message=message, status_kind=kind)
        if user is not None:
            context["cart_count"] = await cart_service.count_items(db, user)
        response = await render(request, "partials/add_to_cart_result.html", context, full_page=False)
        return toast(response, message, "success" if kind == "success" else "error")

    if user is None:
        if source == "home":  # FR-UI-040: toast, card message, then /login after 1 s
            response = await respond("Please login first to add products to cart", "error",
                                     card_message="Please login first")
            return add_trigger(response, "redirectAfter", {"url": "/login?redirect=%2F", "delay": 1000})
        return await respond("Please login first to add products to cart.", "error")  # FR-UI-054
    if product_service.stock_of(product) <= 0:
        return await respond("This product is out of stock.", "error")  # FR-UI-059
    try:
        await cart_service.add(db, user, str(product["_id"]), data.get("quantity") or "1")
    except AppError as exc:
        return await respond(exc.message or "Unable to add product to cart", "error", quantity=data.get("quantity") or "1")
    return await respond("Product added to cart", "success", added=True)

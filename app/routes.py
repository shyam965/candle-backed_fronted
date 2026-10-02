"""Router registry. UI routers carry CSRF protection; API routers carry the origin check (D-06)."""

from __future__ import annotations

from fastapi import FastAPI

from app.api import auth as api_auth
from app.api import category as api_category
from app.api import product as api_product
from app.api import merch as api_merch
from app.api import cart as api_cart
from app.api import order as api_order
from app.web import auth, cart, checkout, orders, pages, storefront, system
from app.web.admin import categories as admin_categories
from app.web.admin import products as admin_products
from app.web.admin import merch as admin_merch
from app.web.admin import orders as admin_orders
from app.web.admin import dashboard as admin_dashboard


def include_routers(app: FastAPI) -> None:
    app.include_router(system.router)
    app.include_router(auth.router)
    app.include_router(pages.router)
    app.include_router(storefront.router)
    app.include_router(cart.router)
    app.include_router(checkout.router)
    app.include_router(orders.router)
    app.include_router(admin_dashboard.router)
    app.include_router(admin_categories.router)
    app.include_router(admin_products.router)
    app.include_router(admin_merch.banner_router)
    app.include_router(admin_merch.promo_router)
    app.include_router(admin_orders.router)
    app.include_router(api_auth.router)
    app.include_router(api_category.router)
    app.include_router(api_product.router)
    app.include_router(api_merch.banner_router)
    app.include_router(api_merch.promo_router)
    app.include_router(api_cart.router)
    app.include_router(api_order.router)

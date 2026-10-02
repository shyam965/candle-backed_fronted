"""Seed a DEMO database with realistic data for local UI review. Never touches real data.

Usage:  python scripts/seed_demo.py <mongo_uri> <db_name starting with akrf_demo> <upload_dir>
Creates admin@demo.test / customer@demo.test (password: demo1234).
"""

from __future__ import annotations

import asyncio
import random
import sys
from datetime import timedelta
from pathlib import Path

from playwright.async_api import async_playwright
from pymongo import AsyncMongoClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.documents import new_meta, now_ist  # noqa: E402
from app.db import ensure_indexes  # noqa: E402
from app.security.passwords import hash_password_sync  # noqa: E402
from app.services.order_service import STATUSES, generate_order_id  # noqa: E402

PALETTES = [("#f4d5a8", "#bf641c"), ("#dccde6", "#6d4580"), ("#c7ecd9", "#1f7a55"), ("#fbd3d3", "#b4234a"),
            ("#d6e6fb", "#2b5c9a"), ("#faecd6", "#9d4b1a"), ("#ede6f2", "#3a2443"), ("#f7f0e4", "#7f3d1c")]

CANDLE_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 400' width='{w}' height='{h}' preserveAspectRatio='xMidYMid slice'>
<defs><radialGradient id='g' cx='50%' cy='35%' r='65%'><stop offset='0' stop-color='#fffaf0'/><stop offset='1' stop-color='{bg}'/></radialGradient>
<linearGradient id='f' x1='0' y1='1' x2='0' y2='0'><stop offset='0' stop-color='#bf641c'/><stop offset='.6' stop-color='#e39a44'/><stop offset='1' stop-color='#fff3df'/></linearGradient>
<linearGradient id='w' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='{fg}' stop-opacity='.75'/><stop offset='1' stop-color='{fg}'/></linearGradient></defs>
<rect width='400' height='400' fill='url(#g)'/><ellipse cx='200' cy='340' rx='120' ry='14' fill='#000' opacity='.12'/>
<rect x='130' y='170' width='140' height='170' rx='22' fill='url(#w)'/><ellipse cx='200' cy='170' rx='70' ry='12' fill='#fff' opacity='.55'/>
<rect x='198' y='140' width='4' height='26' rx='2' fill='#241529'/>
<path d='M200 70c10 18 24 28 24 48a24 24 0 0 1-48 0c0-11 5-18 11-24 1 8 5 12 10 12-4-11-2-24 3-36z' fill='url(#f)'/>
<text x='200' y='262' font-family='Georgia,serif' font-size='18' fill='#fff' text-anchor='middle' letter-spacing='2'>{label}</text></svg>"""

CATEGORIES = [("Jar Candles", "Soy wax candles poured into reusable glass jars"),
              ("Pillar Candles", "Free-standing pillars for tables and mantels"),
              ("Gift Sets", "Curated boxes for every celebration"),
              ("Aromatherapy", "Essential-oil blends to relax and recharge"),
              ("Festive Collection", "Diyas and candles for Diwali and Christmas")]
PRODUCTS = [("Lavender Dream Jar", 0, 499, 699, 25), ("Vanilla Bean Jar", 0, 449, None, 12), ("Rose Garden Jar", 0, 549, 649, 0),
            ("Sandalwood Pillar", 1, 399, None, 30), ("Ivory Classic Pillar", 1, 299, 349, 8), ("Royal Gift Box", 2, 1299, 1599, 6),
            ("Mini Trio Set", 2, 899, None, 15), ("Eucalyptus Calm", 3, 599, 699, 20), ("Citrus Burst", 3, 349, None, 3),
            ("Diwali Diya Set", 4, 799, 999, 40), ("Cinnamon Spice", 4, 459, None, 18), ("Midnight Oud", 0, 999, 1199, 5)]


async def render_images(target: Path, specs: list[tuple[str, str, int, int]]) -> list[str]:
    target.mkdir(parents=True, exist_ok=True)
    names = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        for i, (label, kind, w, h) in enumerate(specs):
            bg, fg = PALETTES[i % len(PALETTES)]
            await page.set_viewport_size({"width": w, "height": h})
            await page.set_content(f"<body style='margin:0'>{CANDLE_SVG.format(w=w, h=h, bg=bg, fg=fg, label=label)}</body>")
            name = f"{1790000000000 + i}-{random.randint(0, 10**9)}.png"
            await page.screenshot(path=str(target / name), clip={"x": 0, "y": 0, "width": w, "height": h})
            names.append(f"/uploads/{name}")
        await browser.close()
    return names


async def seed(uri: str, db_name: str, upload_dir: Path) -> None:
    if not db_name.startswith("akrf_demo"):
        raise SystemExit("Refusing to seed: database name must start with 'akrf_demo'")
    client = AsyncMongoClient(uri, tz_aware=True)
    await client.drop_database(db_name)
    db = client[db_name]
    await ensure_indexes(db)
    specs = [(c[0].split()[0].upper(), "cat", 400, 400) for c in CATEGORIES]
    specs += [(p[0].split()[0].upper(), "prod", 600, 600) for p in PRODUCTS]
    specs += [("FESTIVE", "banner", 1400, 600), ("NEW SCENTS", "banner", 1400, 600), ("GIFTS", "promo", 400, 400),
              ("CALM", "promo", 400, 400), ("SALE", "promo", 400, 400)]
    images = await render_images(upload_dir, specs)
    now = now_ist()
    cat_ids = []
    for i, (name, desc) in enumerate(CATEGORIES):
        cat_ids.append((await db.categories.insert_one({"name": name, "description": desc, "image": images[i],
                                                        **new_meta(now - timedelta(days=30 - i))})).inserted_id)
    products = []
    for i, (name, cat, price, old, stock) in enumerate(PRODUCTS):
        doc = {"name": name, "category": cat_ids[cat], "price": price, "stock": stock,
               "description": f"Hand-poured {name.lower()} with a clean, long-lasting burn of 40+ hours.",
               "image": images[len(CATEGORIES) + i], **new_meta(now - timedelta(days=len(PRODUCTS) - i))}
        if old:
            doc["oldPrice"] = old
        doc["_id"] = (await db.products.insert_one(doc)).inserted_id
        products.append(doc)
    b0 = len(CATEGORIES) + len(PRODUCTS)
    await db.banners.insert_many([
        {"title": "Festive Glow Collection", "subtitle": "Hand-poured candles for Diwali — up to 30% off", "image": images[b0],
         "buttonText": "Shop Festive", "buttonLink": f"/shop?category={cat_ids[4]}", "order": 0, "status": True, **new_meta()},
        {"title": "New Signature Scents", "subtitle": "Lavender, oud and sandalwood — just launched", "image": images[b0 + 1],
         "buttonText": "Explore", "buttonLink": "/shop", "order": 1, "status": True, **new_meta()},
    ])
    await db.promocards.insert_many([
        {"title": "Gift Sets", "subtitle": "Perfect for Diwali", "image": images[b0 + 2], "buttonText": "Shop Gifts",
         "buttonLink": f"/shop?category={cat_ids[2]}", "background": "#4b3057", "order": 0, "status": True, **new_meta()},
        {"title": "Aromatherapy", "subtitle": "Breathe in, slow down", "image": images[b0 + 3], "buttonText": "Shop Now",
         "buttonLink": f"/shop?category={cat_ids[3]}", "background": "#08aaa6", "order": 1, "status": True, **new_meta()},
        {"title": "Weekend Sale", "subtitle": "Extra 10% on pillars", "image": images[b0 + 4], "buttonText": "Shop Now",
         "buttonLink": "/shop", "background": "#9d4b1a", "order": 2, "status": True, **new_meta()},
    ])
    password = hash_password_sync("demo1234")
    admin = {"name": "Anita Kapoor", "email": "admin@demo.test", "phone": "9288245292", "password": password, "address": "",
             "city": "", "pincode": "", "role": "admin", **new_meta()}
    customer = {"name": "Asha Verma", "email": "customer@demo.test", "phone": "9876543210", "password": password,
                "address": "12 MG Road, Civil Lines", "city": "Jaipur", "pincode": "302001", "role": "user", **new_meta()}
    await db.users.insert_many([admin, customer])
    for n, status in enumerate(["Pending", "Confirmed", "Processing", "Shipped", "Delivered", "Cancelled", "Delivered", "Pending"]):
        created = now - timedelta(days=n * 2, hours=n)
        picked = random.sample(products, k=1 + n % 3)
        items = [{"product": p["_id"], "name": p["name"], "image": p["image"], "price": p["price"], "quantity": 1 + i % 2,
                  "total": p["price"] * (1 + i % 2)} for i, p in enumerate(picked)]
        total = sum(i["total"] for i in items)
        dates = {s: None for s in STATUSES}
        dates["Pending"] = created
        flow = STATUSES[:5]
        if status in flow:
            for step in flow[1:flow.index(status) + 1]:
                dates[step] = created + timedelta(hours=6 * (flow.index(step)))
        else:
            dates["Cancelled"] = created + timedelta(hours=3)
        await db.orders.insert_one({
            "orderId": generate_order_id(created), "user": customer["_id"],
            "customer": {"name": customer["name"], "mobile": customer["phone"], "address": customer["address"],
                         "city": customer["city"], "pincode": customer["pincode"], "message": "Please gift wrap" if n % 3 == 0 else ""},
            "items": items, "itemsTotal": total, "shipping": 0,
            "shippingStatus": "FREE" if total >= 1099 else "PAYABLE_SEPARATELY", "grandTotal": total,
            "paymentMethod": "WhatsApp Order", "status": status, "statusDates": dates,
            "expectedDelivery": None if status == "Cancelled" else created + timedelta(days=3),
            "createdAt": created, "updatedAt": created, "__v": 0})
    await db.carts.insert_one({"user": customer["_id"], "items": [
        {"product": products[0]["_id"], "quantity": 2, "selected": True},
        {"product": products[5]["_id"], "quantity": 1, "selected": True},
        {"product": products[8]["_id"], "quantity": 1, "selected": False}], **new_meta()})
    await client.close()
    print(f"Seeded {db_name}: {len(CATEGORIES)} categories, {len(PRODUCTS)} products, 8 orders; images in {upload_dir}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    asyncio.run(seed(sys.argv[1], sys.argv[2], Path(sys.argv[3])))

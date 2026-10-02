"""Browser review of every page at 375 / 768 / 1280 px against a seeded DEMO database.

Usage:  python scripts/ui_review.py <output_dir> [--mongo mongodb://localhost:27017]
Starts the app on 127.0.0.1:9100, seeds `akrf_demo_review`, then for each page and viewport records:
console errors, page errors, failed requests (>= 400), horizontal overflow, unlabeled form controls and
images without alt text. Screenshots are written to <output_dir>; a summary is printed and saved as report.md.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.async_api import Page, async_playwright

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:9100"
VIEWPORTS = {"mobile": (375, 812), "tablet": (768, 1024), "desktop": (1280, 900)}
DB = "akrf_demo_review"

A11Y_JS = """() => {
  const problems = [];
  for (const el of document.querySelectorAll('input:not([type=hidden]), select, textarea')) {
    if (el.closest('[hidden]')) continue;
    const id = el.id;
    const labelled = el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') ||
      (id && document.querySelector(`label[for="${id}"]`)) || el.closest('label');
    if (!labelled) problems.push('unlabeled ' + el.tagName.toLowerCase() + '[name=' + el.name + ']');
  }
  for (const img of document.querySelectorAll('img')) if (!img.hasAttribute('alt')) problems.push('img without alt ' + img.src);
  for (const b of document.querySelectorAll('button, a[href]')) {
    const text = (b.innerText || '').trim() || b.getAttribute('aria-label') || b.getAttribute('title');
    if (!text && !b.closest('[hidden]') && b.offsetParent !== null) problems.push('unnamed ' + b.tagName.toLowerCase() + ' ' + b.outerHTML.slice(0, 80));
  }
  const overflow = document.documentElement.scrollWidth - window.innerWidth;
  return {problems, overflow};
}"""


def start_server(uploads: Path, mongo: str) -> subprocess.Popen:
    env = {**os.environ, "APP_ENV": "development", "APP_BASE_URL": BASE, "PORT": "9100", "MONGO_URI": mongo,
           "MONGO_DB_NAME": DB, "SECRET_KEY": "review-" + "k" * 40, "COOKIE_SECURE": "false",
           "UPLOAD_DIR": str(uploads), "LOG_LEVEL": "WARNING", "HOST": "127.0.0.1"}
    proc = subprocess.Popen([sys.executable, "-m", "app"], cwd=ROOT, env=env)
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/healthz", timeout=1)
            return proc
        except OSError:
            time.sleep(0.5)
    proc.kill()
    raise SystemExit("server did not start")


async def settle(page: Page) -> None:
    """Wait for the page load and for every in-flight HTMX request (tracked by the progress bar) to finish."""
    await page.wait_for_load_state("load")
    await page.wait_for_timeout(300)
    await page.wait_for_function("() => !document.querySelector('#progress-bar.is-active')", timeout=15000)
    await page.wait_for_timeout(250)


async def block_video(context) -> None:
    await context.route("**/*youtube*/**", lambda route: route.abort())


async def login(page: Page, email: str) -> None:
    await page.goto(BASE + "/login")
    await page.fill("#f-email", email)
    await page.fill("#f-password", "demo1234")
    await page.click("#login-form button[type=submit]")
    await page.wait_for_url(lambda url: "/login" not in url)


async def review(out: Path, mongo: str) -> list[dict]:
    results: list[dict] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        for role, email in (("guest", None), ("customer", "customer@demo.test"), ("admin", "admin@demo.test")):
            for vp_name, (w, h) in VIEWPORTS.items():
                context = await browser.new_context(viewport={"width": w, "height": h})
                await block_video(context)
                page = await context.new_page()
                log: list[str] = []
                page_path: dict[str, str] = {}
                page.on("console", lambda m, log=log: log.append(f"console.{m.type}: {m.text}")
                        if m.type == "error" and "youtube" not in m.text and "ERR_FAILED" not in m.text
                        and not ("404" in m.text and page_path.get("p") == "/nope") else None)
                page.on("pageerror", lambda e, log=log: log.append(f"pageerror: {e}"))
                page.on("response", lambda r, log=log: log.append(f"HTTP {r.status} {r.url}")
                        if r.status >= 400 and "/nope" not in r.url and "youtube" not in r.url else None)
                if email:
                    await login(page, email)
                paths = {"guest": ["/", "/shop", "/shop?search=jar&sort=low", "/about", "/contact", "/login", "/register",
                                   "/cart", "/nope"],
                         "customer": ["/", "/shop", "/cart", "/my-orders"],
                         "admin": ["/admin", "/admin/categories", "/admin/products", "/admin/orders", "/admin/banner",
                                   "/admin/promo-card"]}[role]
                if role == "customer":
                    await page.goto(BASE + "/my-orders")
                    await settle(page)
                    first = await page.get_attribute("#orders-list a[href^='/my-orders/']", "href")
                    paths.append(first)
                for path in paths:
                    log.clear()
                    page_path["p"] = path
                    await page.goto(BASE + path)
                    await settle(page)
                    if role == "admin" and path == "/admin/orders":
                        await page.click("#orders-panel button:has-text('View')")
                        await settle(page)
                    info = await page.evaluate(A11Y_JS)
                    name = f"{role}-{vp_name}-{path.strip('/').replace('/', '_').replace('?', '_') or 'home'}"[:90]
                    await page.screenshot(path=str(out / f"{name}.png"), full_page=True)
                    results.append({"role": role, "viewport": vp_name, "path": path, "errors": list(log),
                                    "overflow": info["overflow"], "a11y": info["problems"]})
                await context.close()
        await browser.close()
    return results


async def flows(out: Path) -> list[str]:
    """Exercise the key interactive flows end to end in a real browser."""
    notes: list[str] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        await block_video(context)
        page = await context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await login(page, "customer@demo.test")
        await page.goto(BASE + "/shop")
        await settle(page)
        card = page.locator("article").filter(has_text="Vanilla Bean Jar")
        await card.locator("[data-step='1']").click()
        await card.locator("button[type=submit]").click()
        await page.wait_for_selector("#shop-status .alert-success")
        notes.append("shop add-to-cart: " + (await page.inner_text("#shop-status")).strip())
        notes.append("header badge: " + (await page.inner_text("#cart-badge")).strip())
        await page.fill("#shop-search", "lavender")
        await page.wait_for_timeout(700)
        await settle(page)
        notes.append("search url: " + page.url.replace(BASE, ""))
        await page.goto(BASE + "/cart")
        await settle(page)
        await page.locator("#cart-lines button[aria-label='Increase quantity']").first.click()
        await settle(page)
        notes.append("cart after +: " + (await page.inner_text("#cart-selected-count")).strip())
        await page.locator("#cart-lines li input[type=checkbox]").last.check()
        await settle(page)
        notes.append("cart after selecting last line: " + (await page.inner_text("#cart-selected-count")).strip())
        async with context.expect_page() as popup_info:
            await page.click("#place-order-btn")
        popup = await popup_info.value
        notes.append("whatsapp popup: " + popup.url[:40])
        await popup.close()
        await page.wait_for_url(BASE + "/whatsapp-confirm")
        await settle(page)
        await page.screenshot(path=str(out / "flow-whatsapp-confirm.png"), full_page=True)
        await page.click("#confirm-actions button")
        await page.wait_for_url(BASE + "/my-orders")
        await settle(page)
        notes.append("after confirm: " + page.url.replace(BASE, ""))
        await login(page, "admin@demo.test")
        await page.goto(BASE + "/admin/orders")
        await settle(page)
        page.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
        select = page.locator("select[data-status-select]:not([disabled])").first
        options = await select.locator("option").all_inner_texts()
        await select.select_option(options[1])
        await settle(page)
        toast_text = await page.inner_text("#toasts")
        notes.append(f"admin status change -> {options[1]}; toast: {toast_text.strip()!r}")
        await page.screenshot(path=str(out / "flow-admin-orders.png"), full_page=True)
        notes.append("page errors: " + (json.dumps(errors) if errors else "none"))
        await browser.close()
    return notes


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "ui-review"
    mongo = sys.argv[sys.argv.index("--mongo") + 1] if "--mongo" in sys.argv else "mongodb://localhost:27017"
    out.mkdir(parents=True, exist_ok=True)
    uploads = Path(tempfile.mkdtemp(prefix="akrf-review-"))
    subprocess.run([sys.executable, str(ROOT / "scripts" / "seed_demo.py"), mongo, DB, str(uploads)], check=True)
    server = start_server(uploads, mongo)
    try:
        results = asyncio.run(review(out, mongo))
        notes = asyncio.run(flows(out))
    finally:
        server.terminate()
        server.wait(timeout=10)
    lines = ["# UI review", ""]
    issues = 0
    for r in results:
        bad = r["errors"] or r["overflow"] > 0 or r["a11y"]
        issues += bool(bad)
        status = "ISSUES" if bad else "ok"
        lines.append(f"- [{status}] {r['role']:8} {r['viewport']:7} {r['path']}")
        for e in r["errors"]:
            lines.append(f"    - {e}")
        if r["overflow"] > 0:
            lines.append(f"    - horizontal overflow {r['overflow']}px")
        for a in r["a11y"]:
            lines.append(f"    - a11y: {a}")
    lines += ["", "## Flows"] + [f"- {n}" for n in notes]
    report = "\n".join(lines)
    (out / "report.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"\n{len(results)} page captures, {issues} with issues")
    return 0


if __name__ == "__main__":
    sys.exit(main())

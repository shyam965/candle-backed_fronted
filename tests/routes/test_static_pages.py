"""About and Contact (FR-UI-094–FR-UI-096)."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

from tests.helpers import hx


async def test_about_content_and_links(client):
    r = await client.get("/about")
    assert r.status_code == 200
    for text in ("Our Story", "Our Mission", "Made With Love", "Quality Materials", "Premium Collection", "Beautiful Designs"):
        assert text in r.text
    assert r.text.count('href="/shop"') >= 3


async def test_contact_details(client, app):
    r = await client.get("/contact")
    s = app.state.settings
    for text in (s.business_phone, s.business_email, s.business_address, s.business_hours, s.instagram_url, s.facebook_url):
        assert text in r.text
    assert "Add your business Google Maps embed here" not in r.text and "<iframe" not in r.text


async def test_contact_map_shown_when_configured(app, client):
    app.state.settings.map_embed_url = "https://www.google.com/maps/embed?pb=abc"
    assert 'src="https://www.google.com/maps/embed?pb=abc"' in (await client.get("/contact")).text


async def test_contact_validation(client, app):
    r = await client.post("/contact", data={"name": "", "email": "bad", "subject": "", "message": "  "},
                          headers=await hx(client, app))
    assert r.status_code == 422
    for text in ("Full Name is required", "Please enter a valid email address", "Subject is required", "Your Message is required"):
        assert text in r.text
    assert "openWhatsApp" not in r.headers.get("HX-Trigger", "")


async def test_contact_triggers_whatsapp(client, app):
    data = {"name": "Asha", "email": "asha@example.com", "phone": "", "subject": "Gift", "message": "Need 10 jars"}
    r = await client.post("/contact", data=data, headers=await hx(client, app))
    assert r.status_code == 200
    url = json.loads(r.headers["HX-Trigger"])["openWhatsApp"]["url"]
    parts = urlsplit(url)
    assert parts.netloc == "wa.me" and parts.path == "/919288245292"
    text = parse_qs(parts.query)["text"][0]
    assert text.startswith("*AK ROYAL FLAMES - CONTACT MESSAGE*") and "*Phone:* Not provided" in text
    assert 'value="Asha"' not in r.text  # form cleared


async def test_contact_requires_csrf(client):
    r = await client.post("/contact", data={"name": "x"}, headers={"HX-Request": "true"})
    assert r.status_code == 403

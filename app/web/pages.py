"""Static pages: About (FR-UI-096) and Contact with WhatsApp contact form (FR-UI-094/095)."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import Response

from app.core.htmx import add_trigger
from app.core.templating import render
from app.core.validators import digits_only, is_email
from app.services import whatsapp
from app.web.common import form_data, respond_form, ui_router

router = ui_router()

CONTACT_FIELDS = ("name", "email", "phone", "subject", "message")
LIMITS = {"name": 120, "email": 254, "phone": 15, "subject": 150, "message": 1000}


@router.get("/about")
async def about(request: Request) -> Response:
    return await render(request, "pages/about.html")


@router.get("/contact")
async def contact(request: Request) -> Response:
    return await render(request, "pages/contact.html", {"values": {}, "errors": {}})


def validate_contact(data: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    values = {k: (data.get(k) or "").strip() for k in CONTACT_FIELDS}
    values["phone"] = digits_only(values["phone"], 15)
    errors: dict[str, str] = {}
    labels = {"name": "Full Name", "email": "Email Address", "subject": "Subject", "message": "Your Message"}
    for key, label in labels.items():
        if not values[key]:
            errors[key] = f"{label} is required"
        elif len(values[key]) > LIMITS[key]:
            errors[key] = f"{label} must be at most {LIMITS[key]} characters"
    if values["email"] and "email" not in errors and not is_email(values["email"]):
        errors["email"] = "Please enter a valid email address"
    return values, errors


@router.post("/contact")
async def contact_submit(request: Request) -> Response:
    values, errors = validate_contact(await form_data(request))
    if errors:
        return await respond_form(request, page="pages/contact.html", partial="partials/contact_form.html",
                                  context={"values": values, "errors": errors})
    url = whatsapp.wa_me(request.app.state.settings.whatsapp_number, whatsapp.contact_message(values))
    response = await render(request, "partials/contact_form.html",
                            {"values": {}, "errors": {}, "whatsapp_url": url}, full_page=False)
    add_trigger(response, "openWhatsApp", {"url": url})
    return response

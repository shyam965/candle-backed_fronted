"""WhatsApp message builders (FR-UI-075, FR-UI-079, FR-UI-094, D-34)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from app.services import whatsapp

PENDING = {
    "orderId": "AKRF-1790700056594-4821",
    "customer": {"name": "Asha", "mobile": "9876543210", "address": "12 MG Road", "city": "Jaipur", "pincode": "302001",
                 "message": "Gift wrap"},
    "items": [{"name": "Rose Jar", "price": 499, "quantity": 2, "total": 998}],
    "itemsTotal": 998, "shipping": 0, "shippingStatus": "PAYABLE_SEPARATELY", "grandTotal": 998,
}


def test_order_message_sections():
    text = whatsapp.order_message(PENDING, 1099)
    for part in ("*ORDER INFORMATION*", "Order ID: AKRF-1790700056594-4821", "Total Items: 2", "*CUSTOMER DETAILS*",
                 "*PRODUCT DETAILS*", "Qty: 2 x ₹499 = ₹998", "*PAYMENT SUMMARY*", "Grand Total: ₹998",
                 "*DELIVERY CHARGES:*", "*CUSTOMER NOTE*", "Gift wrap", "Thank you"):
        assert part in text
    free = whatsapp.order_message({**PENDING, "shippingStatus": "FREE", "customer": {**PENDING["customer"], "message": ""}}, 1099)
    assert "*FREE DELIVERY:* Order value is ₹1,099 or above." in free and "CUSTOMER NOTE" not in free


def test_links():
    wa = urlsplit(whatsapp.wa_me("919288245292", "Hi & bye"))
    assert wa.netloc == "wa.me" and wa.path == "/919288245292" and parse_qs(wa.query)["text"] == ["Hi & bye"]
    api = urlsplit(whatsapp.api_send("919288245292", "x"))
    assert api.netloc == "api.whatsapp.com" and parse_qs(api.query)["phone"] == ["919288245292"]


def test_contact_message():
    text = whatsapp.contact_message({"name": "A", "email": "a@b.co", "phone": "", "subject": "S", "message": "M"})
    assert text.startswith("*AK ROYAL FLAMES - CONTACT MESSAGE*") and "*Phone:* Not provided" in text

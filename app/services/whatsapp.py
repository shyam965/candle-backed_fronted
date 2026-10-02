"""WhatsApp click-to-chat messages and links (FE §5.5, §5.6, §5.9; D-34, D-39)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.core.formatting import inr


def wa_me(number: str, text: str) -> str:
    return f"https://wa.me/{number}?text={quote(text, safe='')}"


def api_send(number: str, text: str) -> str:
    return f"https://api.whatsapp.com/send?phone={number}&text={quote(text, safe='')}"


def contact_message(data: dict[str, str]) -> str:
    return "\n".join([
        "*AK ROYAL FLAMES - CONTACT MESSAGE*",
        "",
        f"*Name:* {data['name']}",
        f"*Email:* {data['email']}",
        f"*Phone:* {data.get('phone') or 'Not provided'}",
        f"*Subject:* {data['subject']}",
        "",
        "*Message:*",
        data["message"],
    ])


def order_message(pending: dict[str, Any], threshold: float) -> str:
    """Formatted order text with the order id used for the stored order (FR-UI-075, D-34)."""
    customer = pending["customer"]
    items = pending["items"]
    total_qty = sum(int(i["quantity"]) for i in items)
    lines = [
        "*AK ROYAL FLAMES - NEW ORDER*",
        "",
        "*ORDER INFORMATION*",
        f"Order ID: {pending['orderId']}",
        f"Total Items: {total_qty}",
        "",
        "*CUSTOMER DETAILS*",
        f"Name: {customer['name']}",
        f"Mobile: {customer['mobile']}",
        f"Address: {customer['address']}",
        f"City: {customer['city']}",
        f"Pincode: {customer['pincode']}",
        "",
        "*PRODUCT DETAILS*",
    ]
    for index, item in enumerate(items, start=1):
        lines += [
            f"{index}. {item['name']}",
            f"   Qty: {item['quantity']} x {inr(item['price'])} = {inr(item['total'])}",
        ]
    lines += [
        "",
        "*PAYMENT SUMMARY*",
        f"Items Total: {inr(pending['itemsTotal'])}",
        f"Delivery: {'FREE' if pending['shippingStatus'] == 'FREE' else 'Pay Separately'}",
        f"Grand Total: {inr(pending['grandTotal'])}",
        "",
    ]
    if pending["shippingStatus"] == "FREE":
        lines.append(f"*FREE DELIVERY:* Order value is {inr(threshold)} or above.")
    else:
        lines.append("*DELIVERY CHARGES:* Actual delivery charges will be paid separately to the delivery "
                     "person at the time of delivery.")
    if customer.get("message"):
        lines += ["", "*CUSTOMER NOTE*", customer["message"]]
    lines += ["", "Thank you for shopping with AK Royal Flames!"]
    return "\n".join(lines)

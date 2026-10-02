"""Pydantic v2 schemas of the stored MongoDB documents (BE §4).

Request input is validated by explicit validators that reproduce the exact user-facing messages in the
specs; these models are the persistence contract. `check()` validates every new document before insert
so a programming error can never write a wrong type or enum value into the shared database.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, PlainValidator

ObjectIdField = Annotated[ObjectId, PlainValidator(lambda v: v if isinstance(v, ObjectId) else ObjectId(v))]
Number = Annotated[int | float, Field(allow_inf_nan=False)]
OrderStatus = Literal["Pending", "Confirmed", "Processing", "Shipped", "Delivered", "Cancelled"]


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True, populate_by_name=True)

    id: ObjectIdField | None = Field(default=None, alias="_id")
    createdAt: datetime
    updatedAt: datetime
    v: int = Field(default=0, alias="__v", ge=0)


class UserDoc(Document):
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    phone: str = ""
    password: str = Field(pattern=r"^\$2[aby]\$\d{2}\$.{53}$")
    address: str = ""
    city: str = ""
    pincode: str = ""
    role: Literal["user", "admin"] = "user"


class CategoryDoc(Document):
    name: str = Field(min_length=1)
    description: str = ""
    image: str = Field(min_length=1)


class ProductDoc(Document):
    name: str = Field(min_length=1)
    category: ObjectIdField
    price: Number = Field(ge=1)
    oldPrice: Number | None = Field(default=None, ge=1)
    stock: int = Field(ge=0)
    description: str = ""
    image: str = Field(min_length=1)


class CartItem(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    product: ObjectIdField
    quantity: int = Field(default=1, ge=1)
    selected: bool = True


class CartDoc(Document):
    user: ObjectIdField
    items: list[CartItem] = []


class Customer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    mobile: str = Field(min_length=1)
    address: str = Field(min_length=1)
    city: str = Field(min_length=1)
    pincode: str = Field(min_length=1)
    message: str = ""


class OrderItem(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    product: ObjectIdField
    name: str = Field(min_length=1)
    image: str = ""
    price: Number
    quantity: int = Field(ge=1)
    total: Number


class StatusDates(BaseModel):
    model_config = ConfigDict(extra="forbid")
    Pending: datetime | None = None
    Confirmed: datetime | None = None
    Processing: datetime | None = None
    Shipped: datetime | None = None
    Delivered: datetime | None = None
    Cancelled: datetime | None = None


class OrderDoc(Document):
    orderId: str = Field(pattern=r"^AKRF-\d+-\d{4}$")
    user: ObjectIdField
    customer: Customer
    items: list[OrderItem] = Field(min_length=1)
    itemsTotal: Number
    shipping: Number = 0
    shippingStatus: Literal["FREE", "PAYABLE_SEPARATELY"] | None = "FREE"
    grandTotal: Number
    paymentMethod: str = "WhatsApp Order"
    status: OrderStatus = "Pending"
    statusDates: StatusDates
    expectedDelivery: datetime | None = None


class BannerDoc(Document):
    title: str = Field(min_length=1)
    subtitle: str = ""
    image: str = Field(min_length=1)
    buttonText: str = "Shop Now"
    buttonLink: str = "/shop"
    order: Number = 0
    status: bool = True


class PromoCardDoc(BannerDoc):
    background: str = "#08aaa6"


def check(model: type[Document], doc: dict[str, Any]) -> dict[str, Any]:
    """Validate a document about to be inserted; returns it unchanged (dicts keep BSON-native types)."""
    model.model_validate(doc)
    return doc

import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


# The Philippines has no daylight saving time, so a fixed UTC+8 offset is exact.
PH_TZ = timezone(timedelta(hours=8))


def ph_now() -> datetime:
    """Current Philippine local date and time (naive, for storage and display)."""
    return datetime.now(PH_TZ).replace(tzinfo=None)


def ph_today() -> date:
    """Current Philippine local date, used for membership validity and receipts."""
    return ph_now().date()


PHONE_PATTERN = re.compile(r"^(09|\+639)\d{9}$")


def clean_phone(raw: str) -> str | None:
    """Return the cleaned normalized number (09XXXXXXXXX) if the format is valid, otherwise None."""
    if not raw:
        return None
    cleaned = re.sub(r"[\s-]", "", raw)
    if not PHONE_PATTERN.match(cleaned):
        return None
    if cleaned.startswith("+63"):
        return "0" + cleaned[3:]
    return cleaned


def is_latin_letter(ch: str) -> bool:
    return len(ch) == 1 and ch.isalpha() and "LATIN" in unicodedata.name(ch, "")


def clean_name(raw_name: str) -> str:
    if not raw_name:
        return ""
    return re.sub(r"\s+", " ", raw_name.strip())


def is_valid_name(raw_name: str) -> bool:
    name = clean_name(raw_name)
    if not name or len(name) > 50:
        return False
    if not is_latin_letter(name[0]) or not is_latin_letter(name[-1]):
        return False
    allowed_separators = {" ", "-", "'", "\u2019"}
    for i, ch in enumerate(name):
        if is_latin_letter(ch):
            continue
        elif ch in allowed_separators:
            if i == 0 or i == len(name) - 1:
                return False
            if not is_latin_letter(name[i - 1]) or not is_latin_letter(name[i + 1]):
                return False
        else:
            return False
    return True


class AppBaseModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class Customer(AppBaseModel):
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    phone: str

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v_clean = clean_name(v)
        if len(v_clean) > 50:
            raise ValueError("must be 50 characters or fewer")
        if not is_valid_name(v_clean):
            raise ValueError(
                "may contain only letters, spaces, hyphens, and apostrophes"
            )
        return v_clean

    @field_validator("phone")
    @classmethod
    def validate_ph_phone(cls, v: str) -> str:
        cleaned = clean_phone(v)
        if not cleaned:
            raise ValueError("Enter a valid mobile number: 09XXXXXXXXX or +639XXXXXXXXX.")
        return cleaned


class Membership(AppBaseModel):
    customer_id: int = Field(gt=0)
    plan: str = Field(min_length=1)
    start_date: date
    end_date: date
    method: str | None = None
    amount_tendered: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    request_id: str | None = Field(default=None, max_length=64)


class MembershipRegistration(Membership):
    # New customer details are created atomically with the paid membership.
    customer_id: int | None = Field(default=None, gt=0)
    new_customer: Customer | None = None


CATEGORY_TO_TYPE = {
    "Membership": "Service",
    "Gym Access": "Service",
    "Coaching": "Service",
    "Beverage": "Product",
    "Supplement": "Product",
    "Merchandise": "Product",
}

PRODUCT_CATEGORIES = tuple(CATEGORY_TO_TYPE.keys())


def normalize_method(v: str) -> str:
    if not isinstance(v, str):
        return v
    low = v.strip().lower()
    if low in ("cash", "c"):
        return "Cash"
    if low in ("e-wallet", "ewallet", "e"):
        return "E-Wallet"
    return v.strip()


def normalize_category(v: str) -> str:
    if not isinstance(v, str):
        return v
    low = v.strip().lower()
    for cat in PRODUCT_CATEGORIES:
        if low == cat.lower():
            return cat
    return v.strip()


class Payment(AppBaseModel):
    customer_id: int = Field(gt=0)
    description: str = Field(min_length=1)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    method: Literal["Cash", "E-Wallet"]

    @field_validator("method", mode="before")
    @classmethod
    def validate_method_case(cls, v: str) -> str:
        return normalize_method(v)


class Product(AppBaseModel):
    name: str = Field(min_length=1, max_length=80)
    category: Literal[
        "Membership",
        "Gym Access",
        "Coaching",
        "Beverage",
        "Supplement",
        "Merchandise",
    ]
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)

    @field_validator("category", mode="before")
    @classmethod
    def validate_category_case(cls, v: str) -> str:
        return normalize_category(v)

    @property
    def item_type(self) -> str:
        return CATEGORY_TO_TYPE[self.category]


class PurchaseItem(AppBaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class Purchase(AppBaseModel):
    customer_id: int = Field(gt=0)
    method: Literal["Cash", "E-Wallet"]
    product_id: int | None = Field(default=None, gt=0)
    quantity: int | None = Field(default=None, gt=0)
    items: list[PurchaseItem] = Field(default_factory=list)

    @field_validator("method", mode="before")
    @classmethod
    def validate_method_case(cls, v: str) -> str:
        return normalize_method(v)


class SaleLineItemCreate(AppBaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=99)


class SaleCreate(AppBaseModel):
    customer_id: int | None = None
    payment_method: Literal["Cash", "E-Wallet"]
    amount_tendered: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    items: list[SaleLineItemCreate] = Field(min_length=1)
    request_id: str | None = Field(default=None, max_length=64)

    @field_validator("payment_method", mode="before")
    @classmethod
    def validate_payment_method(cls, v: str) -> str:
        return normalize_method(v)


class QuoteRequest(AppBaseModel):
    customer_id: int | None = None
    items: list[SaleLineItemCreate] = Field(min_length=1)


class DailySessionCreate(AppBaseModel):
    customer_id: int | None = None
    payment_method: Literal["Cash", "E-Wallet"]
    amount_tendered: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    request_id: str | None = Field(default=None, max_length=64)

    @field_validator("payment_method", mode="before")
    @classmethod
    def validate_payment_method(cls, v: str) -> str:
        return normalize_method(v)


class SaleVoid(AppBaseModel):
    reason: str = Field(min_length=1)


class Trainer(AppBaseModel):
    name: str = Field(min_length=1, max_length=50)
    status: Literal["Active", "Inactive"] = "Active"


class TrainerSessionCreate(AppBaseModel):
    customer_id: int | None = Field(default=None, gt=0)
    new_customer: Customer | None = None
    trainer_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    session_datetime: str | None = None
    payment_method: Literal["Cash", "E-Wallet"]
    amount_tendered: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    request_id: str | None = Field(default=None, max_length=64)

    @field_validator("payment_method", mode="before")
    @classmethod
    def validate_payment_method(cls, v: str) -> str:
        return normalize_method(v)

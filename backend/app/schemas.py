from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    role: Literal["coordinator", "supplier"]


class LoginRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(APIModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: dict


class CreateOrganizationRequest(APIModel):
    name: str = Field(min_length=2, max_length=160)


class RequirementInput(APIModel):
    item: str = Field(min_length=1, max_length=160)
    quantity: int = Field(gt=0, le=1_000_000)

    @field_validator("item")
    @classmethod
    def normalize_item(cls, value: str) -> str:
        return value.strip().lower()


class MissionCreateRequest(APIModel):
    organization_id: str
    name: str = Field(min_length=2, max_length=200)
    emergency_event_id: str | None = Field(default=None, max_length=200)
    delivery_location: str = Field(min_length=2, max_length=400)
    delivery_deadline: datetime
    budget: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    requirements: list[RequirementInput] = Field(min_length=1, max_length=100)
    max_supplier_share: Decimal | None = Field(default=None, gt=0, le=1)
    single_source_only: bool = False

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class InvitationCreateRequest(APIModel):
    supplier_email: EmailStr


class QuoteLineInput(APIModel):
    item: str = Field(min_length=1, max_length=160)
    unit_price: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    available_quantity: int = Field(gt=0, le=1_000_000)
    delivery_date: datetime
    restrictions: str | None = Field(default=None, max_length=2_000)
    evidence_url: str | None = Field(default=None, max_length=2_000)

    @field_validator("item")
    @classmethod
    def normalize_item(cls, value: str) -> str:
        return value.strip().lower()


class QuoteCreateRequest(APIModel):
    invitation_token: str = Field(min_length=20, max_length=300)
    expires_at: datetime
    shipping_cost: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    lines: list[QuoteLineInput] = Field(min_length=1, max_length=100)


class QuoteUpdateRequest(APIModel):
    expires_at: datetime
    shipping_cost: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    lines: list[QuoteLineInput] = Field(min_length=1, max_length=100)


class PurchaseOrderSendRequest(APIModel):
    confirm: Literal[True]


class SupplierResponseRequest(APIModel):
    accepted: bool
    reason: str | None = Field(default=None, max_length=1_000)


class FulfillmentUpdateRequest(APIModel):
    status: Literal["in_fulfillment", "completed", "cancelled"]
    note: str = Field(min_length=1, max_length=1_000)

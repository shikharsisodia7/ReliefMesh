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
    # Demo organizations allow a labeled self-approval override; real organizations enforce segregation of duties.
    demo: bool = False


class MemberInviteRequest(APIModel):
    email: EmailStr
    role: Literal["approver", "coordinator", "admin"] = "approver"


class RequirementInput(APIModel):
    id: str | None = Field(default=None, pattern=r"^req_[a-z0-9]{6,32}$")
    item: str = Field(min_length=1, max_length=160)
    quantity: int = Field(gt=0, le=1_000_000)

    @field_validator("item")
    @classmethod
    def normalize_item(cls, value: str) -> str:
        return value.strip().lower()


class MissionCreateRequest(APIModel):
    organization_id: str
    name: str = Field(min_length=2, max_length=200)
    community_label: str | None = Field(default=None, min_length=3, max_length=200)
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
    requirement_id: str | None = Field(default=None, max_length=80)
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


class SupplierProfileInput(APIModel):
    legal_name: str = Field(min_length=2, max_length=200)
    website: str | None = Field(default=None, max_length=300)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    contact_name: str | None = Field(default=None, max_length=160)
    contact_phone: str | None = Field(default=None, max_length=40)

    @field_validator("legal_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("country")
    @classmethod
    def upper_country(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class QuoteCreateRequest(APIModel):
    invitation_token: str = Field(min_length=20, max_length=300)
    expires_at: datetime
    currency: str = Field(default="USD", min_length=3, max_length=3)
    shipping_cost: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    lines: list[QuoteLineInput] = Field(min_length=1, max_length=100)
    supplier_profile: SupplierProfileInput | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class QuoteDraftRequest(APIModel):
    text: str = Field(min_length=20, max_length=12_000)


class QuoteUpdateRequest(APIModel):
    expires_at: datetime
    currency: str = Field(default="USD", min_length=3, max_length=3)
    shipping_cost: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    lines: list[QuoteLineInput] = Field(min_length=1, max_length=100)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class PurchaseOrderSendRequest(APIModel):
    confirm: Literal[True]


class SupplierResponseRequest(APIModel):
    accepted: bool
    reason: str | None = Field(default=None, max_length=1_000)


class FulfillmentUpdateRequest(APIModel):
    status: Literal["in_fulfillment", "completed", "cancelled"]
    note: str = Field(min_length=1, max_length=1_000)


class SupplierReviewRequest(APIModel):
    action: Literal["clear", "block", "unblock"]
    rule_id: str | None = Field(default=None, max_length=80)
    reason: str = Field(min_length=3, max_length=1_000)


class DisruptionRequest(APIModel):
    kind: Literal["withdraw", "reduce_inventory", "raise_price", "delay_eta", "block_supplier"]
    supplier_id: str = Field(min_length=1, max_length=80)
    item: str | None = Field(default=None, max_length=160)
    quantity: int | None = Field(default=None, gt=0, le=1_000_000)
    unit_price: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    delay_hours: int | None = Field(default=None, gt=0, le=24 * 60)
    reason: str | None = Field(default=None, max_length=500)


class DiscoveryRequest(APIModel):
    query: str = Field(min_length=2, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    max_results: int = Field(default=8, ge=1, le=25)


class LeadInviteRequest(APIModel):
    supplier_email: EmailStr


class AgentTokenRequest(APIModel):
    name: str = Field(min_length=2, max_length=120)


class EvidenceRefreshRequest(APIModel):
    supplier_ids: list[str] | None = Field(default=None, max_length=50)

"""Model Fase 69 — mesin harga: skema diskon, promo, kupon."""
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

import reference as ref


class BookingFeePayIn(BaseModel):
    amount: int = Field(gt=0)
    method: ref.PaymentMethod = "transfer"
    note: Optional[str] = None


class BookingFeeRefundIn(BaseModel):
    amount: int = Field(ge=0)
    method: ref.PaymentMethod = "transfer"
    note: Optional[str] = None
    finalize: bool = False


class BookingFeeRejectIn(BaseModel):
    reason: str = Field(min_length=10)


class PortalBookingFeeProofIn(BaseModel):
    deal_id: str
    amount: int = Field(gt=0)
    transfer_date: str
    file_ids: List[str] = Field(min_length=1)
    bank_name: Optional[str] = None
    note: Optional[str] = None


from models_v2 import _code


class PricingRuleBase(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    kind: str = "percent"
    value: float = Field(ge=0)
    max_amount: int = Field(default=0, ge=0)
    applies_project_ids: List[str] = []
    applies_unit_types: List[str] = []
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    active: bool = True
    note: Optional[str] = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        if v not in ("percent", "amount"):
            raise ValueError("Jenis nilai harus 'percent' atau 'amount'.")
        return v

    @field_validator("value")
    @classmethod
    def _value(cls, v, info):
        if info.data.get("kind") == "percent" and v > 100:
            raise ValueError("Persen potongan maksimal 100.")
        return v


class DiscountSchemeIn(PricingRuleBase):
    code: str
    requires_approval: bool = False
    _c = field_validator("code")(_code)


class PromoIn(PricingRuleBase):
    code: str
    stackable: bool = True
    _c = field_validator("code")(_code)


class CouponIn(PricingRuleBase):
    code: str
    quota_total: int = Field(default=0, ge=0)
    quota_per_customer: int = Field(default=1, ge=0)
    _c = field_validator("code")(_code)


class PricingRulePatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=120)
    kind: Optional[str] = None
    value: Optional[float] = Field(default=None, ge=0)
    max_amount: Optional[int] = Field(default=None, ge=0)
    applies_project_ids: Optional[List[str]] = None
    applies_unit_types: Optional[List[str]] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    active: Optional[bool] = None
    note: Optional[str] = None
    requires_approval: Optional[bool] = None
    stackable: Optional[bool] = None
    quota_total: Optional[int] = Field(default=None, ge=0)
    quota_per_customer: Optional[int] = Field(default=None, ge=0)


class CouponValidateIn(BaseModel):
    code: str
    unit_id: str
    lead_id: Optional[str] = None


class PricingSelection(BaseModel):
    """Pilihan potongan pada penawaran/reservasi — SEMUA dari aturan yang dikonfigurasi."""
    discount_scheme_id: Optional[str] = None
    promo_id: Optional[str] = None
    coupon_code: Optional[str] = None

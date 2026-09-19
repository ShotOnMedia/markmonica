from dataclasses import dataclass
from typing import Protocol

from app.models import Event, PackageOrder, utcnow

PAYMENT_PENDING = "pending"
PAYMENT_AWAITING = "awaiting_payment"
PAYMENT_PAID = "paid"
PAYMENT_APPROVED = "approved"
PAYMENT_FAILED = "failed"
PAYMENT_CANCELLED = "cancelled"
FINAL_STATUSES = {PAYMENT_APPROVED, PAYMENT_FAILED, PAYMENT_CANCELLED}

@dataclass(frozen=True)
class CheckoutSession:
    provider: str
    reference: str
    redirect_url: str | None = None

class PaymentProvider(Protocol):
    code: str
    def create_checkout(self, order: PackageOrder, event: Event) -> CheckoutSession: ...

class ManualPaymentProvider:
    code = "manual"
    def create_checkout(self, order: PackageOrder, event: Event) -> CheckoutSession:
        return CheckoutSession(provider=self.code, reference=str(order.id))

PROVIDERS: dict[str, PaymentProvider] = {"manual": ManualPaymentProvider()}

def provider_for(code: str) -> PaymentProvider:
    provider = PROVIDERS.get(code)
    if provider is None:
        raise ValueError(f"Unknown payment provider: {code}")
    return provider

def begin_checkout(order: PackageOrder, event: Event, provider_code: str = "manual") -> CheckoutSession:
    if order.status not in {PAYMENT_PENDING, PAYMENT_FAILED}:
        raise ValueError("Only pending or failed orders can start checkout.")
    session = provider_for(provider_code).create_checkout(order, event)
    order.provider = session.provider
    order.provider_reference = session.reference
    order.status = PAYMENT_AWAITING
    order.updated_at = utcnow()
    return session

def mark_paid(order: PackageOrder, provider_reference: str | None = None) -> None:
    if order.status != PAYMENT_AWAITING:
        raise ValueError("Only an awaiting-payment order can be marked paid.")
    if provider_reference:
        order.provider_reference = provider_reference
    order.status = PAYMENT_PAID
    order.updated_at = utcnow()

def mark_failed(order: PackageOrder) -> None:
    if order.status not in {PAYMENT_AWAITING, PAYMENT_PAID}:
        raise ValueError("This order cannot be marked failed.")
    order.status = PAYMENT_FAILED
    order.updated_at = utcnow()

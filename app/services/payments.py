from dataclasses import dataclass
from typing import Protocol
from hashlib import md5
from urllib.parse import quote_plus
from urllib.request import Request as UrlRequest, urlopen

from app.settings import settings
from app.services.credential_vault import decrypt_secret

from app.models import Event, PackageOrder, PaymentProviderConfig, utcnow

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

class PayfastPaymentProvider:
    code = "payfast"
    def create_checkout(self, order: PackageOrder, event: Event) -> CheckoutSession:
        if not settings.payfast_merchant_id or not settings.payfast_merchant_key:
            raise ValueError("Payfast merchant credentials are not configured.")
        return CheckoutSession(provider=self.code, reference=str(order.id), redirect_url=payfast_process_url())

PROVIDERS: dict[str, PaymentProvider] = {"manual": ManualPaymentProvider(), "payfast": PayfastPaymentProvider()}

def payfast_process_url(is_sandbox: bool | None = None) -> str:
    sandbox = settings.payfast_sandbox if is_sandbox is None else is_sandbox
    return "https://sandbox.payfast.co.za/eng/process" if sandbox else "https://www.payfast.co.za/eng/process"

def _encoded(value: object) -> str:
    return quote_plus(str(value).strip(), safe="")

def payfast_signature(data: dict[str, str], passphrase: str | None = None) -> str:
    parts = [f"{key}={_encoded(value)}" for key, value in data.items() if value != "" and key != "signature"]
    if passphrase:
        parts.append(f"passphrase={_encoded(passphrase)}")
    return md5("&".join(parts).encode("utf-8")).hexdigest()

def payfast_checkout_fields(order: PackageOrder, event: Event, email: str, app_url: str) -> dict[str, str]:
    if not settings.payfast_merchant_id or not settings.payfast_merchant_key:
        raise ValueError("Payfast merchant credentials are not configured.")
    base = app_url.rstrip("/")
    data = {"merchant_id": settings.payfast_merchant_id, "merchant_key": settings.payfast_merchant_key, "return_url": f"{base}/payments/payfast/return?order_id={order.id}", "cancel_url": f"{base}/payments/payfast/cancel?order_id={order.id}", "notify_url": f"{base}/payments/payfast/notify", "email_address": email, "m_payment_id": str(order.id), "amount": f"{order.amount_cents / 100:.2f}", "item_name": f"Memories Events - {order.package_code.title()} package"}
    data["signature"] = payfast_signature(data, settings.payfast_passphrase)
    return data

def valid_payfast_itn_signature(form_items: list[tuple[str, str]], passphrase: str | None = None) -> bool:
    supplied = next((value for key, value in form_items if key == "signature"), "")
    data = {key: value for key, value in form_items if key != "signature"}
    return bool(supplied) and supplied == payfast_signature(data, passphrase)


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


def payfast_runtime_config(db):
    provider = db.get(PaymentProviderConfig, "payfast")
    if provider and provider.is_enabled:
        return provider
    return None

def payfast_checkout_fields_for_config(order: PackageOrder, event: Event, email: str, app_url: str, provider: PaymentProviderConfig) -> dict[str, str]:
    if not provider.merchant_id or not provider.merchant_key:
        raise ValueError("Payfast merchant credentials are not configured.")
    base=app_url.rstrip("/")
    merchant_key=decrypt_secret(provider.merchant_key)
    passphrase=decrypt_secret(provider.passphrase)
    data={"merchant_id":provider.merchant_id,"merchant_key":merchant_key,"return_url":f"{base}/payments/payfast/return?order_id={order.id}","cancel_url":f"{base}/payments/payfast/cancel?order_id={order.id}","notify_url":f"{base}/payments/payfast/notify","email_address":email,"m_payment_id":str(order.id),"amount":f"{order.amount_cents/100:.2f}","item_name":f"Memories Events - {order.package_code.title()} package"}
    data["signature"]=payfast_signature(data,passphrase)
    return data


def payfast_validation_url(is_sandbox: bool) -> str:
    host = "sandbox.payfast.co.za" if is_sandbox else "www.payfast.co.za"
    return f"https://{host}/eng/query/validate"

def payfast_param_string(form_items: list[tuple[str, str]]) -> str:
    return "&".join(f"{key}={_encoded(value)}" for key, value in form_items if key != "signature")

def valid_payfast_server_confirmation(form_items: list[tuple[str, str]], is_sandbox: bool, timeout: float = 10.0) -> bool:
    payload = payfast_param_string(form_items).encode("ascii")
    request = UrlRequest(
        payfast_validation_url(is_sandbox),
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status == 200 and response.read().decode("utf-8").strip() == "VALID"
    except Exception:
        return False

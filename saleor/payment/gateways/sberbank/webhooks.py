import base64
import binascii
import hashlib
import hmac
import json
import logging
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlencode

import Adyen
import graphene
from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.core.handlers.wsgi import WSGIRequest
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseNotFound,
    QueryDict,
)
from django.http.request import HttpHeaders
from django.shortcuts import redirect
from graphql_relay import from_global_id

from ....checkout.complete_checkout import complete_checkout
from ....checkout.models import Checkout
from ....core.transactions import transaction_with_commit_on_errors
from ....core.utils.url import prepare_url
from ....discount.utils import fetch_active_discounts
from ....order.actions import (
    cancel_order,
    order_authorized,
    order_captured,
    order_refunded,
)
from ....order.events import external_notification_event
from ....payment.models import Payment, Transaction
from ... import ChargeStatus, PaymentError, TransactionKind
from ...gateway import payment_refund_or_void
from ...interface import GatewayConfig, GatewayResponse
from ...utils import create_payment_information, create_transaction, gateway_postprocess
from .utils import api_call
from .errors import ERRORS as FAILED_STATUSES

logger = logging.getLogger(__name__)


def get_payment(
        payment_id: Optional[str], transaction_id: Optional[str] = None
) -> Optional[Payment]:
    transaction_id = transaction_id or ""
    if not payment_id:
        logger.warning("Missing payment ID. Reference %s", transaction_id)
        return None
    try:
        _type, db_payment_id = from_global_id(payment_id)
    except UnicodeDecodeError:
        logger.warning(
            "Unable to decode the payment ID %s. Reference %s",
            payment_id,
            transaction_id,
        )
        return None
    payment = (
        Payment.objects.prefetch_related("order", "checkout")
            .select_for_update(of=("self",))
            .filter(id=db_payment_id, is_active=True, gateway="korolev.payments.sberbank")
            .first()
    )
    if not payment:
        logger.warning(
            "Payment for %s was not found. Reference %s", payment_id, transaction_id
        )
    return payment


def get_checkout(payment: Payment) -> Optional[Checkout]:
    if not payment.checkout:
        return None
    # Lock checkout in the same way as in checkoutComplete
    return (
        Checkout.objects.select_for_update(of=("self",))
            .prefetch_related("gift_cards", "lines__variant__product", )
            .select_related("shipping_method__shipping_zone")
            .filter(pk=payment.checkout.pk)
            .first()
    )


def get_transaction(
        payment: "Payment", transaction_id: Optional[str], kind: str,
) -> Optional[Transaction]:
    transaction = payment.transactions.filter(kind=kind, token=transaction_id).last()
    return transaction


def create_new_transaction(notification, payment, kind):
    transaction_id = notification.get("pspReference")
    currency = notification.get("amount", {}).get("currency")
    # amount = from_sberbank_price(notification.get("amount", {}).get("value"))
    amount = notification.get("amount", {}).get("value")
    is_success = True if notification.get("success") == "true" else False

    gateway_response = GatewayResponse(
        kind=kind,
        action_required=False,
        transaction_id=transaction_id,
        is_success=is_success,
        amount=amount,
        currency=currency,
        error="",
        raw_response={},
        searchable_key=transaction_id,
    )
    return create_transaction(
        payment,
        kind=kind,
        payment_information=None,
        action_required=False,
        gateway_response=gateway_response,
    )


def create_payment_notification_for_order(
        payment: Payment, success_msg: str, failed_msg: Optional[str], is_success: bool
):
    if not payment.order:
        # Order is not assigned
        return
    msg = success_msg if is_success else failed_msg

    external_notification_event(
        order=payment.order,
        user=None,
        message=msg,
        parameters={"service": payment.gateway, "id": payment.token},
    )


def create_order(payment, checkout):
    try:
        discounts = fetch_active_discounts()
        order, _, _ = complete_checkout(
            checkout=checkout,
            payment_data={},
            store_source=False,
            discounts=discounts,
            user=checkout.user or AnonymousUser(),
        )
    except ValidationError:
        payment_refund_or_void(payment)
        return None
    # Refresh the payment to assign the newly created order
    payment.refresh_from_db()
    return order


def handle_not_created_order(notification, payment, checkout):
    """Process the notification in case when payment doesn't have assigned order."""

    # We don't want to create order for payment that is cancelled or refunded
    if payment.charge_status not in {
        ChargeStatus.NOT_CHARGED,
        ChargeStatus.PENDING,
        ChargeStatus.PARTIALLY_CHARGED,
        ChargeStatus.FULLY_CHARGED,
    }:
        return
    # If the payment is not Auth/Capture, it means that user didn't return to the
    # storefront and we need to finalize the checkout asynchronously.
    action_transaction = create_new_transaction(
        notification, payment, TransactionKind.ACTION_TO_CONFIRM
    )

    # Only when we confirm that notification is success we will create the order
    if action_transaction.is_success and checkout:  # type: ignore
        order = create_order(payment, checkout)
        return order
    return None


def handle_authorization(notification: Dict[str, Any], gateway_config: GatewayConfig):
    # TODO: handle_authorization
    pass


def handle_cancellation(notification: Dict[str, Any], _gateway_config: GatewayConfig):
    # TODO: handle_cancellation
    pass


def handle_cancel_or_refund(
        notification: Dict[str, Any], gateway_config: GatewayConfig
):
    # TODO: handle_cancel_or_refund
    pass


def handle_capture(notification: Dict[str, Any], _gateway_config: GatewayConfig):
    # TODO: handle_capture
    pass


def handle_failed_capture(notification: Dict[str, Any], _gateway_config: GatewayConfig):
    # TODO: handle_failed_capture
    pass


def handle_pending(notification: Dict[str, Any], gateway_config: GatewayConfig):
    # TODO: handle_pending
    pass


def handle_refund(notification: Dict[str, Any], _gateway_config: GatewayConfig):
    # TODO: handle_refund
    pass


def _get_kind(transaction: Optional[Transaction]) -> str:
    if transaction:
        return transaction.kind
    # To proceed the refund we already need to have the capture status so we will use it
    return TransactionKind.CAPTURE


def handle_failed_refund(notification: Dict[str, Any], gateway_config: GatewayConfig):
    # TODO: handle_failed_refund
    pass


def handle_reversed_refund(
        notification: Dict[str, Any], _gateway_config: GatewayConfig
):
    # TODO: handle_reversed_refund
    pass


def handle_refund_with_data(
        notification: Dict[str, Any], gateway_config: GatewayConfig
):
    handle_refund(notification, gateway_config)


def webhook_not_implemented(
        notification: Dict[str, Any], gateway_config: GatewayConfig
):
    # TODO: handle_refund
    pass


EVENT_MAP = {
    "AUTHORISATION": handle_authorization,
    "AUTHORISATION_ADJUSTMENT": webhook_not_implemented,
    "CANCELLATION": handle_cancellation,
    "CANCEL_OR_REFUND": handle_cancel_or_refund,
    "CAPTURE": handle_capture,
    "CAPTURE_FAILED": handle_failed_capture,
    "HANDLED_EXTERNALLY": webhook_not_implemented,
    "ORDER_OPENED": webhook_not_implemented,
    "ORDER_CLOSED": webhook_not_implemented,
    "PENDING": handle_pending,
    "PROCESS_RETRY": webhook_not_implemented,
    "REFUND": handle_refund,
    "REFUND_FAILED": handle_failed_refund,
    "REFUNDED_REVERSED": handle_reversed_refund,
    "REFUND_WITH_DATA": handle_refund_with_data,
    "REPORT_AVAILABLE": webhook_not_implemented,
    "VOID_PENDING_REFUND": webhook_not_implemented,
}


@transaction_with_commit_on_errors()
def handle_additional_actions(
        request: WSGIRequest, gateway_config: "GatewayConfig"
):
    payment_id = request.GET.get("payment")
    checkout_pk = request.GET.get("checkout")

    if not payment_id or not checkout_pk:
        return HttpResponseNotFound()

    payment = get_payment(payment_id, transaction_id=None)
    if not payment:
        return HttpResponseNotFound(
            "Cannot perform payment.There is no active sberbank payment."
        )
    if not payment.checkout or str(payment.checkout.token) != checkout_pk:
        return HttpResponseNotFound(
            "Cannot perform payment.There is no checkout with this payment."
        )

    extra_data = json.loads(payment.extra_data)
    data = extra_data[-1] if isinstance(extra_data, list) else extra_data

    return_url = payment.return_url

    if not return_url:
        return HttpResponseNotFound(
            "Cannot perform payment. Lack of data about returnUrl."
        )

    try:
        request_data = prepare_api_request_data(request, data, payment.pk, checkout_pk)
    except KeyError as e:

        return HttpResponseBadRequest(e.args[0])
    try:
        result = api_call(request_data, gateway_config)
    except PaymentError as e:
        return HttpResponseBadRequest(str(e))

    handle_api_response(payment, result)

    redirect_url = prepare_redirect_url(payment_id, checkout_pk, result, return_url)
    return redirect(redirect_url)


def prepare_api_request_data(request: WSGIRequest, data: dict, payment_pk, checkout_pk):
    params = request.GET
    request_data: "QueryDict" = QueryDict("")

    if all([param in request.GET for param in params]):
        request_data = request.GET
    elif all([param in request.POST for param in params]):
        request_data = request.POST

    if not request_data:
        raise KeyError(
            "Cannot perform payment. Lack of required parameters in request."
        )

    api_request_data = {
        "data": data,
        "payment_id": payment_pk,
        "checkout_pk": checkout_pk,
        "details": {key: request_data[key] for key in params},
    }
    return api_request_data


def prepare_redirect_url(
        payment_id: str, checkout_pk: str, api_response: Adyen.Adyen, return_url: str
):
    checkout_id = graphene.Node.to_global_id(
        "Checkout", checkout_pk  # type: ignore
    )

    params = {
        "checkout": checkout_id,
        "payment": payment_id,
        "resultCode": api_response.get("errorMessage"),
    }

    # Check if further action is needed.
    # if "action" in api_response.message:
    #     params.update(api_response.message["action"])

    return prepare_url(urlencode(params), return_url)


def handle_api_response(
        payment: Payment, response: Adyen.Adyen,
):
    checkout = get_checkout(payment)
    payment_data = create_payment_information(
        payment=payment, payment_token=payment.token,
    )

    error_message = response.get('errorMessage')

    result_code = response.get('errorCode')
    is_success = result_code not in FAILED_STATUSES

    token = ''
    list_attributes = response.get('attributes')
    if list_attributes:
        if len(list_attributes) > 0:
            token = list_attributes[0].get('value')

    gateway_response = GatewayResponse(
        is_success=is_success,
        action_required=False,
        kind=TransactionKind.ACTION_TO_CONFIRM,
        amount=payment_data.amount,
        currency=payment_data.currency,
        transaction_id=token,
        error=error_message,
        raw_response=response,
        searchable_key=token,
    )

    create_transaction(
        payment=payment,
        kind=TransactionKind.ACTION_TO_CONFIRM,
        action_required=False,
        payment_information=payment_data,
        gateway_response=gateway_response,
    )

    if is_success:
        create_order(payment, checkout)

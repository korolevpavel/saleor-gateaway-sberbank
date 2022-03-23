import logging
from urllib.parse import urlencode

from django.core.exceptions import ObjectDoesNotExist

from ....core.utils import build_absolute_uri
from ....core.utils.url import prepare_url
from ... import PaymentError
from ...interface import (
    GatewayConfig,
    GatewayResponse,
    PaymentData,
)

from ...utils import create_transaction, TransactionKind

from ...models import Payment

from .forms import SberbankPaymentForm
from . import errors
from .utils import (
    get_amount_for_sberbank,
    get_error_response,
    get_return_url,
    get_data_for_payment)

from . import client as sberbank

from .tasks import check_status_sberbank_task

# The list of currencies supported by razorpay
SUPPORTED_CURRENCIES = ("RUB", "USD")
PENDING_STATUSES = [""]

# Define what are the Sberbank exceptions,
# as the Sberbank provider doesn't define a base exception as of now.
SBERBANK_EXCEPTIONS = (
    sberbank.errors.BadRequestError,
    sberbank.errors.GatewayError,
    sberbank.errors.ServerError,
)

# Get the logger for this file, it will allow us to log
# error responses from Sberbank.
logger = logging.getLogger(__name__)


def get_error_message_from_sberbank_error(exc: BaseException):
    """Convert a Razorpay error to a user-friendly error message.

    It also logs the exception to stderr.
    """
    logger.exception(exc)
    if isinstance(exc, sberbank.errors.BadRequestError):
        return errors.INVALID_REQUEST
    else:
        return errors.SERVER_ERROR


def check_payment_supported(payment_information: PaymentData):
    """Check that a given payment is supported."""
    if payment_information.currency not in SUPPORTED_CURRENCIES:
        return errors.UNSUPPORTED_CURRENCY % {"currency": payment_information.currency}


def get_client(connection_params):
    """Create a Sberbank client from set-up application keys."""
    sberbank_client = sberbank.Client(
        auth=(connection_params['login'], connection_params['password']),
        sandbox=connection_params['sandbox_mode'])
    return sberbank_client


def process_payment(self, payment_information: PaymentData, config: GatewayConfig
                    ) -> GatewayResponse:
    # return authorize(payment_information, config)

    try:
        payment = Payment.objects.get(pk=payment_information.payment_id)
    except ObjectDoesNotExist:
        raise PaymentError("Payment cannot be performed. Payment does not exists.")

    checkout = payment.checkout
    if checkout is None:
        raise PaymentError(
            "Payment cannot be performed. Checkout for this payment does not exist."
        )

    params = urlencode(
        {"payment": payment_information.graphql_payment_id, "checkout": checkout.pk}
    )
    return_url = prepare_url(
        params,
        build_absolute_uri(
            f"/plugins/{self.PLUGIN_ID}/additional-actions"
        ),  # type: ignore
    )

    error = check_payment_supported(payment_information=payment_information)

    sberbank_client = get_client(config.connection_params)

    try:

        kind = TransactionKind.AUTH
        sberbank_auto_capture = self.config.auto_capture
        if sberbank_auto_capture:
            kind = TransactionKind.CAPTURE

        response = sberbank_client.payment.register(
            order_id=payment_information.payment_id,
            amount=get_amount_for_sberbank(payment_information.amount),
            return_url=return_url,
            data=get_data_for_payment(payment_information))
        # response = {"formUrl": "https://3dsec.sberbank.ru/payment/merchants/sbersafe_id/payment_ru.html?mdOrder=389320f5-d423-714b-bae5-ca325e3d5a10",
        #             "orderId": "389320f5-d423-714b-bae5-ca325e3d5a10"}

        # orderId есть только у успешно зарегистрированных заказов
        if 'orderId' in response:
            token = response['orderId']
            payment_information.token = token

            # Запустим проверку оплаты с API-сбербанка
            # check_status_sberbank_task.delay(order_id=token,
            #                                  connection_params=config.connection_params)

            action = {
                'method': 'GET',
                'type': 'redirect',
                'paymentMethodType': 'sberbank',
                'paymentData': token,
                'url': response['formUrl']
            }

            return GatewayResponse(
                is_success=True,
                action_required=True,
                transaction_id=token,
                amount=payment_information.amount,
                currency=payment_information.currency,
                kind=kind,
                error='',
                raw_response=response,
                action_required_data=action,
                customer_id=payment_information.customer_id,
                searchable_key=token,
            )

        if 'errorCode' in response:
            error_code = int(response['errorCode'])
            if error_code in errors.ERRORS:
                error_msg = response['errorMessage']
                logger.critical('{}:{}'.format(error_code, error_msg))

                return GatewayResponse(
                    is_success=False,
                    action_required=True,
                    amount=payment_information.amount,
                    error=error_msg,
                    transaction_id='',
                    currency=payment_information.currency,
                    kind=kind,
                    raw_response=response,
                    customer_id=payment_information.customer_id,
                )
                # raise Exception(error_msg)

    except SBERBANK_EXCEPTIONS as exc:
        error = get_error_message_from_sberbank_error(exc)

        return GatewayResponse(
            is_success=False,
            action_required=False,
            currency=payment_information.currency,
            error=error,
            customer_id=payment_information.customer_id,
        )


def confirm_payment(
        self, payment_information: "PaymentData", previous_value
) -> "GatewayResponse":
    config = self._get_gateway_config()
    # The additional checks are proceed asynchronously so we try to confirm that
    # the payment is already processed
    payment = Payment.objects.filter(id=payment_information.payment_id).first()
    if not payment:
        raise PaymentError("Unable to find the payment.")

    transaction = (
        payment.transactions.filter(
            kind=TransactionKind.ACTION_TO_CONFIRM,
            is_success=True,
            action_required=False,
        )
            .exclude(token__isnull=False, token__exact="")
            .last()
    )

    kind = TransactionKind.AUTH
    if config.auto_capture:
        kind = TransactionKind.CAPTURE

    # if not transaction:
    #     return self._process_additional_action(payment_information, kind)

    result_code = transaction.gateway_response.get("actionCodeDescription", "").strip().lower()
    if result_code and result_code in PENDING_STATUSES:
        kind = TransactionKind.PENDING

    transaction_already_processed = payment.transactions.filter(
        kind=kind,
        is_success=True,
        action_required=False,
        amount=payment_information.amount,
        currency=payment_information.currency,
    ).first()
    is_success = True

    # confirm that we should proceed the capture action
    if (
            not transaction_already_processed
            and config.auto_capture
            and kind == TransactionKind.CAPTURE
    ):
        is_success = True

    token = transaction.token
    if transaction_already_processed:
        token = transaction_already_processed.token

    return GatewayResponse(
        is_success=is_success,
        action_required=False,
        kind=kind,
        amount=payment_information.amount,  # type: ignore
        currency=payment_information.currency,  # type: ignore
        transaction_id=token,  # type: ignore
        error=None,
        raw_response={},
        transaction_already_processed=bool(transaction_already_processed),
    )

import logging

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
SUPPORTED_CURRENCIES = ("RUB",)

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


def create_form(data, payment_information, connection_params):
    """Return the associated Sberbank payment form."""
    sberbank_payment_id, sberbank_payment_url = get_sberbank_register_info(payment_information,
                                                                           connection_params)

    form = SberbankPaymentForm(
        data=data,
        payment_information=payment_information,
        connection_params=connection_params,
        initial={
            'sberbank_payment_id': sberbank_payment_id,
        },
    )

    form.sberbank_payment_url = sberbank_payment_url

    return form


def get_sberbank_register_info(payment_information, connection_params):
    sberbank_client = get_client(connection_params)

    try:

        response = sberbank_client.payment.register(order_id=payment_information.order_id,
                                                    amount=get_amount_for_sberbank(payment_information.amount),
                                                    return_url=get_return_url(payment_information.order_id),
                                                    data=get_data_for_payment(payment_information))

        # orderId есть только у успешно зарегистрированных заказов
        if 'orderId' in response:
            # Создадим транзакцию, которую будем обновлять фоновым заданием
            token = response['orderId']
            payment_information.token = token
            txn = create_transaction(
                payment=Payment.objects.get(order_id=payment_information.order_id),
                kind=TransactionKind.CAPTURE,
                payment_information=payment_information,
            )

            check_status_sberbank_task.delay(order_id=token,
                                             connection_params=connection_params)
            return token, response['formUrl']

        if 'errorCode' in response:
            error_code = int(response['errorCode'])
            if error_code in errors.ERRORS:
                error_msg = response['errorMessage']
                logger.critical('{}:{}'.format(error_code, error_msg))
                raise Exception(error_msg)

    except SBERBANK_EXCEPTIONS as exc:
        error = get_error_message_from_sberbank_error(exc)
        response = get_error_response(
            payment_information.amount, error=error, id=payment_information.order_id
        )


def check_payment_supported(payment_information: PaymentData):
    """Check that a given payment is supported."""
    if payment_information.currency not in SUPPORTED_CURRENCIES:
        return errors.UNSUPPORTED_CURRENCY % {"currency": payment_information.currency}


def get_client(connection_params):
    """Create a Sberbank client from set-up application keys."""
    sberbank_client = sberbank.Client(auth=(connection_params['login'], connection_params['password']),
                                      sandbox=connection_params['sandbox_mode'])
    return sberbank_client



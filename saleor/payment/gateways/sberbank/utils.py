from decimal import Decimal

# from ..sberbank import SBERBANK_EXCEPTIONS, logger
from . import client as sberbank
from ... import PaymentError
from ...models import Order
from .errors import ERRORS as FAILED_STATUSES


def get_error_response(amount: Decimal, **additional_kwargs) -> dict:
    """Create a placeholder response for invalid or failed requests.

    It is used to generate a failed transaction object.
    """
    return {"is_success": False, "amount": amount, **additional_kwargs}


def get_amount_for_sberbank(amount):
    """В Сбербанк необходимо передавать значение в копейках или центах
    Поэтому необходимо получить значение в копейках
    https://developer.sberbank.ru/doc/v1/acquiring/rest-requests1pay
    """

    amount *= 100

    return int(amount.to_integral_value())


def get_order_token(order_id):
    return Order.objects.get(pk=order_id).token


def get_return_url(order_id):
    #return build_absolute_uri(reverse("order:payment-success", kwargs={"token": get_order_token(order_id)}))
    return ('http://localhost:3000/checkout/review')

def get_data_for_payment(payment_information):
    data = {
        'language': 'ru',
        'currency': 643,
        'email': payment_information.customer_email,
    }
    return data

def api_call(request_data: dict, config):

    sberbank_client = sberbank.Client(
        auth=(config.connection_params['login'], config.connection_params['password']),
        sandbox=config.connection_params['sandbox_mode'])

    response = sberbank_client.payment.get_status(order_id=request_data.get('payment_id'))
    result_code = response.get('errorCode')
    is_success = result_code not in FAILED_STATUSES
    if is_success:
        return response
    else:
        raise PaymentError(
            code=response.get('errorCode'),
            message=response.get('errorMessage')
        )
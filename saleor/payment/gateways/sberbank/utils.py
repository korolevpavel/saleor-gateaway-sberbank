from decimal import Decimal

from django.urls import reverse

from ...models import Order
from ....core.utils import build_absolute_uri


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
    return build_absolute_uri(reverse("order:payment-success", kwargs={"token": get_order_token(order_id)}))


def get_data_for_payment(payment_information):
    data = {
        'currency': 643,
        'email': payment_information.customer_email,
    }
    return data

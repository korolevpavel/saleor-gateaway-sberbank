from .base import Resource
from ..constants.url import URL


class Payment(Resource):
    def __init__(self, client):
        super(Payment, self).__init__(client)
        self.base_url = client.base_url

    def all(self, data={}, **kwargs):
        """"
        Fetch all Payment entities

        Returns:
            Dictionary of Payment data
        """
        return super(Payment, self).all(data, **kwargs)

    def register(self, order_id, amount, return_url, data={}, **kwargs):
        """"
        Запрос  регистрации заказа в Сбербанке

        Args:
            order_id : Id for which payment object has to be retrieved
            amount : Amount for which the payment has to be retrieved

        Returns:
            Payment form URL to redirect the client's browser to.
            :param data:
        """
        data['amount'] = amount
        data['orderNumber'] = order_id
        data['returnUrl'] = return_url

        return self.post_url(URL.REGISTER_URL, data, **kwargs)

    def get_status(self, order_id, data={}, **kwargs):
        """"
        Get payment status in Sberbank

        Args:
            order_id : ID of the registered order in Sberbank

        Returns:
            Order status in the payment system
        """

        data['orderId'] = order_id
        return self.post_url(URL.STATUS_URL, data, **kwargs)

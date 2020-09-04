from ....celeryconf import app
from . import client as sberbank
from ...models import Payment, Transaction


@app.task(bind=True, default_retry_delay=60, time_limit=1200)
def check_status_sberbank_task(self, order_id, connection_params):
    sberbank_client = sberbank.Client(auth=(connection_params['login'], connection_params['password']),
                                      sandbox=connection_params['sandbox_mode'])

    response = sberbank_client.payment.get_status(order_id=order_id)

    txn = Transaction.objects.get(token=order_id)
    if response['actionCode'] == 0:

        txn.is_success = True
        txn.save()

        payment = Payment.objects.get(pk=txn.payment_id)
        payment.charge_status = 'fully-charged'
        payment.captured_amount = payment.total
        payment.save()

        return 'Success pay on Sberbank for ' + str(order_id)
    else:
        self.retry(countdown=60)

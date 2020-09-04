from django import forms


class SberbankPaymentForm(forms.Form):
    sberbank_payment_id = forms.CharField(required=True, widget=forms.HiddenInput)

    def __init__(self, payment_information, connection_params, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_payment_token(self):
        return self.cleaned_data["sberbank_payment_id"]

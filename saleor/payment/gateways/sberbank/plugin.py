from saleor.plugins.base_plugin import BasePlugin, ConfigurationTypeField
from django.utils.translation import pgettext_lazy

from ..utils import get_supported_currencies
from . import (GatewayConfig,
               confirm_payment,
               process_payment,
               )

from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse, HttpResponseNotFound

from .webhooks import handle_additional_actions

GATEWAY_NAME = "Sberbank"
ADDITIONAL_ACTION_PATH = "/additional-actions"


def require_active_plugin(fn):
    def wrapped(self, *args, **kwargs):
        previous = kwargs.get("previous_value", None)
        if not self.active:
            return previous
        return fn(self, *args, **kwargs)

    return wrapped


class SberbankGatewayPlugin(BasePlugin):
    PLUGIN_NAME = GATEWAY_NAME
    PLUGIN_ID = "korolev.payments.sberbank"

    DEFAULT_CONFIGURATION = [
        {"name": "Login", "value": None},
        {"name": "Password", "value": None},
        {"name": "Use sandbox", "value": True},
        {"name": "Automatic payment capture", "value": False},
        {"name": "Supported currencies", "value": "RUB"},
    ]

    CONFIG_STRUCTURE = {
        "Template path": {
            "type": ConfigurationTypeField.STRING,
            "help_text": pgettext_lazy(
                "Plugin help text", "Location of django payment template for gateway."
            ),
            "label": pgettext_lazy("Plugin label", "Template path"),
        },
        "Login": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Provide your login name Sberbank API",
            "label": "Username for API",
        },
        "Password": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Provide your password",
            "label": "Password for API",
        },
        "Use sandbox": {
            "type": ConfigurationTypeField.BOOLEAN,
            "help_text": pgettext_lazy(
                "Plugin help text",
                "Determines if Saleor should use Sberbank sandbox API.",
            ),
            "label": pgettext_lazy("Plugin label", "Use sandbox"),
        },
        "Automatic payment capture": {
            "type": ConfigurationTypeField.BOOLEAN,
            "help_text": pgettext_lazy(
                "Plugin help text",
                "Determines if Saleor should automaticaly capture payments.",
            ),
            "label": pgettext_lazy("Plugin label", "Automatic payment capture"),
        },
        "Supported currencies": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Determines currencies supported by gateway."
                         " Please enter currency codes separated by a comma.",
            "label": "Supported currencies",
        },
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}
        self.config = GatewayConfig(
            gateway_name=GATEWAY_NAME,
            auto_capture=configuration["Automatic payment capture"],
            supported_currencies=configuration["Supported currencies"],
            connection_params={
                "sandbox_mode": configuration["Use sandbox"],
                "login": configuration["Login"],
                "password": configuration["Password"]
            },
        )

    def _get_gateway_config(self) -> GatewayConfig:
        return self.config

    @require_active_plugin
    def get_supported_currencies(self, previous_value):
        config = self._get_gateway_config()
        return get_supported_currencies(config, GATEWAY_NAME)

    @require_active_plugin
    def process_payment(
            self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        return process_payment(self, payment_information, self._get_gateway_config())

    @require_active_plugin
    def confirm_payment(
            self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        return confirm_payment(self, payment_information, previous_value)

    @require_active_plugin
    def token_is_required_as_payment_input(self, previous_value):
        return False

    def webhook(self, request: WSGIRequest, path: str, previous_value) -> HttpResponse:
        config = self._get_gateway_config()
        if path.startswith(ADDITIONAL_ACTION_PATH):
            return handle_additional_actions(
                request, config
            )
        return HttpResponseNotFound()

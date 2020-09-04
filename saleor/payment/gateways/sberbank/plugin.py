from saleor.extensions import ConfigurationTypeField
from saleor.extensions.base_plugin import BasePlugin
from django.utils.translation import pgettext_lazy

from . import (GatewayConfig,
               capture,
               process_payment,
               create_form,
               )

GATEWAY_NAME = "Sberbank"


def require_active_plugin(fn):
    def wrapped(self, *args, **kwargs):
        previous = kwargs.get("previous_value", None)
        self._initialize_plugin_configuration()
        if not self.active:
            return previous
        return fn(self, *args, **kwargs)

    return wrapped


class SberbankGatewayPlugin(BasePlugin):
    PLUGIN_NAME = GATEWAY_NAME
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
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = None

    def _initialize_plugin_configuration(self):
        super()._initialize_plugin_configuration()

        if self._cached_config and self._cached_config.configuration:
            configuration = self._cached_config.configuration

            configuration = {item["name"]: item["value"] for item in configuration}
            self.config = GatewayConfig(
                gateway_name=GATEWAY_NAME,
                auto_capture=configuration["Automatic payment capture"],
                connection_params={
                    "sandbox_mode": configuration["Use sandbox"],
                    "login": configuration["Login"],
                    "password": configuration["Password"]
                },
                template_path=configuration["Template path"],
            )

    @classmethod
    def _hide_secret_configuration_fields(cls, configuration):
        secret_fields = ["Password"]
        for field in configuration:
            # We don't want to share our secret data
            if field.get("name") in secret_fields and field.get("value"):
                field["value"] = cls.REDACTED_FORM

    @classmethod
    def _get_default_configuration(cls):
        defaults = {
            "name": cls.PLUGIN_NAME,
            "description": "Sberbank payments",
            "active": False,
            "configuration": [
                {"name": "Template path", "value": "order/payment/sberbank.html"},
                {"name": "Login", "value": ""},
                {"name": "Password", "value": ""},
                {"name": "Use sandbox", "value": True},
            ],
        }
        return defaults

    def _get_gateway_config(self) -> GatewayConfig:
        return self.config

    @require_active_plugin
    def capture_payment(
            self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        return capture(payment_information, self._get_gateway_config())

    @require_active_plugin
    def process_payment(
            self, payment_information: "PaymentData", previous_value
    ) -> "GatewayResponse":
        return process_payment(payment_information, self._get_gateway_config())


    @require_active_plugin
    def create_form(
            self, data, payment_information: "PaymentData", previous_value
    ) -> "forms.Form":
        return create_form(
            data,
            payment_information,
            connection_params=self._get_gateway_config().connection_params,
        )

    @require_active_plugin
    def get_payment_template(self, previous_value) -> str:
        return self._get_gateway_config().template_path

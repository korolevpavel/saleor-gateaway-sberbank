import { storiesOf } from "@storybook/react";
import { action } from "@storybook/addon-actions";
import React from "react";
import { IntlProvider } from "react-intl";

import { SberbankPaymentGateway } from ".";

const processPayment = action("processPayment");
const submitPayment = async () => action("submitPayment");
const submitPaymentSuccess = action("submitPaymentSuccess");
const onError = action("onError");

storiesOf("@components/organisms/SberbankPaymentGateway", module)
  .addParameters({ component: SberbankPaymentGateway })
  .addDecorator(story => <IntlProvider locale="en">{story()}</IntlProvider>)
  .add("default", () => (
    <SberbankPaymentGateway
      processPayment={processPayment}
      submitPayment={submitPayment}
      submitPaymentSuccess={submitPaymentSuccess}
      onError={onError}
    />
  ));

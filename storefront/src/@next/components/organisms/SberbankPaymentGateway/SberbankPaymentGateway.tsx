import React, { useEffect, useRef } from "react";

import { IFormError } from "@types";
import { CompleteCheckout_checkoutComplete_order } from "@saleor/sdk/lib/mutations/gqlTypes/CompleteCheckout";
import { ErrorMessage } from "@components/atoms";

export const sberbankNotNegativeConfirmationStatusCodes = ["Успешно"];

interface SberbankSubmitState {
  data?: any;
  isValid?: boolean;
}

export interface IPropsSber {
  formRef?: React.RefObject<HTMLFormElement>;

  processPayment: () => void;

  submitPayment: (data: {
    confirmationData: any;
    confirmationNeeded: boolean;
  }) => Promise<any>;

  submitPaymentSuccess: (
    order?: CompleteCheckout_checkoutComplete_order
  ) => void;

  errors?: IFormError[];

  onError: (errors: IFormError[]) => void;
}

const SberbankPaymentGateway: React.FC<IPropsSber> = ({
  formRef,
  processPayment,
  submitPayment,
  submitPaymentSuccess,
  errors,
  onError,
}: IPropsSber) => {
  const gatewayRef = useRef<HTMLDivElement>(null);

  const handlePaymentAction = (data?: any) => {
    if (data?.url) {
      window.location.href = data?.url;
    } else {
      onError([new Error("Invalid payment url. please try again")]);
    }
  };

  const onSubmitSberbankForm = async (state?: SberbankSubmitState) => {
    const payment = await submitPayment(state?.data);
    if (payment.errors?.length) {
      onError(payment.errors);
    } else {
      let paymentActionData;
      try {
        paymentActionData = JSON.parse(payment.confirmationData);
      } catch (parseError) {
        onError([
          new Error(
            "Payment needs confirmation but data required for confirmation received from the server is malformed."
          ),
        ]);
      }
      try {
        handlePaymentAction(paymentActionData);
      } catch (error) {
        onError([new Error(error)]);
      }
    }
  };

  useEffect(() => {
    (formRef?.current as any)?.addEventListener("submitComplete", () => {
      onSubmitSberbankForm();
    });
  }, [formRef]);

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    processPayment();
  };

  return (
    <form ref={formRef} onSubmit={handleSubmit}>
      <div ref={gatewayRef} />
      <ErrorMessage errors={errors} />
    </form>
  );
};

export { SberbankPaymentGateway };

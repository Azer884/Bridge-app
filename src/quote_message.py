"""Customer-facing quotation text. The breakdown stays with the SME; the customer only ever
receives the approved total."""

INSPECTION_MESSAGE = ("This job needs an inspection before we can give a reliable price, so a member "
                      "of our team will contact you to arrange it.")


def approved_quote_message(total, currency, business_name):
    return (f"Good news from {business_name}: your quotation is {currency} {total:,.2f} in total "
            "(excluding any applicable tax). A team member will contact you to confirm the appointment.")

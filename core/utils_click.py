from django.conf import settings

def get_click_link(registration_id: int, amount: int, return_url: str = "https://irnolympiad.uz/dashboard") -> str:
    """
    Generates Click Button redirect payment link.
    amount is in UZS. Format: N.NN
    """
    if not amount or amount <= 0:
        raise ValueError(f"Invalid payment amount: {amount}")

    service_id = settings.CLICK_SERVICE_ID
    merchant_id = settings.CLICK_MERCHANT_ID
    merchant_user_id = settings.CLICK_MERCHANT_USER_ID
    formatted_amount = f"{amount:.2f}"

    return (
        f"https://my.click.uz/services/pay/"
        f"?service_id={service_id}"
        f"&merchant_id={merchant_id}"
        f"&amount={formatted_amount}"
        f"&transaction_param={registration_id}"
        f"&merchant_user_id={merchant_user_id}"
        f"&return_url={return_url}"
    )

from django.conf import settings
import base64
import json


def get_payme_link(registration_id: int, amount: int, return_url: str = "https://irnolympiad.uz/dashboard/history"):
    if not amount or amount <= 0:
        raise ValueError(f"Invalid payment amount: {amount}")

    # Payme expects amount in TIYIN (1 sum = 100 tiyin)
    amount_tiyin = int(amount) * 100

    params = {
        "m": settings.PAYME_ID,
        "ac.registration_id": str(registration_id),
        "a": amount_tiyin,
        "c": return_url,
    }

    encoded = base64.b64encode(json.dumps(params).encode()).decode()
    base_url = settings.PAYME_URL  # test.paycom.uz or checkout.paycom.uz

    return f"{base_url}/{encoded}"
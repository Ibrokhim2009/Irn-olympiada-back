from django.conf import settings
from payme import Payme


def get_payme_link(registration_id: int, amount: int, return_url: str = "https://irnolympiad.uz/dashboard/history"):
    if not amount or amount <= 0:
        raise ValueError(f"Invalid payment amount: {amount}")

    amount_in_tiyin = int(amount * 100)

    # ✅ Payme minimum is 1000 tiyin (10 sum)
    if amount_in_tiyin < 1000:
        raise ValueError(f"Amount too small: {amount_in_tiyin} tiyin. Minimum is 1000 tiyin (10 sum).")

    payme = Payme(payme_id=settings.PAYME_ID)
    return payme.generate_pay_link(
        id=registration_id,
        amount=amount_in_tiyin,
        return_url=return_url
    )
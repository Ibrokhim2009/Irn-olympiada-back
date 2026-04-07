from django.conf import settings
from payme import Payme


def get_payme_link(registration_id: int, amount: int, return_url: str = "https://irnolympiad.uz/dashboard/history"):
    """
    amount is in UZS (sum). The payme-pkg library handles tiyin conversion internally.
    """
    if not amount or amount <= 0:
        raise ValueError(f"Invalid payment amount: {amount}")

    payme = Payme(payme_id=settings.PAYME_ID)
    return payme.generate_pay_link(
        id=int(registration_id),
        amount=int(amount),
        return_url=return_url
    )
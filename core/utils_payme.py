from django.conf import settings
from payme import Payme


def get_payme_link(registration_id: int, amount: int, return_url: str = "https://irnolympiad.uz/dashboard/history"):
    """
    Генерирует ссылку на оплату через библиотеку payme-pkg.
    amount передаётся в сумах (UZS), конвертируется в тийины (* 100).
    Минимум: 1000 тийин = 10 сум.
    """
    if not amount or amount <= 0:
        raise ValueError(f"Invalid payment amount: {amount}. Amount must be greater than 0.")

    payme = Payme(payme_id=settings.PAYME_ID)

    # ✅ Payme requires amount in tiyin (1 sum = 100 tiyin)
    amount_in_tiyin = int(amount * 100)

    return payme.generate_pay_link(
        id=registration_id,
        amount=amount_in_tiyin,
        return_url=return_url
    )
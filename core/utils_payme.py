from django.conf import settings
from payme import Payme

def get_payme_link(registration_id: int, amount: int, return_url: str = "https://irnolympiad.uz/dashboard/history"):
    """
    Генерирует ссылку на оплату через библиотеку payme-pkg
    """
    payme = Payme(payme_id=settings.PAYME_ID)
    # payme-pkg ожидает сумму в тийинах (сум * 100)
    return payme.generate_pay_link(
        id=registration_id,
        amount=int(amount * 100),
        return_url=return_url
    )

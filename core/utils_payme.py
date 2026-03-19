from django.conf import settings
from payme import Payme

def get_payme_link(registration_id: int, amount: int, return_url: str = "https://irnolympiad.uz/dashboard/history"):
    payme = Payme(payme_id=settings.PAYME_ID, is_test_env=True)
    return payme.generate_pay_link(
        id=registration_id,
        amount=int(amount) * 100,
        return_url=return_url
    )

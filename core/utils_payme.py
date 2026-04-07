def get_payme_link(registration_id: int, amount: int, return_url: str = "https://irnolympiad.uz/dashboard/history"):
    if not amount or amount <= 0:
        raise ValueError(f"Invalid payment amount: {amount}")

    amount_in_tiyin = int(amount * 100)

    if amount_in_tiyin < 1000:
        raise ValueError(f"Amount too small: {amount_in_tiyin} tiyin.")

    payme = Payme(payme_id=settings.PAYME_ID)
    
    # ✅ Force int to avoid zero-padding bug
    return payme.generate_pay_link(
        id=int(registration_id),
        amount=amount_in_tiyin,
        return_url=return_url
    )
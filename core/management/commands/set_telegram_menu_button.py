import requests
from django.core.management.base import BaseCommand

BOT_TOKEN = "7361972097:AAFOiy-yKvejKL_nG4r9b7ecmj6TzJC655A"
MINI_APP_URL = "https://irnolympiad.uz/"


class Command(BaseCommand):
    help = (
        "One-off: sets @irnolympiad_bot's global chat menu button to open the "
        "full site as a Telegram Mini App. Only needs to be re-run if the menu "
        "button text/URL changes — it is not part of the normal deploy cycle."
    )

    def handle(self, *args, **options):
        res = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/setChatMenuButton",
            json={
                "menu_button": {
                    "type": "web_app",
                    "text": "Ilova / Открыть",
                    "web_app": {"url": MINI_APP_URL},
                }
            },
        )
        data = res.json()
        if data.get("ok"):
            self.stdout.write(self.style.SUCCESS(f"Menu button set to {MINI_APP_URL}"))
        else:
            self.stdout.write(self.style.ERROR(f"Failed: {data}"))

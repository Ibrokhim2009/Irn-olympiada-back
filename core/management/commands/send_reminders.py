import os
import django
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from core.models import Olympiad, Registration, Notification

class Command(BaseCommand):
    help = 'Отправляет автоматические напоминания об олимпиадах'

    def handle(self, *args, **options):
        now = timezone.now()
        
        # 1. За 24 часа до начала
        target_24h = now + timedelta(hours=24)
        olys_24h = Olympiad.objects.filter(
            start_datetime__lte=target_24h, 
            start_datetime__gt=now + timedelta(hours=23),
            is_active=True
        )
        self.send_batch_reminders(olys_24h, "Напоминание: 24 часа до начала", "Eslatma: 24 soat qoldi")

        # 2. За 5 часов до начала
        target_5h = now + timedelta(hours=5)
        olys_5h = Olympiad.objects.filter(
            start_datetime__lte=target_5h, 
            start_datetime__gt=now + timedelta(hours=4, minutes=30),
            is_active=True
        )
        self.send_batch_reminders(olys_5h, "Напоминание: 5 часов до начала", "Eslatma: 5 soat qoldi")

        # 3. За 30 минут до начала
        target_30m = now + timedelta(minutes=30)
        olys_30m = Olympiad.objects.filter(
            start_datetime__lte=target_30m, 
            start_datetime__gt=now + timedelta(minutes=25),
            is_active=True
        )
        self.send_batch_reminders(olys_30m, "Внимание: Начало через 30 минут!", "Diqqat: 30 daqiqadan so'ng boshlanadi!")

    def send_batch_reminders(self, olys, title_ru, title_uz):
        for oly in olys:
            regs = Registration.objects.filter(olympiad=oly, payment_status__in=['paid', 'free'])
            created_count = 0
            for reg in regs:
                # Проверяем, не отправляли ли уже такое уведомление за последний час
                exists = Notification.objects.filter(
                    user=reg.user, 
                    title_ru=title_ru, 
                    created_at__gt=timezone.now() - timedelta(hours=1)
                ).exists()
                
                if not exists:
                    Notification.objects.create(
                        user=reg.user,
                        title_ru=title_ru,
                        title_uz=title_uz,
                        title_en=title_ru, # fallback
                        message_ru=f"Олимпиада '{oly.title_ru}' скоро начнется. Будьте готовы!",
                        message_uz=f"'{oly.title_uz}' olimpiadasi yaqinda boshlanadi. Tayyor turing!",
                        message_en=f"Olympiad '{oly.title_en}' is starting soon. Get ready!",
                        type='warning'
                    )
                    created_count += 1
            if created_count > 0:
                self.stdout.write(self.style.SUCCESS(f"Sent {created_count} reminders for {oly.title_ru}"))

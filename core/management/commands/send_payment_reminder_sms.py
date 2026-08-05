from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from core.models import Olympiad, Registration, PaymentReminderSMSSettings
from core.utils_eskiz import send_sms


class Command(BaseCommand):
    help = (
        "Sends a reminder SMS (interval/text configured in PaymentReminderSMSSettings, "
        "editable from the admin SMS Manager page) to users who started registering for "
        "an olympiad but never completed payment (pending or expired reservation), for "
        "olympiads with payment_reminder_sms_enabled=True and still-open registration."
    )

    def handle(self, *args, **options):
        now = timezone.now()
        settings_obj = PaymentReminderSMSSettings.get_solo()
        reminder_interval = timedelta(hours=settings_obj.interval_hours)

        olympiads = Olympiad.objects.filter(
            payment_reminder_sms_enabled=True,
            is_active=True,
            registration_end_date__gt=now,
        )

        sent_count = 0
        for oly in olympiads:
            remaining = oly.registration_end_date - now
            if remaining.total_seconds() <= 0:
                continue
            days = remaining.days
            hours = remaining.seconds // 3600
            time_text = f"{days} kun va {hours} soat" if days > 0 else f"{hours} soat"

            title = oly.get_translated('title', 'uz')
            try:
                message = settings_obj.message_template.format(olympiad=title, time_left=time_text)
            except (KeyError, IndexError) as e:
                self.stderr.write(f"Bad message_template placeholder ({e}), falling back to default text.")
                message = (
                    f"⏳ {title} olimpiadasiga ro'yxatdan o'tish yakunlanishiga atigi "
                    f"{time_text} qoldi! Ishtirok etish imkoniyatini qo'ldan boy bermang — "
                    f"hoziroq ro'yxatdan o'ting! 🏆"
                )

            regs = Registration.objects.filter(
                olympiad=oly,
                payment_status__in=[Registration.PaymentStatus.PENDING, Registration.PaymentStatus.EXPIRED],
            ).select_related('user')

            for reg in regs:
                if reg.last_payment_reminder_sent_at and now - reg.last_payment_reminder_sent_at < reminder_interval:
                    continue
                phone = reg.user.phone
                if not phone:
                    continue

                result = send_sms(phone, message)
                if isinstance(result, dict) and result.get("status") == "error":
                    self.stderr.write(f"Failed to send reminder to {phone}: {result.get('message')}")
                    continue

                reg.last_payment_reminder_sent_at = now
                reg.save(update_fields=['last_payment_reminder_sent_at'])
                sent_count += 1

        self.stdout.write(self.style.SUCCESS(f"Sent {sent_count} payment reminder SMS."))

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from core.models import User, Registration, Olympiad

print("Searching for users with name 'Shuhrat':")
users = User.objects.filter(first_name__icontains="Shuhrat") | User.objects.filter(last_name__icontains="Shuhrat") | User.objects.filter(username__icontains="Shuhrat")
for u in users:
    print(f"User ID: {u.id}, Username: {u.username}, Name: {u.first_name} {u.last_name}, Role: {u.role}, Active: {u.is_active}")
    print("Registrations:")
    for reg in u.registrations.all():
        print(f"  - Reg ID: {reg.id}, Olympiad: {reg.olympiad.id} ({reg.olympiad.title_ru} / {reg.olympiad.title_uz}), Status: {reg.payment_status}")

print("\nListing all registrations for 'IRN Respublika Ingliz tili Olimpiadasi 2026':")
try:
    oly = Olympiad.objects.get(title_uz__icontains="IRN Respublika Ingliz tili Olimpiadasi 2026")
    print(f"Olympiad ID: {oly.id}, Title: {oly.title_uz}")
    regs = Registration.objects.filter(olympiad=oly)
    for r in regs:
        print(f"  - User: {r.user.first_name} {r.user.last_name} (Role: {r.user.role}, Active: {r.user.is_active}), Status: {r.payment_status}")
except Exception as e:
    print("Error:", e)

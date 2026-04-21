import os
import django

# Updated settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'src.settings')
django.setup()

from core.models import User, Olympiad, Registration, SubOlympiadGrade
from django.db.models import Q

users = User.objects.filter(role=User.Role.PARTICIPANT)
print(f"Total participants: {users.count()}")

target_user = None
for u in users:
    if u.registrations.exists():
        target_user = u
        break

if not target_user:
    print("No participant with registrations found. Checking all participants...")
    target_user = users.first()

if not target_user:
    print("No participants at all!")
    exit()

print(f"DEBUG USER: {target_user.username} (ID: {target_user.id})")
print(f"Grade: '{target_user.grade}'")

user_regs = Registration.objects.filter(user=target_user)
print(f"User Registrations ({user_regs.count()}):")
for reg in user_regs:
    oly = reg.olympiad
    print(f" - Reg ID: {reg.id}, Oly ID: {oly.id}, Oly Title: {oly.title_ru}, Active: {oly.is_active}")

print("\n--- Simulating get_queryset ---")
qs = Olympiad.objects.all()
print(f"Total Olympiads: {qs.count()}")
active_qs = qs.filter(is_active=True)
print(f"Active Olympiads: {active_qs.count()}")

reg_filter = Q(registrations__user=target_user)
grade_filter = Q()
if target_user.grade:
    user_grade = str(target_user.grade).strip()
    grade_filter = (Q(grades=[]) | Q(subs__grade_sessions__grade__iexact=user_grade))
    print(f"Grade filter applied for '{user_grade}'")
else:
    print("No grade filter (user.grade is empty)")

final_qs = active_qs.filter(reg_filter | grade_filter).distinct()
print(f"Final QuerySet count: {final_qs.count()}")
for oly in final_qs:
    print(f" - Visible Oly ID: {oly.id}, Title: {oly.title_ru}")

# Check if grade matching works as expected
print("\n--- Checking Grade Sessions ---")
all_sessions = SubOlympiadGrade.objects.all()
print(f"Total Grade Sessions: {all_sessions.count()}")
for gs in all_sessions:
    print(f" - Session ID: {gs.id}, Grade: '{gs.grade}', SubOly: {gs.sub_olympiad.title_ru}")

if target_user.grade:
    matching_sessions = all_sessions.filter(grade__iexact=target_user.grade.strip())
    print(f"Sessions matching user grade '{target_user.grade.strip()}': {matching_sessions.count()}")

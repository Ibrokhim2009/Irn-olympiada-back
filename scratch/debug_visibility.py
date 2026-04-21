import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IRNolympiadBack.settings')
django.setup()

from core.models import User, Olympiad, Registration
from django.db.models import Q

# Let's check a participant
user = User.objects.filter(role=User.Role.PARTICIPANT).first()
if not user:
    print("No participant found")
    exit()

print(f"User: {user.username}, Grade: {user.grade}")

registrations = Registration.objects.filter(user=user)
print(f"Registrations count: {registrations.count()}")
for reg in registrations:
    print(f" - Registered for Olympiad ID: {reg.olympiad_id}")

grade = user.grade
queryset = Olympiad.objects.all()

if grade:
    # Try the filter I added
    try:
        filtered = queryset.filter(
            Q(grades__contains=grade) | Q(registrations__user=user)
        ).distinct()
        print(f"Filtered (grade={grade}) count: {filtered.count()}")
        for oly in filtered:
            print(f" - Oly ID: {oly.id}, Grades: {oly.grades}")
    except Exception as e:
        print(f"Error during filter: {e}")

    # Try searching as integer if it's a numeric list
    try:
        g_int = int(grade)
        filtered_int = queryset.filter(
            Q(grades__contains=g_int) | Q(registrations__user=user)
        ).distinct()
        print(f"Filtered (grade_int={g_int}) count: {filtered_int.count()}")
    except:
        pass
else:
    print("User has no grade set")

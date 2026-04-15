import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IRNolympiadBack.settings')
try:
    django.setup()
except Exception as e:
    print(f"Django setup failed: {e}")

from core.models import ExamResult, Olympiad, User

print("\n=== SYSTEM DEBUG: RESULTS VISIBILITY ===")
results = ExamResult.objects.all()
if not results.exists():
    print("NO RESULTS FOUND IN DATABASE AT ALL.")
else:
    for r in results:
        status = "VISIBLE"
        reason = ""
        if not r.completed_at:
            status = "HIDDEN"
            reason += "[Not finished by user] "
        if r.olympiad and not r.olympiad.is_completed:
            status = "HIDDEN"
            reason += "[Olympiad not 'Finished' by Admin] "
            
        print(f"ResultID: {r.id} | User: {r.user.username} (ID: {r.user.id}) | Score: {r.score} | Status: {status} | Reason: {reason}")

print("\n=== OLYMPIADS STATUS ===")
for o in Olympiad.objects.all():
    print(f"Oly: {o.title_ru} | is_completed: {o.is_completed}")

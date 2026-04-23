
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'src.settings')
django.setup()

from core.models import ExamResult, User

user_id = 2
user = User.objects.get(id=user_id)
results = ExamResult.objects.filter(user=user)

print(f"Results for user {user.username} (ID: {user_id}):")
for r in results:
    print(f"ID: {r.id}, Olympiad: {r.olympiad_id}, Session: {r.sub_olympiad_grade_id}, Score: {r.score}, Completed: {r.completed_at}, AnswersLen: {len(str(r.answers_json)) if r.answers_json else 0}")

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IRNolympiadBack.settings')
django.setup()

from core.models import Olympiad, ExamResult, User

print('--- Olympiads Status ---')
for o in Olympiad.objects.all():
    print(f'ID: {o.id}, Title: {o.title_ru}, is_completed: {o.is_completed}, is_started: {o.is_started}')

print('\n--- Exam Results ---')
for r in ExamResult.objects.all():
    print(f'ID: {r.id}, User: {r.user.username}, Oly: {r.olympiad.title_ru if r.olympiad else "None"}, Score: {r.score}, Completed: {r.completed_at is not None}')

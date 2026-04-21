import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'IRNolympiadBack.settings')
django.setup()

from core.models import Olympiad, SubOlympiadGrade

def sync_all_grades():
    olympiads = Olympiad.objects.all()
    print(f"Syncing {olympiads.count()} olympiads...")
    for oly in olympiads:
        all_grades = SubOlympiadGrade.objects.filter(
            sub_olympiad__olympiad=oly
        ).values_list('grade', flat=True).distinct()
        
        numeric_grades = []
        for g in all_grades:
            try:
                numeric_grades.append(int(g))
            except:
                pass
        
        oly.grades = sorted(numeric_grades)
        oly.save(update_fields=['grades'])
        print(f" - {oly.title_ru or oly.id}: {oly.grades}")

if __name__ == "__main__":
    sync_all_grades()
